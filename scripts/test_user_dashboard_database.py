#!/usr/bin/env python3
"""Development-only, rollback-only Dashboard and Workspace Trash DB acceptance."""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess


ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT / ".env"

USER_IDS = (
    "00000000-0000-4000-8000-00000000f501",
    "00000000-0000-4000-8000-00000000f502",
    "00000000-0000-4000-8000-00000000f503",
    "00000000-0000-4000-8000-00000000f504",
    "00000000-0000-4000-8000-00000000f505",
)
IMAGE_IDS = (
    "00000000-0000-4000-8000-00000000f511",
    "00000000-0000-4000-8000-00000000f512",
    "00000000-0000-4000-8000-00000000f513",
    "00000000-0000-4000-8000-00000000f514",
    "00000000-0000-4000-8000-00000000f515",
    "00000000-0000-4000-8000-00000000f516",
    "00000000-0000-4000-8000-00000000f517",
    "00000000-0000-4000-8000-00000000f518",
    "00000000-0000-4000-8000-00000000f519",
    "00000000-0000-4000-8000-00000000f51a",
    "00000000-0000-4000-8000-00000000f51b",
)

EXPECTED_MARKERS = (
    "dashboard_database_pg_proc_security=yes",
    "dashboard_database_acl_boundary=yes",
    "dashboard_database_aggregate=yes",
    "dashboard_database_owner_isolation=yes",
    "dashboard_database_identity_guards=yes",
    "workspace_trash_database_owner_filter=yes",
    "workspace_trash_database_state_filter=yes",
    "dashboard_database_fixtures_rolled_back=yes",
)


SQL = r"""
\set ON_ERROR_STOP on

begin;
select pg_advisory_xact_lock(hashtextextended('mt-dashboard-trash-database-test', 0));

do $$
declare
  proc_row record;
  allowed_authenticated oid := (select oid from pg_roles where rolname = 'authenticated');
begin
  if allowed_authenticated is null
     or not exists (select 1 from pg_roles where rolname = 'anon')
     or not exists (select 1 from pg_roles where rolname = 'service_role') then
    raise exception 'Supabase database roles are unavailable';
  end if;

  for proc_row in
    select
      p.oid,
      p.oid::regprocedure::text as identity,
      p.proowner,
      p.prosecdef,
      p.proconfig,
      p.oid in (
        'public.get_my_dashboard()'::regprocedure,
        'public.workspace_list_trashed_drafts()'::regprocedure
      ) as allow_authenticated
    from pg_proc p
    where p.oid in (
      'public.dashboard_image_json(uuid)'::regprocedure,
      'public.get_my_dashboard()'::regprocedure,
      'public.workspace_list_trashed_drafts()'::regprocedure
    )
  loop
    if not proc_row.prosecdef then
      raise exception '% is not SECURITY DEFINER', proc_row.identity;
    end if;
    if not coalesce(proc_row.proconfig, '{}'::text[]) @> array['search_path=""']::text[] then
      raise exception '% does not pin an empty search_path', proc_row.identity;
    end if;
    if has_function_privilege('authenticated', proc_row.oid, 'EXECUTE')
       <> proc_row.allow_authenticated then
      raise exception '% has an invalid authenticated EXECUTE grant', proc_row.identity;
    end if;
    if has_function_privilege('anon', proc_row.oid, 'EXECUTE')
       or has_function_privilege('service_role', proc_row.oid, 'EXECUTE') then
      raise exception '% is executable by anon or service_role', proc_row.identity;
    end if;
    if exists (
      select 1
      from aclexplode(coalesce(
        (select p2.proacl from pg_proc p2 where p2.oid = proc_row.oid),
        acldefault('f', proc_row.proowner)
      )) privilege
      where privilege.privilege_type = 'EXECUTE'
        and privilege.grantee not in (
          proc_row.proowner,
          case when proc_row.allow_authenticated then allowed_authenticated else proc_row.proowner end
        )
    ) then
      raise exception '% grants EXECUTE outside its exact allowlist', proc_row.identity;
    end if;
  end loop;

  if (select count(*) from pg_proc p where p.oid in (
    'public.dashboard_image_json(uuid)'::regprocedure,
    'public.get_my_dashboard()'::regprocedure,
    'public.workspace_list_trashed_drafts()'::regprocedure
  )) <> 3 then
    raise exception 'Dashboard/Trash function metadata is incomplete';
  end if;
end
$$;

select 'dashboard_database_pg_proc_security=yes';

set local role anon;
do $$
begin
  begin
    perform public.get_my_dashboard();
    raise exception 'anon executed get_my_dashboard';
  exception when insufficient_privilege then
    null;
  end;
  begin
    perform public.workspace_list_trashed_drafts();
    raise exception 'anon executed workspace_list_trashed_drafts';
  exception when insufficient_privilege then
    null;
  end;
end
$$;
reset role;

set local role service_role;
do $$
begin
  begin
    perform public.get_my_dashboard();
    raise exception 'service_role executed get_my_dashboard';
  exception when insufficient_privilege then
    null;
  end;
  begin
    perform public.workspace_list_trashed_drafts();
    raise exception 'service_role executed workspace_list_trashed_drafts';
  exception when insufficient_privilege then
    null;
  end;
end
$$;
reset role;

select 'dashboard_database_acl_boundary=yes';

do $$
begin
  if exists (
    select 1 from public.users
    where id in (
      '00000000-0000-4000-8000-00000000f501',
      '00000000-0000-4000-8000-00000000f502',
      '00000000-0000-4000-8000-00000000f503',
      '00000000-0000-4000-8000-00000000f504',
      '00000000-0000-4000-8000-00000000f505'
    )
  ) or exists (
    select 1 from public.images
    where id between '00000000-0000-4000-8000-00000000f511'::uuid
      and '00000000-0000-4000-8000-00000000f51b'::uuid
  ) then
    raise exception 'fixed Dashboard database fixtures already exist';
  end if;
end
$$;

create function pg_temp.set_dashboard_claims(
  actor_id uuid,
  actor_aal text default 'aal1',
  recovery boolean default false
)
returns void
language plpgsql
as $$
begin
  perform set_config(
    'request.jwt.claims',
    jsonb_build_object(
      'sub', actor_id,
      'role', 'authenticated',
      'aal', actor_aal,
      'amr', case when recovery
        then jsonb_build_array(jsonb_build_object('method', 'recovery'))
        when actor_aal = 'aal2'
          then jsonb_build_array(
            jsonb_build_object('method', 'password'),
            jsonb_build_object('method', 'totp')
          )
        else jsonb_build_array(jsonb_build_object('method', 'password'))
      end
    )::text,
    true
  );
end
$$;

insert into public.users (
  id, auth_subject, email, email_verified_at, account_status
) values
  ('00000000-0000-4000-8000-00000000f501', '00000000-0000-4000-8000-00000000f501', 'dashboard-owner-a@example.test', now(), 'active'),
  ('00000000-0000-4000-8000-00000000f502', '00000000-0000-4000-8000-00000000f502', 'dashboard-owner-b@example.test', now(), 'active'),
  ('00000000-0000-4000-8000-00000000f503', '00000000-0000-4000-8000-00000000f503', 'dashboard-inactive@example.test', now(), 'suspended'),
  ('00000000-0000-4000-8000-00000000f504', '00000000-0000-4000-8000-00000000f504', 'dashboard-recovery@example.test', now(), 'active'),
  ('00000000-0000-4000-8000-00000000f505', '00000000-0000-4000-8000-00000000f505', 'dashboard-admin@example.test', now(), 'active');

insert into public.user_profiles (user_id, display_name) values
  ('00000000-0000-4000-8000-00000000f501', 'Dashboard Owner A'),
  ('00000000-0000-4000-8000-00000000f502', 'Dashboard Owner B'),
  ('00000000-0000-4000-8000-00000000f503', 'Dashboard Inactive'),
  ('00000000-0000-4000-8000-00000000f504', 'Dashboard Recovery'),
  ('00000000-0000-4000-8000-00000000f505', 'Dashboard Admin');

insert into public.user_roles (user_id, role, reason) values
  ('00000000-0000-4000-8000-00000000f501', 'user', 'Dashboard database acceptance'),
  ('00000000-0000-4000-8000-00000000f502', 'user', 'Dashboard database acceptance'),
  ('00000000-0000-4000-8000-00000000f503', 'user', 'Dashboard database acceptance'),
  ('00000000-0000-4000-8000-00000000f504', 'user', 'Dashboard database acceptance'),
  ('00000000-0000-4000-8000-00000000f505', 'user', 'Dashboard database acceptance'),
  ('00000000-0000-4000-8000-00000000f505', 'reviewer', 'Dashboard stacked-role acceptance'),
  ('00000000-0000-4000-8000-00000000f505', 'admin', 'Dashboard stacked-role acceptance');

insert into public.folders (id, owner_user_id, name, sort_order, is_system) values
  ('00000000-0000-4000-8000-00000000f571', '00000000-0000-4000-8000-00000000f501', 'Inbox', 0, true),
  ('00000000-0000-4000-8000-00000000f572', '00000000-0000-4000-8000-00000000f502', 'Inbox', 0, true),
  ('00000000-0000-4000-8000-00000000f575', '00000000-0000-4000-8000-00000000f505', 'Inbox', 0, true);

insert into public.images (
  id, owner_user_id, folder_id, processing_status, workflow_status,
  publication_status, original_filename, original_width, original_height,
  checksum_sha256, version, published_at, deleted_at, updated_at
) values
  ('00000000-0000-4000-8000-00000000f511', '00000000-0000-4000-8000-00000000f501', '00000000-0000-4000-8000-00000000f571', 'ready', 'draft', 'never_published', 'owner-a-draft.jpg', 1600, 1200, repeat('a', 64), 1, null, null, now() - interval '4 hours'),
  ('00000000-0000-4000-8000-00000000f512', '00000000-0000-4000-8000-00000000f501', '00000000-0000-4000-8000-00000000f571', 'failed', 'changes_requested', 'unpublished', 'owner-a-changes.jpg', 1600, 1200, repeat('b', 64), 1, null, null, now() - interval '3 hours'),
  ('00000000-0000-4000-8000-00000000f513', '00000000-0000-4000-8000-00000000f501', '00000000-0000-4000-8000-00000000f571', 'ready', 'submitted', 'never_published', 'owner-a-submitted.jpg', 1600, 1200, repeat('c', 64), 1, null, null, now() - interval '2 hours'),
  ('00000000-0000-4000-8000-00000000f514', '00000000-0000-4000-8000-00000000f501', '00000000-0000-4000-8000-00000000f571', 'ready', 'approved', 'published', 'owner-a-published.jpg', 1600, 1200, repeat('d', 64), 1, now() - interval '1 hour', null, now() - interval '1 hour'),
  ('00000000-0000-4000-8000-00000000f515', '00000000-0000-4000-8000-00000000f501', '00000000-0000-4000-8000-00000000f571', 'ready', 'draft', 'never_published', 'owner-a-trashed-draft.jpg', 1600, 1200, repeat('e', 64), 2, null, now() - interval '2 hours', now() - interval '2 hours'),
  ('00000000-0000-4000-8000-00000000f516', '00000000-0000-4000-8000-00000000f501', '00000000-0000-4000-8000-00000000f571', 'ready', 'changes_requested', 'never_published', 'owner-a-trashed-changes.jpg', 1600, 1200, repeat('f', 64), 2, null, now() - interval '1 hour', now() - interval '1 hour'),
  ('00000000-0000-4000-8000-00000000f517', '00000000-0000-4000-8000-00000000f501', '00000000-0000-4000-8000-00000000f571', 'ready', 'submitted', 'never_published', 'owner-a-trashed-submitted.jpg', 1600, 1200, repeat('1', 64), 2, null, now() - interval '30 minutes', now() - interval '30 minutes'),
  ('00000000-0000-4000-8000-00000000f518', '00000000-0000-4000-8000-00000000f502', '00000000-0000-4000-8000-00000000f572', 'ready', 'draft', 'never_published', 'owner-b-draft.jpg', 1200, 1600, repeat('2', 64), 1, null, null, now() - interval '2 hours'),
  ('00000000-0000-4000-8000-00000000f519', '00000000-0000-4000-8000-00000000f502', '00000000-0000-4000-8000-00000000f572', 'ready', 'draft', 'never_published', 'owner-b-trashed-draft.jpg', 1200, 1600, repeat('3', 64), 2, null, now() - interval '1 hour', now() - interval '1 hour'),
  ('00000000-0000-4000-8000-00000000f51a', '00000000-0000-4000-8000-00000000f502', '00000000-0000-4000-8000-00000000f572', 'ready', 'submitted', 'never_published', 'owner-b-submitted.jpg', 1200, 1600, repeat('4', 64), 1, null, null, now() - interval '1 hour'),
  ('00000000-0000-4000-8000-00000000f51b', '00000000-0000-4000-8000-00000000f505', '00000000-0000-4000-8000-00000000f575', 'ready', 'draft', 'never_published', 'admin-draft.jpg', 1400, 1400, repeat('5', 64), 1, null, null, now());

insert into public.image_versions (
  id, image_id, version_number, title, alt_text, created_by_user_id
) values
  ('00000000-0000-4000-8000-00000000f521', '00000000-0000-4000-8000-00000000f511', 1, 'Owner A Draft', 'Owner A draft fixture.', '00000000-0000-4000-8000-00000000f501'),
  ('00000000-0000-4000-8000-00000000f522', '00000000-0000-4000-8000-00000000f512', 1, 'Owner A Changes', 'Owner A changes fixture.', '00000000-0000-4000-8000-00000000f501'),
  ('00000000-0000-4000-8000-00000000f523', '00000000-0000-4000-8000-00000000f513', 1, 'Owner A Submitted', 'Owner A submitted fixture.', '00000000-0000-4000-8000-00000000f501'),
  ('00000000-0000-4000-8000-00000000f524', '00000000-0000-4000-8000-00000000f514', 1, 'Owner A Published', 'Owner A published fixture.', '00000000-0000-4000-8000-00000000f501'),
  ('00000000-0000-4000-8000-00000000f525', '00000000-0000-4000-8000-00000000f515', 1, 'Owner A Trashed Draft', 'Owner A trashed draft fixture.', '00000000-0000-4000-8000-00000000f501'),
  ('00000000-0000-4000-8000-00000000f526', '00000000-0000-4000-8000-00000000f516', 1, 'Owner A Trashed Changes', 'Owner A trashed changes fixture.', '00000000-0000-4000-8000-00000000f501'),
  ('00000000-0000-4000-8000-00000000f527', '00000000-0000-4000-8000-00000000f517', 1, 'Owner A Trashed Submitted', 'Owner A trashed submitted fixture.', '00000000-0000-4000-8000-00000000f501'),
  ('00000000-0000-4000-8000-00000000f528', '00000000-0000-4000-8000-00000000f518', 1, 'Owner B Draft', 'Owner B draft fixture.', '00000000-0000-4000-8000-00000000f502'),
  ('00000000-0000-4000-8000-00000000f529', '00000000-0000-4000-8000-00000000f519', 1, 'Owner B Trashed Draft', 'Owner B trashed draft fixture.', '00000000-0000-4000-8000-00000000f502'),
  ('00000000-0000-4000-8000-00000000f52a', '00000000-0000-4000-8000-00000000f51a', 1, 'Owner B Submitted', 'Owner B submitted fixture.', '00000000-0000-4000-8000-00000000f502'),
  ('00000000-0000-4000-8000-00000000f52b', '00000000-0000-4000-8000-00000000f51b', 1, 'Admin Draft', 'Admin draft fixture.', '00000000-0000-4000-8000-00000000f505');

update public.images i set current_version_id = versions.version_id
from (values
  ('00000000-0000-4000-8000-00000000f511'::uuid, '00000000-0000-4000-8000-00000000f521'::uuid),
  ('00000000-0000-4000-8000-00000000f512'::uuid, '00000000-0000-4000-8000-00000000f522'::uuid),
  ('00000000-0000-4000-8000-00000000f513'::uuid, '00000000-0000-4000-8000-00000000f523'::uuid),
  ('00000000-0000-4000-8000-00000000f514'::uuid, '00000000-0000-4000-8000-00000000f524'::uuid),
  ('00000000-0000-4000-8000-00000000f515'::uuid, '00000000-0000-4000-8000-00000000f525'::uuid),
  ('00000000-0000-4000-8000-00000000f516'::uuid, '00000000-0000-4000-8000-00000000f526'::uuid),
  ('00000000-0000-4000-8000-00000000f517'::uuid, '00000000-0000-4000-8000-00000000f527'::uuid),
  ('00000000-0000-4000-8000-00000000f518'::uuid, '00000000-0000-4000-8000-00000000f528'::uuid),
  ('00000000-0000-4000-8000-00000000f519'::uuid, '00000000-0000-4000-8000-00000000f529'::uuid),
  ('00000000-0000-4000-8000-00000000f51a'::uuid, '00000000-0000-4000-8000-00000000f52a'::uuid),
  ('00000000-0000-4000-8000-00000000f51b'::uuid, '00000000-0000-4000-8000-00000000f52b'::uuid)
) as versions(image_id, version_id)
where i.id = versions.image_id;

alter table public.image_assets disable trigger image_assets_enqueue_scan_job;
insert into public.image_assets (
  id, image_id, owner_user_id, kind, storage_key, mime_type, byte_size,
  width, height, checksum_sha256, scan_status, scan_result_code,
  scan_completed_at, scan_policy_version, storage_visibility
) values
  ('00000000-0000-4000-8000-00000000f541', '00000000-0000-4000-8000-00000000f511', '00000000-0000-4000-8000-00000000f501', 'thumbnail', '00000000-0000-4000-8000-00000000f501/dashboard/thumbnail.jpg', 'image/jpeg', 300, 400, 300, repeat('6', 64), 'clean', 'clean', now(), 'mt-asset-scan-2026-07-v1', 'private'),
  ('00000000-0000-4000-8000-00000000f542', '00000000-0000-4000-8000-00000000f511', '00000000-0000-4000-8000-00000000f501', 'original', '00000000-0000-4000-8000-00000000f501/dashboard/original.jpg', 'image/jpeg', 700, 1600, 1200, repeat('7', 64), 'pending', null, null, null, 'private'),
  ('00000000-0000-4000-8000-00000000f543', '00000000-0000-4000-8000-00000000f518', '00000000-0000-4000-8000-00000000f502', 'thumbnail', '00000000-0000-4000-8000-00000000f502/dashboard/thumbnail.jpg', 'image/jpeg', 200, 300, 400, repeat('8', 64), 'clean', 'clean', now(), 'mt-asset-scan-2026-07-v1', 'private');
alter table public.image_assets enable trigger image_assets_enqueue_scan_job;

insert into public.review_submissions (
  id, image_id, image_version_id, submitted_by_user_id, idempotency_key,
  status, policy_version, lock_version, readiness_snapshot, asset_snapshot
) values
  ('00000000-0000-4000-8000-00000000f531', '00000000-0000-4000-8000-00000000f513', '00000000-0000-4000-8000-00000000f523', '00000000-0000-4000-8000-00000000f501', '00000000-0000-4000-8000-00000000f551', 'submitted', 'mt-review-2026-07-v1', 1, '{"ready":true,"checks":[{},{},{},{},{}]}', '[{},{},{}]'),
  ('00000000-0000-4000-8000-00000000f532', '00000000-0000-4000-8000-00000000f51a', '00000000-0000-4000-8000-00000000f52a', '00000000-0000-4000-8000-00000000f502', '00000000-0000-4000-8000-00000000f552', 'submitted', 'mt-review-2026-07-v1', 1, '{"ready":true,"checks":[{},{},{},{},{}]}', '[{},{},{}]');

select pg_temp.set_dashboard_claims('00000000-0000-4000-8000-00000000f501');
set local role authenticated;
do $$
declare
  dashboard jsonb;
  trash jsonb;
  image jsonb;
begin
  dashboard := public.get_my_dashboard();
  if dashboard #>> '{status_counts,drafts}' <> '1'
     or dashboard #>> '{status_counts,submitted}' <> '1'
     or dashboard #>> '{status_counts,changes_requested}' <> '1'
     or dashboard #>> '{status_counts,published}' <> '1'
     or dashboard #>> '{status_counts,unpublished}' <> '1' then
    raise exception 'Owner A Dashboard status aggregate is incorrect';
  end if;
  if jsonb_array_length(dashboard -> 'needs_attention') <> 1
     or dashboard #>> '{needs_attention,0,image_id}' <> '00000000-0000-4000-8000-00000000f512'
     or dashboard #>> '{needs_attention,0,type}' <> 'changes_requested' then
    raise exception 'Owner A Dashboard attention aggregate is incorrect';
  end if;
  if jsonb_array_length(dashboard -> 'recent_images') <> 4
     or jsonb_array_length(dashboard -> 'drafts') <> 2
     or jsonb_array_length(dashboard -> 'review_activity') <> 1
     or dashboard #>> '{review_activity,0,submission_id}' <> '00000000-0000-4000-8000-00000000f531' then
    raise exception 'Owner A Dashboard list aggregates are incorrect';
  end if;
  if dashboard #>> '{storage_usage,used_bytes}' <> '1000'
     or dashboard #>> '{storage_usage,asset_count}' <> '2'
     or dashboard #>> '{storage_usage,image_count}' <> '1' then
    raise exception 'Owner A Dashboard storage aggregate is incorrect';
  end if;
  select entry into image
  from jsonb_array_elements(dashboard -> 'recent_images') entry
  where entry ->> 'id' = '00000000-0000-4000-8000-00000000f511';
  if image #>> '{thumbnail_asset,storage_key}'
       <> '00000000-0000-4000-8000-00000000f501/dashboard/thumbnail.jpg'
     or image #>> '{thumbnail_asset,scan_status}' <> 'clean'
     or image #>> '{thumbnail_asset,scan_policy_version}' <> 'mt-asset-scan-2026-07-v1' then
    raise exception 'Owner A Dashboard current-clean thumbnail projection is incorrect';
  end if;
  if dashboard::text like '%00000000-0000-4000-8000-00000000f502%'
     or dashboard::text like '%00000000-0000-4000-8000-00000000f518%'
     or dashboard::text like '%00000000-0000-4000-8000-00000000f519%'
     or dashboard::text like '%00000000-0000-4000-8000-00000000f51a%'
     or dashboard::text like '%00000000-0000-4000-8000-00000000f532%' then
    raise exception 'Owner A Dashboard contains Owner B data';
  end if;

  trash := public.workspace_list_trashed_drafts();
  if jsonb_array_length(trash -> 'images') <> 2
     or exists (
       select 1 from jsonb_array_elements(trash -> 'images') entry
       where entry ->> 'id' not in (
         '00000000-0000-4000-8000-00000000f515',
         '00000000-0000-4000-8000-00000000f516'
       )
         or entry ->> 'workflow_status' not in ('draft', 'changes_requested')
         or nullif(entry ->> 'deleted_at', '') is null
     ) then
    raise exception 'Owner A Trash returned an invalid owner/state set';
  end if;
  if trash::text like '%00000000-0000-4000-8000-00000000f517%'
     or trash::text like '%00000000-0000-4000-8000-00000000f519%' then
    raise exception 'Owner A Trash included submitted or cross-owner data';
  end if;
end
$$;
reset role;

select 'dashboard_database_aggregate=yes';
select 'workspace_trash_database_state_filter=yes';

select pg_temp.set_dashboard_claims('00000000-0000-4000-8000-00000000f502');
set local role authenticated;
do $$
declare
  dashboard jsonb;
  trash jsonb;
begin
  dashboard := public.get_my_dashboard();
  if dashboard #>> '{status_counts,drafts}' <> '1'
     or dashboard #>> '{status_counts,submitted}' <> '1'
     or jsonb_array_length(dashboard -> 'recent_images') <> 2
     or jsonb_array_length(dashboard -> 'review_activity') <> 1
     or dashboard #>> '{review_activity,0,submission_id}' <> '00000000-0000-4000-8000-00000000f532'
     or dashboard #>> '{storage_usage,used_bytes}' <> '200'
     or dashboard::text like '%00000000-0000-4000-8000-00000000f501%'
     or dashboard::text like '%00000000-0000-4000-8000-00000000f511%'
     or dashboard::text like '%00000000-0000-4000-8000-00000000f531%' then
    raise exception 'Owner B Dashboard is not owner isolated';
  end if;
  trash := public.workspace_list_trashed_drafts();
  if jsonb_array_length(trash -> 'images') <> 1
     or trash #>> '{images,0,id}' <> '00000000-0000-4000-8000-00000000f519'
     or nullif(trash #>> '{images,0,deleted_at}', '') is null
     or trash::text like '%00000000-0000-4000-8000-00000000f515%' then
    raise exception 'Owner B Trash is not owner isolated';
  end if;
end
$$;
reset role;

select 'dashboard_database_owner_isolation=yes';
select 'workspace_trash_database_owner_filter=yes';

select pg_temp.set_dashboard_claims('00000000-0000-4000-8000-00000000f503');
set local role authenticated;
do $$
begin
  begin
    perform public.get_my_dashboard();
    raise exception 'inactive account opened Dashboard';
  exception when sqlstate '42501' then
    null;
  end;
  begin
    perform public.workspace_list_trashed_drafts();
    raise exception 'inactive account opened Workspace Trash';
  exception when sqlstate '42501' then
    null;
  end;
end
$$;
reset role;

select pg_temp.set_dashboard_claims('00000000-0000-4000-8000-00000000f504', 'aal1', true);
set local role authenticated;
do $$
begin
  begin
    perform public.get_my_dashboard();
    raise exception 'recovery session opened Dashboard';
  exception when sqlstate '42501' then
    null;
  end;
  begin
    perform public.workspace_list_trashed_drafts();
    raise exception 'recovery session opened Workspace Trash';
  exception when sqlstate '42501' then
    null;
  end;
end
$$;
reset role;

select pg_temp.set_dashboard_claims('00000000-0000-4000-8000-00000000f505', 'aal1');
set local role authenticated;
do $$
begin
  begin
    perform public.get_my_dashboard();
    raise exception 'stacked Admin AAL1 opened Dashboard';
  exception when sqlstate '42501' then
    null;
  end;
  begin
    perform public.workspace_list_trashed_drafts();
    raise exception 'stacked Admin AAL1 opened Workspace Trash';
  exception when sqlstate '42501' then
    null;
  end;
end
$$;
reset role;

select pg_temp.set_dashboard_claims('00000000-0000-4000-8000-00000000f505', 'aal2');
set local role authenticated;
do $$
declare
  dashboard jsonb;
  trash jsonb;
begin
  dashboard := public.get_my_dashboard();
  trash := public.workspace_list_trashed_drafts();
  if dashboard #>> '{status_counts,drafts}' <> '1'
     or jsonb_array_length(dashboard -> 'recent_images') <> 1
     or dashboard #>> '{recent_images,0,id}' <> '00000000-0000-4000-8000-00000000f51b'
     or dashboard::text like '%00000000-0000-4000-8000-00000000f511%'
     or jsonb_array_length(trash -> 'images') <> 0 then
    raise exception 'Admin AAL2 did not receive only its owner-scoped Dashboard/Trash data';
  end if;
end
$$;
reset role;

select 'dashboard_database_identity_guards=yes';

rollback;
select 'dashboard_database_fixtures_rolled_back=yes';
"""


def load_dotenv() -> None:
    if not ENV_PATH.exists():
        return
    for raw_line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        os.environ.setdefault(name.strip(), value)


def require_development_environment() -> None:
    if os.environ.get("MT_TEST_ENVIRONMENT") != "development":
        raise RuntimeError(
            "Refusing Dashboard database fixtures without MT_TEST_ENVIRONMENT=development"
        )
    if os.environ.get("MT_ALLOW_PRODUCTION") == "yes":
        raise RuntimeError("Refusing Dashboard database fixtures while production approval is enabled")
    missing = [
        name
        for name in ("PGHOST", "PGDATABASE", "PGUSER", "PGPASSWORD")
        if not os.environ.get(name)
    ]
    if missing:
        raise RuntimeError(f"Missing required database environment variables: {', '.join(missing)}")


def psql_binary() -> str:
    found = shutil.which("psql")
    fallback = Path("/opt/homebrew/opt/libpq/bin/psql")
    if found:
        return found
    if fallback.exists():
        return str(fallback)
    raise RuntimeError("psql is required for the Dashboard database acceptance")


def psql_command() -> list[str]:
    return [
        psql_binary(),
        "--no-psqlrc",
        "--quiet",
        "--no-align",
        "--tuples-only",
        "--set",
        "ON_ERROR_STOP=1",
    ]


def redact_diagnostics(value: str) -> str:
    cleaned = value
    for name in (
        "PGPASSWORD",
        "SUPABASE_SECRET_KEY",
        "SUPABASE_SERVICE_ROLE_KEY",
        "SUPABASE_PUBLISHABLE_KEY",
    ):
        secret = os.environ.get(name, "")
        if secret:
            cleaned = cleaned.replace(secret, "[redacted]")
    return cleaned.strip()[-2400:]


def run_psql(sql: str) -> str:
    completed = subprocess.run(
        psql_command(),
        input=sql,
        cwd=ROOT,
        env=os.environ.copy(),
        capture_output=True,
        text=True,
        timeout=90,
        check=False,
    )
    if completed.returncode:
        detail = redact_diagnostics(completed.stderr)
        raise RuntimeError(
            "Dashboard database acceptance failed"
            + (f":\n{detail}" if detail else "")
        )
    return completed.stdout


def sql_values(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{value}'" for value in values)


def assert_fixtures_absent() -> None:
    fixture_count = run_psql(
        f"""
        select (
          (select count(*) from public.users where id in ({sql_values(USER_IDS)}))
          + (select count(*) from public.user_profiles where user_id in ({sql_values(USER_IDS)}))
          + (select count(*) from public.user_roles where user_id in ({sql_values(USER_IDS)}))
          + (select count(*) from public.folders where owner_user_id in ({sql_values(USER_IDS)}))
          + (select count(*) from public.images where id in ({sql_values(IMAGE_IDS)}))
          + (select count(*) from public.image_versions
             where image_id in ({sql_values(IMAGE_IDS)}))
          + (select count(*) from public.image_assets
             where image_id in ({sql_values(IMAGE_IDS)}))
          + (select count(*) from public.review_submissions
             where image_id in ({sql_values(IMAGE_IDS)}))
        );
        """
    ).strip()
    if fixture_count != "0":
        raise RuntimeError("Dashboard database fixture UUIDs remain after rollback")


def main() -> None:
    load_dotenv()
    require_development_environment()
    output = run_psql(SQL)
    lines = {line.strip() for line in output.splitlines() if line.strip()}
    missing = [marker for marker in EXPECTED_MARKERS if marker not in lines]
    if missing:
        raise RuntimeError(f"Dashboard database markers are missing: {', '.join(missing)}")
    assert_fixtures_absent()
    for marker in EXPECTED_MARKERS:
        print(marker)
    print("dashboard_database_fixtures_absent=yes")


if __name__ == "__main__":
    main()
