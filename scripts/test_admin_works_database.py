#!/usr/bin/env python3
"""Development-only, rollback-only Admin Works governance acceptance."""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess


ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT / ".env"

USER_IDS = tuple(
    f"00000000-0000-4000-8000-00000000f7{suffix}"
    for suffix in ("01", "02", "03", "04", "05", "06")
)
FOLDER_IDS = tuple(
    f"00000000-0000-4000-8000-00000000f7{suffix}"
    for suffix in ("11", "12", "13", "14", "15")
)
IMAGE_IDS = tuple(
    f"00000000-0000-4000-8000-00000000f7{suffix}"
    for suffix in ("21", "22", "23", "24")
)
ASSET_IDS = tuple(
    f"00000000-0000-4000-8000-00000000f7{suffix}"
    for suffix in ("41", "42", "43", "44", "45", "46", "47", "48", "49")
)
OBJECT_IDS = tuple(
    f"00000000-0000-4000-8000-00000000f7{suffix}"
    for suffix in ("51", "52", "53", "54", "55", "56", "57", "58", "59")
)
REVIEW_SUBMISSION_IDS = ("00000000-0000-4000-8000-00000000f771",)
REVIEW_DECISION_IDS = ("00000000-0000-4000-8000-00000000f773",)

EXPECTED_MARKERS = (
    "admin_works_database_pg_proc_security=yes",
    "admin_works_database_acl_boundary=yes",
    "admin_works_database_role_boundary=yes",
    "admin_works_database_storage_rls=yes",
    "admin_works_database_list_detail=yes",
    "admin_works_database_unpublish_restore=yes",
    "admin_works_database_idempotency_cas=yes",
    "admin_works_database_takedown_legal_hold=yes",
    "admin_works_database_restore_asset_gate=yes",
    "admin_works_database_failure_audit=yes",
    "admin_works_database_append_only=yes",
    "admin_works_database_fixtures_rolled_back=yes",
)


SQL = r"""
\set ON_ERROR_STOP on

begin;
select pg_advisory_xact_lock(hashtextextended('mt-admin-works-database-test', 0));

do $$
declare
  proc_row record;
  authenticated_role oid := (select oid from pg_roles where rolname = 'authenticated');
begin
  if authenticated_role is null
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
        'public.admin_list_images(text,text,text,integer,integer)'::regprocedure,
        'public.admin_get_image(uuid)'::regprocedure,
        'public.admin_govern_image(uuid,integer,text,text,text,text,uuid)'::regprocedure,
        'public.can_read_admin_work_storage_object(uuid,text,text,text)'::regprocedure,
        'public.can_read_review_storage_object(text,text,text)'::regprocedure
      ) as allow_authenticated
    from pg_proc p
    where p.oid in (
      'public.admin_require_governance_actor()'::regprocedure,
      'public.admin_governance_actor_role(uuid)'::regprocedure,
      'public.admin_governance_failure_result(uuid,public.role_code,uuid,text,text,integer,uuid,text,text)'::regprocedure,
      'public.can_read_admin_work_storage_object(uuid,text,text,text)'::regprocedure,
      'public.can_read_review_storage_object(text,text,text)'::regprocedure,
      'public.admin_image_asset_json(uuid)'::regprocedure,
      'public.admin_image_summary_json(uuid)'::regprocedure,
      'public.admin_list_images(text,text,text,integer,integer)'::regprocedure,
      'public.admin_get_image(uuid)'::regprocedure,
      'public.admin_governance_action_result(uuid,boolean)'::regprocedure,
      'public.admin_govern_image(uuid,integer,text,text,text,text,uuid)'::regprocedure
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
          case when proc_row.allow_authenticated
            then authenticated_role else proc_row.proowner end
        )
    ) then
      raise exception '% grants EXECUTE outside its exact allowlist', proc_row.identity;
    end if;
  end loop;

  if (select count(*) from pg_proc p where p.oid in (
    'public.admin_require_governance_actor()'::regprocedure,
    'public.admin_governance_actor_role(uuid)'::regprocedure,
    'public.admin_governance_failure_result(uuid,public.role_code,uuid,text,text,integer,uuid,text,text)'::regprocedure,
    'public.can_read_admin_work_storage_object(uuid,text,text,text)'::regprocedure,
    'public.can_read_review_storage_object(text,text,text)'::regprocedure,
    'public.admin_image_asset_json(uuid)'::regprocedure,
    'public.admin_image_summary_json(uuid)'::regprocedure,
    'public.admin_list_images(text,text,text,integer,integer)'::regprocedure,
    'public.admin_get_image(uuid)'::regprocedure,
    'public.admin_governance_action_result(uuid,boolean)'::regprocedure,
    'public.admin_govern_image(uuid,integer,text,text,text,text,uuid)'::regprocedure
  )) <> 11 then
    raise exception 'Admin Works function metadata is incomplete';
  end if;
  if has_function_privilege(
       'authenticated',
       'public.admin_governance_error(text,text)',
       'EXECUTE'
     ) then
    raise exception 'authenticated can execute the private error helper';
  end if;
end
$$;

select 'admin_works_database_pg_proc_security=yes';

do $$
begin
  if has_table_privilege('anon', 'public.image_governance_actions', 'SELECT')
     or has_table_privilege('authenticated', 'public.image_governance_actions', 'SELECT')
     or has_table_privilege('authenticated', 'public.image_governance_actions', 'INSERT')
     or has_table_privilege('authenticated', 'public.image_governance_actions', 'UPDATE')
     or has_table_privilege('authenticated', 'public.image_governance_actions', 'DELETE')
     or has_table_privilege('service_role', 'public.image_governance_actions', 'SELECT')
     or has_table_privilege('authenticated', 'public.takedown_cases', 'INSERT')
     or has_table_privilege('authenticated', 'public.takedown_cases', 'UPDATE')
     or has_table_privilege('authenticated', 'public.takedown_cases', 'DELETE') then
    raise exception 'Admin Works tables expose direct governance access';
  end if;
  if not exists (
    select 1 from pg_trigger
    where tgrelid = 'public.image_governance_actions'::regclass
      and tgname = 'image_governance_actions_append_only'
      and not tgisinternal
  ) then
    raise exception 'image_governance_actions append-only trigger is missing';
  end if;
  if not exists (
    select 1
    from pg_policies policy
    where policy.schemaname = 'storage'
      and policy.tablename = 'objects'
      and policy.policyname = 'admin_work_storage_objects_select'
      and policy.cmd = 'SELECT'
      and policy.roles = array['authenticated'::name]
      and position('can_read_admin_work_storage_object' in policy.qual) > 0
  ) then
    raise exception 'Admin Works Storage SELECT policy is missing or over-broad';
  end if;
  if not exists (
    select 1
    from pg_policies policy
    where policy.schemaname = 'storage'
      and policy.tablename = 'objects'
      and policy.policyname = 'review_storage_objects_select'
      and policy.cmd = 'SELECT'
      and policy.roles = array['authenticated'::name]
      and position('can_read_review_storage_object' in policy.qual) > 0
  ) then
    raise exception 'Review Storage policy is missing or over-broad';
  end if;
end
$$;

set local role anon;
do $$
begin
  begin
    perform public.admin_list_images('all', '', 'updated_desc', 30, 0);
    raise exception 'anon executed admin_list_images';
  exception when insufficient_privilege then null;
  end;
  begin
    perform public.admin_get_image('00000000-0000-4000-8000-00000000f721');
    raise exception 'anon executed admin_get_image';
  exception when insufficient_privilege then null;
  end;
  begin
    perform public.admin_govern_image(
      '00000000-0000-4000-8000-00000000f721', 1, 'unpublish',
      'privacy', 'Privacy review required.', null,
      '00000000-0000-4000-8000-00000000f761'
    );
    raise exception 'anon executed admin_govern_image';
  exception when insufficient_privilege then null;
  end;
end
$$;
reset role;

set local role service_role;
do $$
begin
  begin
    perform public.admin_list_images('all', '', 'updated_desc', 30, 0);
    raise exception 'service_role executed admin_list_images';
  exception when insufficient_privilege then null;
  end;
  begin
    perform public.admin_get_image('00000000-0000-4000-8000-00000000f721');
    raise exception 'service_role executed admin_get_image';
  exception when insufficient_privilege then null;
  end;
end
$$;
reset role;

select 'admin_works_database_acl_boundary=yes';

do $$
begin
  if exists (
    select 1 from public.users
    where id between '00000000-0000-4000-8000-00000000f701'::uuid
      and '00000000-0000-4000-8000-00000000f706'::uuid
  ) or exists (
    select 1 from public.folders
    where id between '00000000-0000-4000-8000-00000000f711'::uuid
      and '00000000-0000-4000-8000-00000000f715'::uuid
  ) or exists (
    select 1 from public.images
    where id between '00000000-0000-4000-8000-00000000f721'::uuid
      and '00000000-0000-4000-8000-00000000f724'::uuid
  ) or exists (
    select 1 from storage.objects
    where id between '00000000-0000-4000-8000-00000000f751'::uuid
      and '00000000-0000-4000-8000-00000000f759'::uuid
  ) or exists (
    select 1 from public.review_submissions
    where id = '00000000-0000-4000-8000-00000000f771'
  ) or exists (
    select 1 from public.review_decisions
    where id = '00000000-0000-4000-8000-00000000f773'
  ) then
    raise exception 'fixed Admin Works fixtures already exist';
  end if;
end
$$;

create function pg_temp.set_admin_works_claims(
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
  ('00000000-0000-4000-8000-00000000f701', '00000000-0000-4000-8000-00000000f701', 'governance-owner@example.test', now(), 'active'),
  ('00000000-0000-4000-8000-00000000f702', '00000000-0000-4000-8000-00000000f702', 'governance-admin@example.test', now(), 'active'),
  ('00000000-0000-4000-8000-00000000f703', '00000000-0000-4000-8000-00000000f703', 'governance-super@example.test', now(), 'active'),
  ('00000000-0000-4000-8000-00000000f704', '00000000-0000-4000-8000-00000000f704', 'governance-reviewer@example.test', now(), 'active'),
  ('00000000-0000-4000-8000-00000000f705', '00000000-0000-4000-8000-00000000f705', 'governance-inactive@example.test', now(), 'suspended'),
  ('00000000-0000-4000-8000-00000000f706', '00000000-0000-4000-8000-00000000f706', 'governance-other-user@example.test', now(), 'active');

insert into public.user_profiles (user_id, display_name, public_slug) values
  ('00000000-0000-4000-8000-00000000f701', 'Governance Owner', 'governance-owner'),
  ('00000000-0000-4000-8000-00000000f702', 'Governance Admin', 'governance-admin'),
  ('00000000-0000-4000-8000-00000000f703', 'Governance Super', 'governance-super'),
  ('00000000-0000-4000-8000-00000000f704', 'Governance Reviewer', 'governance-reviewer'),
  ('00000000-0000-4000-8000-00000000f705', 'Governance Inactive', 'governance-inactive'),
  ('00000000-0000-4000-8000-00000000f706', 'Governance Other User', 'governance-other-user');

insert into public.user_roles (user_id, role, reason) values
  ('00000000-0000-4000-8000-00000000f701', 'user', 'Admin Works test owner'),
  ('00000000-0000-4000-8000-00000000f702', 'user', 'Admin Works test administrator'),
  ('00000000-0000-4000-8000-00000000f702', 'admin', 'Admin Works test administrator'),
  ('00000000-0000-4000-8000-00000000f703', 'super_admin', 'Admin Works test super administrator'),
  ('00000000-0000-4000-8000-00000000f704', 'reviewer', 'Admin Works test reviewer'),
  ('00000000-0000-4000-8000-00000000f705', 'admin', 'Admin Works test inactive administrator'),
  ('00000000-0000-4000-8000-00000000f706', 'user', 'Admin Works test cross-owner user');

insert into public.folders (id, owner_user_id, name, sort_order, is_system) values
  ('00000000-0000-4000-8000-00000000f711', '00000000-0000-4000-8000-00000000f701', 'Inbox', 0, true),
  ('00000000-0000-4000-8000-00000000f712', '00000000-0000-4000-8000-00000000f702', 'Inbox', 0, true),
  ('00000000-0000-4000-8000-00000000f713', '00000000-0000-4000-8000-00000000f703', 'Inbox', 0, true),
  ('00000000-0000-4000-8000-00000000f714', '00000000-0000-4000-8000-00000000f704', 'Inbox', 0, true),
  ('00000000-0000-4000-8000-00000000f715', '00000000-0000-4000-8000-00000000f705', 'Inbox', 0, true);

insert into public.images (
  id, owner_user_id, processing_status, workflow_status, publication_status,
  original_filename, original_width, original_height, checksum_sha256,
  version, published_at, unpublished_at, updated_at
) values
  ('00000000-0000-4000-8000-00000000f721', '00000000-0000-4000-8000-00000000f701', 'ready', 'approved', 'published', 'owner-public-original.jpg', 1800, 1200, repeat('1', 64), 1, now() - interval '3 days', null, now() - interval '1 hour'),
  ('00000000-0000-4000-8000-00000000f722', '00000000-0000-4000-8000-00000000f702', 'ready', 'approved', 'published', 'admin-public-original.jpg', 1200, 1800, repeat('2', 64), 1, now() - interval '2 days', null, now() - interval '2 hours'),
  ('00000000-0000-4000-8000-00000000f723', '00000000-0000-4000-8000-00000000f701', 'ready', 'approved', 'unpublished', 'dirty-unpublished-original.jpg', 1600, 1200, repeat('3', 64), 1, now() - interval '4 days', now() - interval '1 day', now() - interval '3 hours'),
  ('00000000-0000-4000-8000-00000000f724', '00000000-0000-4000-8000-00000000f701', 'ready', 'draft', 'never_published', 'never-published.jpg', 1000, 1000, repeat('4', 64), 1, null, null, now() - interval '4 hours');

insert into public.image_versions (
  id, image_id, version_number, title, caption, description, alt_text, tags,
  content_category, gps_visibility, public_exif, rights_declared,
  created_by_user_id, locked_at
) values
  ('00000000-0000-4000-8000-00000000f731', '00000000-0000-4000-8000-00000000f721', 1, 'Owner public work', 'Caption', 'Description', 'Owner work', '["governance"]', 'concrete', 'private', '{"camera":"Fixture"}', true, '00000000-0000-4000-8000-00000000f701', now()),
  ('00000000-0000-4000-8000-00000000f732', '00000000-0000-4000-8000-00000000f722', 1, 'Admin public work', 'Caption', 'Description', 'Admin work', '["governance"]', 'abstract', 'private', '{}', true, '00000000-0000-4000-8000-00000000f702', now()),
  ('00000000-0000-4000-8000-00000000f733', '00000000-0000-4000-8000-00000000f723', 1, 'Dirty unpublished work', '', '', 'Dirty work', '[]', 'concrete', 'private', '{}', true, '00000000-0000-4000-8000-00000000f701', now()),
  ('00000000-0000-4000-8000-00000000f734', '00000000-0000-4000-8000-00000000f724', 1, 'Never published work', '', '', '', '[]', 'concrete', 'private', '{}', false, '00000000-0000-4000-8000-00000000f701', null);

update public.images set current_version_id = case id
  when '00000000-0000-4000-8000-00000000f721' then '00000000-0000-4000-8000-00000000f731'::uuid
  when '00000000-0000-4000-8000-00000000f722' then '00000000-0000-4000-8000-00000000f732'::uuid
  when '00000000-0000-4000-8000-00000000f723' then '00000000-0000-4000-8000-00000000f733'::uuid
  else '00000000-0000-4000-8000-00000000f734'::uuid
end
where id between '00000000-0000-4000-8000-00000000f721'::uuid
  and '00000000-0000-4000-8000-00000000f724'::uuid;

create temporary table admin_works_fixture_assets (
  object_id uuid primary key,
  asset_id uuid not null unique,
  image_id uuid not null,
  owner_id uuid not null,
  kind text not null,
  bucket text not null,
  storage_key text not null,
  byte_size bigint not null,
  width integer not null,
  height integer not null,
  checksum char(64) not null,
  visibility text not null
) on commit drop;

insert into admin_works_fixture_assets values
  ('00000000-0000-4000-8000-00000000f751', '00000000-0000-4000-8000-00000000f741', '00000000-0000-4000-8000-00000000f721', '00000000-0000-4000-8000-00000000f701', 'original', 'image-originals', '00000000-0000-4000-8000-00000000f701/00000000-0000-4000-8000-00000000f721/original.jpg', 3000, 1800, 1200, repeat('1', 64), 'private'),
  ('00000000-0000-4000-8000-00000000f752', '00000000-0000-4000-8000-00000000f742', '00000000-0000-4000-8000-00000000f721', '00000000-0000-4000-8000-00000000f701', 'display', 'image-display', '00000000-0000-4000-8000-00000000f701/00000000-0000-4000-8000-00000000f721/display.jpg', 1800, 1800, 1200, repeat('2', 64), 'public'),
  ('00000000-0000-4000-8000-00000000f753', '00000000-0000-4000-8000-00000000f743', '00000000-0000-4000-8000-00000000f721', '00000000-0000-4000-8000-00000000f701', 'thumbnail', 'image-thumbnails', '00000000-0000-4000-8000-00000000f701/00000000-0000-4000-8000-00000000f721/thumbnail.jpg', 600, 600, 400, repeat('3', 64), 'public'),
  ('00000000-0000-4000-8000-00000000f754', '00000000-0000-4000-8000-00000000f744', '00000000-0000-4000-8000-00000000f722', '00000000-0000-4000-8000-00000000f702', 'original', 'image-originals', '00000000-0000-4000-8000-00000000f702/00000000-0000-4000-8000-00000000f722/original.jpg', 3000, 1200, 1800, repeat('4', 64), 'private'),
  ('00000000-0000-4000-8000-00000000f755', '00000000-0000-4000-8000-00000000f745', '00000000-0000-4000-8000-00000000f722', '00000000-0000-4000-8000-00000000f702', 'display', 'image-display', '00000000-0000-4000-8000-00000000f702/00000000-0000-4000-8000-00000000f722/display.jpg', 1800, 1200, 1800, repeat('5', 64), 'public'),
  ('00000000-0000-4000-8000-00000000f756', '00000000-0000-4000-8000-00000000f746', '00000000-0000-4000-8000-00000000f722', '00000000-0000-4000-8000-00000000f702', 'thumbnail', 'image-thumbnails', '00000000-0000-4000-8000-00000000f702/00000000-0000-4000-8000-00000000f722/thumbnail.jpg', 600, 400, 600, repeat('6', 64), 'public'),
  ('00000000-0000-4000-8000-00000000f757', '00000000-0000-4000-8000-00000000f747', '00000000-0000-4000-8000-00000000f723', '00000000-0000-4000-8000-00000000f701', 'original', 'image-originals', '00000000-0000-4000-8000-00000000f701/00000000-0000-4000-8000-00000000f723/original.jpg', 3000, 1600, 1200, repeat('7', 64), 'private'),
  ('00000000-0000-4000-8000-00000000f758', '00000000-0000-4000-8000-00000000f748', '00000000-0000-4000-8000-00000000f723', '00000000-0000-4000-8000-00000000f701', 'display', 'image-display', '00000000-0000-4000-8000-00000000f701/00000000-0000-4000-8000-00000000f723/display.jpg', 1800, 1600, 1200, repeat('8', 64), 'private'),
  ('00000000-0000-4000-8000-00000000f759', '00000000-0000-4000-8000-00000000f749', '00000000-0000-4000-8000-00000000f723', '00000000-0000-4000-8000-00000000f701', 'thumbnail', 'image-thumbnails', '00000000-0000-4000-8000-00000000f701/00000000-0000-4000-8000-00000000f723/thumbnail.jpg', 600, 600, 450, repeat('9', 64), 'private');

insert into storage.objects (id, bucket_id, name, owner_id, metadata)
select object_id, bucket, storage_key, owner_id::text,
       jsonb_build_object('mimetype', 'image/jpeg', 'size', byte_size)
from admin_works_fixture_assets;

insert into public.image_assets (
  id, image_id, owner_user_id, kind, storage_key, mime_type, byte_size,
  width, height, checksum_sha256, storage_visibility
)
select asset_id, image_id, owner_id, kind, storage_key, 'image/jpeg', byte_size,
       width, height, checksum, visibility
from admin_works_fixture_assets;

update public.asset_scan_jobs job set
  status = 'clean',
  attempt_count = 1,
  scanner_version = 'admin-works-fixture',
  engine_name = 'fixture',
  engine_version = '1',
  result_code = 'clean',
  result_details = '{"fixture":true}'::jsonb,
  completed_at = now()
where job.asset_id in (
  select asset_id from admin_works_fixture_assets
  where asset_id <> '00000000-0000-4000-8000-00000000f748'
);

update public.image_assets asset set
  scan_status = 'clean',
  scan_result_code = 'clean',
  scan_completed_at = now(),
  scan_policy_version = 'mt-asset-scan-2026-07-v1'
where asset.id in (
  select asset_id from admin_works_fixture_assets
  where asset_id <> '00000000-0000-4000-8000-00000000f748'
);

set local role authenticated;

select pg_temp.set_admin_works_claims('00000000-0000-4000-8000-00000000f706', 'aal2');
do $$
begin
  begin
    perform public.admin_list_images('all', '', 'updated_desc', 30, 0);
    raise exception 'ordinary user accessed Admin Works';
  exception when sqlstate '42501' then null;
  end;
end
$$;

select pg_temp.set_admin_works_claims('00000000-0000-4000-8000-00000000f704', 'aal2');
do $$
begin
  begin
    perform public.admin_get_image('00000000-0000-4000-8000-00000000f721');
    raise exception 'reviewer accessed Admin Works';
  exception when sqlstate '42501' then null;
  end;
end
$$;

select pg_temp.set_admin_works_claims('00000000-0000-4000-8000-00000000f702', 'aal1');
do $$
begin
  begin
    perform public.admin_list_images('all', '', 'updated_desc', 30, 0);
    raise exception 'AAL1 administrator accessed Admin Works';
  exception when sqlstate '42501' then null;
  end;
end
$$;

select pg_temp.set_admin_works_claims('00000000-0000-4000-8000-00000000f702', 'aal2', true);
do $$
begin
  begin
    perform public.admin_list_images('all', '', 'updated_desc', 30, 0);
    raise exception 'recovery administrator accessed Admin Works';
  exception when sqlstate '42501' then null;
  end;
end
$$;

select pg_temp.set_admin_works_claims('00000000-0000-4000-8000-00000000f705', 'aal2');
do $$
begin
  begin
    perform public.admin_list_images('all', '', 'updated_desc', 30, 0);
    raise exception 'inactive administrator accessed Admin Works';
  exception when sqlstate '42501' then null;
  end;
end
$$;

select pg_temp.set_admin_works_claims('00000000-0000-4000-8000-00000000f703', 'aal2');
do $$
begin
  if public.admin_list_images('all', '', 'updated_desc', 1, 0)
       #>> '{actor,id}' <> '00000000-0000-4000-8000-00000000f703' then
    raise exception 'AAL2 Super Admin could not access Admin Works';
  end if;
end
$$;

select 'admin_works_database_role_boundary=yes';

reset role;
select pg_temp.set_admin_works_claims('00000000-0000-4000-8000-00000000f702', 'aal2');
do $$
declare
  list_result jsonb;
  search_result jsonb;
  page_result jsonb;
  detail_result jsonb;
begin
  list_result := public.admin_list_images(
    'all', '00000000-0000-4000-8000-00000000f7', 'updated_desc', 30, 0
  );
  if jsonb_array_length(list_result -> 'items') <> 4
     or (list_result #>> '{counts,all}')::integer <> 4
     or (list_result #>> '{counts,published}')::integer <> 2
     or (list_result #>> '{counts,unpublished}')::integer <> 1
     or (list_result #>> '{counts,never_published}')::integer <> 1
     or (list_result #>> '{pagination,total}')::integer <> 4
     or (list_result #>> '{pagination,has_more}')::boolean then
    raise exception 'Admin Works list/count/pagination DTO is invalid: %', list_result;
  end if;

  search_result := public.admin_list_images('all', 'Owner public work', 'title_asc', 30, 0);
  if jsonb_array_length(search_result -> 'items') <> 1
     or search_result #>> '{items,0,id}' <> '00000000-0000-4000-8000-00000000f721' then
    raise exception 'Admin Works search is invalid: %', search_result;
  end if;

  page_result := public.admin_list_images(
    'all', '00000000-0000-4000-8000-00000000f7', 'updated_desc', 1, 0
  );
  if jsonb_array_length(page_result -> 'items') <> 1
     or not (page_result #>> '{pagination,has_more}')::boolean then
    raise exception 'Admin Works bounded pagination is invalid: %', page_result;
  end if;

  detail_result := public.admin_get_image('00000000-0000-4000-8000-00000000f721');
  if detail_result #>> '{work,id}' <> '00000000-0000-4000-8000-00000000f721'
     or detail_result #>> '{work,current_version,title}' <> 'Owner public work'
     or detail_result #>> '{work,current_version,image_id}' <> '00000000-0000-4000-8000-00000000f721'
     or detail_result #>> '{work,versions,0,image_id}' <> '00000000-0000-4000-8000-00000000f721'
     or detail_result #>> '{work,display_asset,kind}' <> 'display'
     or detail_result #>> '{work,thumbnail_asset,kind}' <> 'thumbnail'
     or (detail_result -> 'work') ? 'original_asset'
     or position('internal_note' in detail_result::text) > 0 then
    raise exception 'Admin Works detail DTO is invalid: %', detail_result;
  end if;

  if public.admin_list_images('all', '', 'updated_desc', 51, 0)
       #>> '{error,code}' <> 'ADMIN_FILTER_INVALID' then
    raise exception 'Admin Works accepted an oversized page';
  end if;
end
$$;

select 'admin_works_database_list_detail=yes';

do $$
declare
  before_public jsonb;
  unpublish_result jsonb;
  replay_result jsonb;
  conflict_result jsonb;
  stale_result jsonb;
  governed_detail jsonb;
begin
  before_public := public.get_public_works('governance-owner', 100, 0);
  if (before_public ->> 'count')::integer <> 1 then
    raise exception 'published fixture was not public before governance: %', before_public;
  end if;

  unpublish_result := public.admin_govern_image(
    '00000000-0000-4000-8000-00000000f721',
    1,
    'unpublish',
    'privacy',
    'This work is unavailable during a privacy review.',
    'private operational note',
    '00000000-0000-4000-8000-00000000f761'
  );
  if (unpublish_result #>> '{replayed}')::boolean
     or unpublish_result #>> '{action,action}' <> 'unpublish'
     or unpublish_result #>> '{action,image_id}' <> '00000000-0000-4000-8000-00000000f721'
     or unpublish_result #>> '{action,actor_user_id}' <> '00000000-0000-4000-8000-00000000f702'
     or unpublish_result #>> '{action,actor_role}' <> 'admin'
     or unpublish_result #>> '{action,policy_version}' <> 'mt-admin-governance-2026-07-v1'
     or (unpublish_result #>> '{action,expected_image_version}')::integer <> 1
     or unpublish_result #>> '{work,latest_governance_action,image_id}' <> '00000000-0000-4000-8000-00000000f721'
     or unpublish_result #>> '{work,latest_governance_action,actor_role}' <> 'admin'
     or unpublish_result #>> '{work,latest_governance_action,policy_version}' <> 'mt-admin-governance-2026-07-v1'
     or unpublish_result #>> '{work,publication_status}' <> 'unpublished'
     or (unpublish_result #>> '{work,version}')::integer <> 2
     or unpublish_result #>> '{takedown,image_id}' <> '00000000-0000-4000-8000-00000000f721'
     or unpublish_result #>> '{action,takedown_case_id}' <> unpublish_result #>> '{takedown,id}'
     or unpublish_result #>> '{takedown,status}' <> 'unpublished'
     or position('private operational note' in unpublish_result::text) > 0 then
    raise exception 'unpublish result is invalid: %', unpublish_result;
  end if;
  if public.public_delivery_work_json('00000000-0000-4000-8000-00000000f721') is not null
     or exists (
       select 1 from public.image_assets a
       where a.image_id = '00000000-0000-4000-8000-00000000f721'
         and a.storage_visibility <> 'private'
     ) then
    raise exception 'unpublished image or derivative remains public';
  end if;
  if (select count(*) from public.image_governance_actions a
      where a.image_id = '00000000-0000-4000-8000-00000000f721') <> 1
     or (select count(*) from public.notifications n
         where n.payload ->> 'image_id' = '00000000-0000-4000-8000-00000000f721') <> 1
     or (select count(*) from public.audit_logs l
         where l.target_type = 'image'
           and l.target_id = '00000000-0000-4000-8000-00000000f721') <> 1 then
    raise exception 'unpublish did not create exactly one action, notification, and audit';
  end if;
  governed_detail := public.admin_get_image('00000000-0000-4000-8000-00000000f721');
  if governed_detail #>> '{work,governance_actions,0,image_id}'
       <> '00000000-0000-4000-8000-00000000f721'
     or governed_detail #>> '{work,governance_actions,0,actor_role}' <> 'admin'
     or governed_detail #>> '{work,governance_actions,0,policy_version}'
       <> 'mt-admin-governance-2026-07-v1'
     or (governed_detail -> 'work') ? 'original_asset' then
    raise exception 'governance detail locator boundary is invalid: %', governed_detail;
  end if;

  replay_result := public.admin_govern_image(
    '00000000-0000-4000-8000-00000000f721',
    1,
    'unpublish',
    'privacy',
    'This work is unavailable during a privacy review.',
    'private operational note',
    '00000000-0000-4000-8000-00000000f761'
  );
  if not (replay_result #>> '{replayed}')::boolean
     or replay_result #>> '{action,id}' <> unpublish_result #>> '{action,id}'
     or (select version from public.images
         where id = '00000000-0000-4000-8000-00000000f721') <> 2 then
    raise exception 'same-payload idempotency replay is invalid: %', replay_result;
  end if;

  conflict_result := public.admin_govern_image(
    '00000000-0000-4000-8000-00000000f721',
    2,
    'unpublish',
    'privacy',
    'This work is unavailable during a privacy review.',
    'private operational note',
    '00000000-0000-4000-8000-00000000f761'
  );
  if conflict_result #>> '{error,code}' <> 'ADMIN_GOVERNANCE_IDEMPOTENCY_CONFLICT' then
    raise exception 'different-payload idempotency conflict was accepted: %', conflict_result;
  end if;

  stale_result := public.admin_govern_image(
    '00000000-0000-4000-8000-00000000f721',
    1,
    'restore',
    'investigation_cleared',
    'The privacy review is complete and this work is restored.',
    null,
    '00000000-0000-4000-8000-00000000f762'
  );
  if stale_result #>> '{error,code}' <> 'ADMIN_IMAGE_VERSION_CONFLICT' then
    raise exception 'stale governance CAS was accepted: %', stale_result;
  end if;
  if not exists (
    select 1
    from public.audit_logs failure_log
    where failure_log.action = 'admin.image.governance_failed'
      and failure_log.target_type = 'image'
      and failure_log.target_id = '00000000-0000-4000-8000-00000000f721'
      and failure_log.request_id = '00000000-0000-4000-8000-00000000f762'
      and failure_log.result = 'failure'
      and failure_log.before_state is null
      and failure_log.after_state #>> '{error_code}' = 'ADMIN_IMAGE_VERSION_CONFLICT'
      and failure_log.after_state #>> '{action}' = 'restore'
      and failure_log.after_state #>> '{reason_code}' = 'investigation_cleared'
      and (failure_log.after_state #>> '{expected_version}')::integer = 1
      and (failure_log.after_state #>> '{current_version}')::integer = 2
      and failure_log.after_state #>> '{policy_version}' = 'mt-admin-governance-2026-07-v1'
      and (
        select count(*) from jsonb_object_keys(failure_log.after_state)
      ) = 7
  ) then
    raise exception 'CAS conflict did not write the controlled failure audit';
  end if;
  if exists (
    select 1
    from public.audit_logs failure_log
    where failure_log.action = 'admin.image.governance_failed'
      and (
        failure_log.after_state::text ilike '%private operational note%'
        or failure_log.after_state::text ilike '%this work is unavailable%'
        or failure_log.after_state ?| array['user_message', 'internal_note', 'token']
      )
  ) then
    raise exception 'governance failure audit contains sensitive request data';
  end if;
end
$$;

-- The image is now unpublished, so neither public delivery nor the Review
-- policy can make these objects visible. This isolates the Admin Works policy.
do $$
begin
  if exists (
    select 1 from public.review_submissions submission
    where submission.image_id = '00000000-0000-4000-8000-00000000f721'
  ) then
    raise exception 'Storage boundary fixture unexpectedly has a review submission';
  end if;
end
$$;

set local role authenticated;
select pg_temp.set_admin_works_claims('00000000-0000-4000-8000-00000000f702', 'aal2');
do $$
begin
  if (select count(*) from storage.objects object_row
      where object_row.id in (
        '00000000-0000-4000-8000-00000000f752',
        '00000000-0000-4000-8000-00000000f753'
      )) <> 2
     or exists (
       select 1 from storage.objects object_row
       where object_row.id in (
         '00000000-0000-4000-8000-00000000f751',
         '00000000-0000-4000-8000-00000000f758'
       )
     ) then
    raise exception 'AAL2 Admin Storage scope is not clean derivative-only';
  end if;
end
$$;

select pg_temp.set_admin_works_claims('00000000-0000-4000-8000-00000000f703', 'aal2');
do $$
begin
  if (select count(*) from storage.objects object_row
      where object_row.id in (
        '00000000-0000-4000-8000-00000000f752',
        '00000000-0000-4000-8000-00000000f753'
      )) <> 2 then
    raise exception 'AAL2 Super Admin cannot read clean cross-owner derivatives';
  end if;
end
$$;

select pg_temp.set_admin_works_claims('00000000-0000-4000-8000-00000000f706', 'aal2');
do $$
begin
  if exists (
    select 1 from storage.objects object_row
    where object_row.id in (
      '00000000-0000-4000-8000-00000000f752',
      '00000000-0000-4000-8000-00000000f753'
    )
  ) then
    raise exception 'ordinary user crossed the Admin Works Storage policy';
  end if;
end
$$;

select pg_temp.set_admin_works_claims('00000000-0000-4000-8000-00000000f704', 'aal2');
do $$
begin
  if exists (
    select 1 from storage.objects object_row
    where object_row.id in (
      '00000000-0000-4000-8000-00000000f752',
      '00000000-0000-4000-8000-00000000f753'
    )
  ) then
    raise exception 'unassigned reviewer crossed the Admin Works Storage policy';
  end if;
end
$$;

select pg_temp.set_admin_works_claims('00000000-0000-4000-8000-00000000f702', 'aal1');
do $$
begin
  if exists (
    select 1 from storage.objects object_row
    where object_row.id in (
      '00000000-0000-4000-8000-00000000f752',
      '00000000-0000-4000-8000-00000000f753'
    )
  ) then
    raise exception 'AAL1 Admin crossed the Admin Works Storage policy';
  end if;
end
$$;

select pg_temp.set_admin_works_claims('00000000-0000-4000-8000-00000000f702', 'aal2', true);
do $$
begin
  if exists (
    select 1 from storage.objects object_row
    where object_row.id in (
      '00000000-0000-4000-8000-00000000f752',
      '00000000-0000-4000-8000-00000000f753'
    )
  ) then
    raise exception 'recovery Admin crossed the Admin Works Storage policy';
  end if;
end
$$;

select pg_temp.set_admin_works_claims('00000000-0000-4000-8000-00000000f705', 'aal2');
do $$
begin
  if exists (
    select 1 from storage.objects object_row
    where object_row.id in (
      '00000000-0000-4000-8000-00000000f752',
      '00000000-0000-4000-8000-00000000f753'
    )
  ) then
    raise exception 'inactive Admin crossed the Admin Works Storage policy';
  end if;
end
$$;
reset role;

-- Admin-only review access remains derivative-only. The assigned Reviewer
-- keeps the existing time-scoped original permission for Review Center.
insert into public.review_submissions (
  id, image_id, image_version_id, submitted_by_user_id, idempotency_key,
  status, assigned_reviewer_id, policy_version, lock_version,
  readiness_snapshot, asset_snapshot
) values (
  '00000000-0000-4000-8000-00000000f771',
  '00000000-0000-4000-8000-00000000f721',
  '00000000-0000-4000-8000-00000000f731',
  '00000000-0000-4000-8000-00000000f701',
  '00000000-0000-4000-8000-00000000f772',
  'submitted',
  '00000000-0000-4000-8000-00000000f704',
  'mt-review-2026-07-v1',
  1,
  '{"ready":true,"checks":[{},{},{},{},{}]}'::jsonb,
  '[{},{},{}]'::jsonb
);

insert into public.review_decisions (
  id, submission_id, reviewer_id, decision, reason_codes, user_message,
  internal_note, checklist_result, policy_version, idempotency_key,
  expected_lock_version, result_snapshot
) values (
  '00000000-0000-4000-8000-00000000f773',
  '00000000-0000-4000-8000-00000000f771',
  '00000000-0000-4000-8000-00000000f704',
  'approve',
  '["fixture_quality"]'::jsonb,
  'Fixture review decision.',
  null,
  '{"fixture":true}'::jsonb,
  'mt-review-2026-07-v1',
  '00000000-0000-4000-8000-00000000f774',
  1,
  '{"fixture":true}'::jsonb
);

set local role authenticated;
select pg_temp.set_admin_works_claims('00000000-0000-4000-8000-00000000f702', 'aal2');
do $$
declare
  review_detail jsonb;
begin
  review_detail := public.admin_get_image('00000000-0000-4000-8000-00000000f721');
  if review_detail #>> '{work,latest_review,image_id}'
       <> '00000000-0000-4000-8000-00000000f721'
     or review_detail #>> '{work,latest_review,image_version_id}'
       <> '00000000-0000-4000-8000-00000000f731'
     or review_detail #>> '{work,review_submissions,0,image_id}'
       <> '00000000-0000-4000-8000-00000000f721'
     or review_detail #>> '{work,review_submissions,0,image_version_image_id}'
       <> '00000000-0000-4000-8000-00000000f721'
     or review_detail #>> '{work,review_submissions,0,decisions,0,submission_id}'
       <> '00000000-0000-4000-8000-00000000f771'
     or exists (
       select 1
       from jsonb_array_elements(
         review_detail #> '{work,audit_timeline}'
       ) audit_entry
       where audit_entry ->> 'target_type' <> 'image'
          or audit_entry ->> 'target_id'
            <> '00000000-0000-4000-8000-00000000f721'
     )
     or (review_detail -> 'work') ? 'original_asset' then
    raise exception 'Admin Works detail cross-record locators are invalid: %', review_detail;
  end if;
  if not public.can_read_review_storage_object(
       'image-display',
       '00000000-0000-4000-8000-00000000f701/00000000-0000-4000-8000-00000000f721/display.jpg',
       '00000000-0000-4000-8000-00000000f701'
     )
     or public.can_read_review_storage_object(
       'image-originals',
       '00000000-0000-4000-8000-00000000f701/00000000-0000-4000-8000-00000000f721/original.jpg',
       '00000000-0000-4000-8000-00000000f701'
     )
     or not exists (
       select 1 from storage.objects object_row
       where object_row.id = '00000000-0000-4000-8000-00000000f752'
     )
     or exists (
       select 1 from storage.objects object_row
       where object_row.id = '00000000-0000-4000-8000-00000000f751'
     ) then
    raise exception 'Admin-only Review Storage exposed an original or hid a display';
  end if;
end
$$;

select pg_temp.set_admin_works_claims('00000000-0000-4000-8000-00000000f704', 'aal2');
do $$
begin
  if not public.can_read_review_storage_object(
       'image-display',
       '00000000-0000-4000-8000-00000000f701/00000000-0000-4000-8000-00000000f721/display.jpg',
       '00000000-0000-4000-8000-00000000f701'
     )
     or not public.can_read_review_storage_object(
       'image-originals',
       '00000000-0000-4000-8000-00000000f701/00000000-0000-4000-8000-00000000f721/original.jpg',
       '00000000-0000-4000-8000-00000000f701'
     )
     or (select count(*) from storage.objects object_row
         where object_row.id in (
           '00000000-0000-4000-8000-00000000f751',
           '00000000-0000-4000-8000-00000000f752'
         )) <> 2 then
    raise exception 'assigned Reviewer lost the scoped original/display access';
  end if;
end
$$;
reset role;

select 'admin_works_database_storage_rls=yes';

select pg_temp.set_admin_works_claims('00000000-0000-4000-8000-00000000f702', 'aal2');
do $$
declare
  restore_result jsonb;
begin

  restore_result := public.admin_govern_image(
    '00000000-0000-4000-8000-00000000f721',
    2,
    'restore',
    'investigation_cleared',
    'The privacy review is complete and this work is restored.',
    null,
    '00000000-0000-4000-8000-00000000f763'
  );
  if restore_result #>> '{work,publication_status}' <> 'published'
     or (restore_result #>> '{work,version}')::integer <> 3
     or restore_result #>> '{action,image_id}' <> '00000000-0000-4000-8000-00000000f721'
     or restore_result #>> '{action,actor_user_id}' <> '00000000-0000-4000-8000-00000000f702'
     or restore_result #>> '{action,actor_role}' <> 'admin'
     or restore_result #>> '{action,policy_version}' <> 'mt-admin-governance-2026-07-v1'
     or (restore_result #>> '{action,expected_image_version}')::integer <> 2
     or restore_result #>> '{work,latest_governance_action,image_id}' <> '00000000-0000-4000-8000-00000000f721'
     or restore_result #>> '{work,latest_governance_action,actor_role}' <> 'admin'
     or restore_result #>> '{work,latest_governance_action,policy_version}' <> 'mt-admin-governance-2026-07-v1'
     or restore_result #>> '{takedown,image_id}' <> '00000000-0000-4000-8000-00000000f721'
     or restore_result #>> '{action,takedown_case_id}' <> restore_result #>> '{takedown,id}'
     or restore_result #>> '{takedown,status}' <> 'restored'
     or restore_result #>> '{work,thumbnail_asset,storage_visibility}' <> 'public' then
    raise exception 'restore result is invalid: %', restore_result;
  end if;
  if public.public_delivery_work_json('00000000-0000-4000-8000-00000000f721') is null
     or exists (
       select 1 from public.image_assets a
       where a.image_id = '00000000-0000-4000-8000-00000000f721'
         and (
           (a.kind = 'original' and a.storage_visibility <> 'private')
           or (a.kind in ('display', 'thumbnail') and a.storage_visibility <> 'public')
         )
     ) then
    raise exception 'restored work visibility or original privacy is invalid';
  end if;
end
$$;

select 'admin_works_database_unpublish_restore=yes';
select 'admin_works_database_idempotency_cas=yes';

-- The product contract says Admin may govern any image; only review decisions
-- prohibit self-review. This fixture intentionally governs an Admin-owned work.
do $$
declare
  takedown_result jsonb;
  takedown_case uuid;
begin
  takedown_result := public.admin_govern_image(
    '00000000-0000-4000-8000-00000000f722',
    1,
    'takedown',
    'copyright',
    'This work is unavailable while a copyright case is reviewed.',
    'legal hold fixture',
    '00000000-0000-4000-8000-00000000f764'
  );
  if takedown_result #>> '{work,publication_status}' <> 'quarantined'
     or (takedown_result #>> '{work,version}')::integer <> 2
     or takedown_result #>> '{action,image_id}' <> '00000000-0000-4000-8000-00000000f722'
     or takedown_result #>> '{action,actor_user_id}' <> '00000000-0000-4000-8000-00000000f702'
     or takedown_result #>> '{action,actor_role}' <> 'admin'
     or takedown_result #>> '{action,policy_version}' <> 'mt-admin-governance-2026-07-v1'
     or (takedown_result #>> '{action,expected_image_version}')::integer <> 1
     or takedown_result #>> '{work,latest_governance_action,image_id}' <> '00000000-0000-4000-8000-00000000f722'
     or takedown_result #>> '{work,latest_governance_action,actor_role}' <> 'admin'
     or takedown_result #>> '{work,latest_governance_action,policy_version}' <> 'mt-admin-governance-2026-07-v1'
     or takedown_result #>> '{takedown,image_id}' <> '00000000-0000-4000-8000-00000000f722'
     or takedown_result #>> '{action,takedown_case_id}' <> takedown_result #>> '{takedown,id}'
     or takedown_result #>> '{takedown,status}' <> 'open'
     or public.public_delivery_work_json('00000000-0000-4000-8000-00000000f722') is not null then
    raise exception 'Admin-owned takedown is invalid: %', takedown_result;
  end if;
  takedown_case := (takedown_result #>> '{takedown,id}')::uuid;
  update public.takedown_cases set legal_hold = true where id = takedown_case;
  perform pg_temp.set_admin_works_claims('00000000-0000-4000-8000-00000000f702', 'aal2');
  if public.admin_govern_image(
       '00000000-0000-4000-8000-00000000f722',
       2,
       'restore',
       'appeal_upheld',
       'The appeal is accepted and this work may be restored.',
       null,
       '00000000-0000-4000-8000-00000000f765'
     ) #>> '{error,code}' <> 'ADMIN_GOVERNANCE_RESTORE_BLOCKED' then
    raise exception 'legal hold did not block restore';
  end if;
  if not exists (
    select 1
    from public.audit_logs failure_log
    where failure_log.action = 'admin.image.governance_failed'
      and failure_log.target_id = '00000000-0000-4000-8000-00000000f722'
      and failure_log.request_id = '00000000-0000-4000-8000-00000000f765'
      and failure_log.result = 'failure'
      and failure_log.after_state #>> '{error_code}' = 'ADMIN_GOVERNANCE_RESTORE_BLOCKED'
      and failure_log.after_state #>> '{action}' = 'restore'
      and failure_log.after_state #>> '{reason_code}' = 'appeal_upheld'
      and (failure_log.after_state #>> '{expected_version}')::integer = 2
      and (failure_log.after_state #>> '{current_version}')::integer = 2
      and (
        select count(*) from jsonb_object_keys(failure_log.after_state)
      ) = 7
  ) then
    raise exception 'legal hold did not write the controlled failure audit';
  end if;
end
$$;

select 'admin_works_database_takedown_legal_hold=yes';

do $$
begin
  if public.admin_govern_image(
       '00000000-0000-4000-8000-00000000f723',
       1,
       'restore',
       'copyright',
       'This message uses an invalid restore reason.',
       null,
       '00000000-0000-4000-8000-00000000f766'
     ) #>> '{error,code}' <> 'ADMIN_GOVERNANCE_VALIDATION_FAILED' then
    raise exception 'restore accepted an invalid reason';
  end if;
  if not exists (
    select 1
    from public.audit_logs failure_log
    where failure_log.request_id = '00000000-0000-4000-8000-00000000f766'
      and failure_log.action = 'admin.image.governance_failed'
      and failure_log.result = 'failure'
      and failure_log.reason_code is null
      and failure_log.after_state #>> '{error_code}' = 'ADMIN_GOVERNANCE_VALIDATION_FAILED'
      and failure_log.after_state -> 'reason_code' = 'null'::jsonb
      and (
        select count(*) from jsonb_object_keys(failure_log.after_state)
      ) = 7
  ) then
    raise exception 'invalid restore reason was not safely redacted in audit';
  end if;
  if public.admin_govern_image(
       '00000000-0000-4000-8000-00000000f723',
       1,
       'restore',
       'investigation_cleared',
       'The investigation is complete and this work may be restored.',
       null,
       '00000000-0000-4000-8000-00000000f767'
     ) #>> '{error,code}' <> 'ADMIN_GOVERNANCE_RESTORE_BLOCKED' then
    raise exception 'restore accepted a non-clean current asset';
  end if;
  if not exists (
    select 1
    from public.audit_logs failure_log
    where failure_log.request_id = '00000000-0000-4000-8000-00000000f767'
      and failure_log.action = 'admin.image.governance_failed'
      and failure_log.result = 'failure'
      and failure_log.after_state #>> '{error_code}' = 'ADMIN_GOVERNANCE_RESTORE_BLOCKED'
      and (failure_log.after_state #>> '{expected_version}')::integer = 1
      and (failure_log.after_state #>> '{current_version}')::integer = 1
  ) then
    raise exception 'asset-gated restore did not write a failure audit';
  end if;
  if public.admin_govern_image(
       '00000000-0000-4000-8000-00000000f799',
       1,
       'takedown',
       'security',
       'This unavailable image should not produce an audit target.',
       'must not be recorded',
       '00000000-0000-4000-8000-00000000f768'
     ) #>> '{error,code}' <> 'ADMIN_IMAGE_NOT_FOUND' then
    raise exception 'missing governance image did not return not-found';
  end if;
  if exists (
    select 1
    from public.audit_logs failure_log
    where failure_log.target_id = '00000000-0000-4000-8000-00000000f799'
       or failure_log.request_id = '00000000-0000-4000-8000-00000000f768'
  ) then
    raise exception 'missing image leaked an attacker-controlled audit target';
  end if;
  if (select version from public.images
      where id = '00000000-0000-4000-8000-00000000f723') <> 1
     or exists (
       select 1 from public.image_governance_actions a
       where a.image_id = '00000000-0000-4000-8000-00000000f723'
     ) then
    raise exception 'blocked restore changed image state or wrote an action';
  end if;
end
$$;

select 'admin_works_database_restore_asset_gate=yes';
select 'admin_works_database_failure_audit=yes';

reset role;
do $$
declare
  mutation_blocked boolean := false;
  action_before jsonb;
  action_after jsonb;
begin
  select to_jsonb(action_row) into action_before
  from public.image_governance_actions action_row
  where action_row.idempotency_key = '00000000-0000-4000-8000-00000000f761';
  if action_before is null then
    raise exception 'append-only fixture action is missing';
  end if;
  begin
    update public.image_governance_actions
    set user_message = 'tampered governance message'
    where idempotency_key = '00000000-0000-4000-8000-00000000f761';
  exception when sqlstate 'P0001' then
    if sqlerrm <> 'image_governance_actions is append-only' then
      raise exception 'unexpected append-only trigger error: %', sqlerrm;
    end if;
    mutation_blocked := true;
  end;
  if not mutation_blocked then
    raise exception 'image governance action was mutable';
  end if;
  select to_jsonb(action_row) into action_after
  from public.image_governance_actions action_row
  where action_row.idempotency_key = '00000000-0000-4000-8000-00000000f761';
  if action_after is distinct from action_before then
    raise exception 'append-only action changed after rejected update';
  end if;
end
$$;

select 'admin_works_database_append_only=yes';

rollback;
select 'admin_works_database_fixtures_rolled_back=yes';
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
            "Refusing Admin Works database fixtures without "
            "MT_TEST_ENVIRONMENT=development"
        )
    if os.environ.get("MT_ALLOW_PRODUCTION") == "yes":
        raise RuntimeError(
            "Refusing Admin Works database fixtures while production approval is enabled"
        )
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
    raise RuntimeError("psql is required for the Admin Works database acceptance")


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
    return cleaned.strip()[-3000:]


def run_psql(sql: str) -> str:
    completed = subprocess.run(
        psql_command(),
        input=sql,
        cwd=ROOT,
        env=os.environ.copy(),
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    if completed.returncode:
        detail = redact_diagnostics(completed.stderr)
        raise RuntimeError(
            "Admin Works database acceptance failed"
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
          + (select count(*) from public.folders where id in ({sql_values(FOLDER_IDS)}))
          + (select count(*) from public.images where id in ({sql_values(IMAGE_IDS)}))
          + (select count(*) from public.image_versions
             where image_id in ({sql_values(IMAGE_IDS)}))
          + (select count(*) from public.image_assets where id in ({sql_values(ASSET_IDS)}))
          + (select count(*) from public.asset_scan_jobs
             where asset_id in ({sql_values(ASSET_IDS)}))
          + (select count(*) from storage.objects where id in ({sql_values(OBJECT_IDS)}))
          + (select count(*) from public.review_submissions
             where id in ({sql_values(REVIEW_SUBMISSION_IDS)}))
          + (select count(*) from public.review_decisions
             where id in ({sql_values(REVIEW_DECISION_IDS)}))
          + (select count(*) from public.image_governance_actions
             where image_id in ({sql_values(IMAGE_IDS)}))
          + (select count(*) from public.takedown_cases
             where image_id in ({sql_values(IMAGE_IDS)}))
          + (select count(*) from public.notifications
             where payload ->> 'image_id' in ({sql_values(IMAGE_IDS)}))
          + (select count(*) from public.audit_logs
             where target_type = 'image' and target_id in ({sql_values(IMAGE_IDS)}))
        );
        """
    ).strip()
    if fixture_count != "0":
        raise RuntimeError("Admin Works database fixture UUIDs remain after rollback")


def main() -> None:
    load_dotenv()
    require_development_environment()
    output = run_psql(SQL)
    lines = {line.strip() for line in output.splitlines() if line.strip()}
    missing = [marker for marker in EXPECTED_MARKERS if marker not in lines]
    if missing:
        raise RuntimeError(
            f"Admin Works database markers are missing: {', '.join(missing)}"
        )
    assert_fixtures_absent()
    for marker in EXPECTED_MARKERS:
        print(marker)
    print("admin_works_database_fixtures_absent=yes")


if __name__ == "__main__":
    main()
