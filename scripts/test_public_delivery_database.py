#!/usr/bin/env python3
"""Development-only, rollback-only public delivery database acceptance."""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess


ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT / ".env"

USER_IDS = (
    "00000000-0000-4000-8000-00000000f601",
    "00000000-0000-4000-8000-00000000f602",
    "00000000-0000-4000-8000-00000000f603",
)
FOLDER_IDS = (
    "00000000-0000-4000-8000-00000000f607",
    "00000000-0000-4000-8000-00000000f608",
    "00000000-0000-4000-8000-00000000f609",
)
IMAGE_IDS = (
    "00000000-0000-4000-8000-00000000f611",
    "00000000-0000-4000-8000-00000000f612",
    "00000000-0000-4000-8000-00000000f613",
    "00000000-0000-4000-8000-00000000f614",
    "00000000-0000-4000-8000-00000000f615",
    "00000000-0000-4000-8000-00000000f616",
)
ASSET_IDS = tuple(
    f"00000000-0000-4000-8000-00000000f6{suffix}"
    for suffix in ("31", "32", "33", "34", "35", "36", "37", "38", "39", "3a", "3b", "3c", "3d")
)
OBJECT_IDS = tuple(
    f"00000000-0000-4000-8000-00000000f6{suffix}"
    for suffix in ("41", "42", "43", "44", "45", "46", "47", "48", "49", "4a", "4b", "4c", "4d")
)

EXPECTED_MARKERS = (
    "public_delivery_database_pg_proc_security=yes",
    "public_delivery_database_acl_boundary=yes",
    "public_delivery_database_published_only=yes",
    "public_delivery_database_account_status=yes",
    "public_delivery_database_storage_boundary=yes",
    "public_delivery_database_selected_derivatives=yes",
    "public_delivery_database_creator_projection=yes",
    "public_delivery_database_owner_cover=yes",
    "public_delivery_database_status=yes",
    "public_delivery_database_fixtures_rolled_back=yes",
)


SQL = r"""
\set ON_ERROR_STOP on

begin;
select pg_advisory_xact_lock(hashtextextended('mt-public-delivery-database-test', 0));

do $$
declare
  proc_row record;
begin
  if not has_function_privilege('anon', 'public.get_public_works(text,integer,integer)', 'EXECUTE')
     or not has_function_privilege('authenticated', 'public.get_public_works(text,integer,integer)', 'EXECUTE')
     or has_function_privilege('service_role', 'public.get_public_works(text,integer,integer)', 'EXECUTE')
     or not has_function_privilege('anon', 'public.get_public_creator(text)', 'EXECUTE')
     or not has_function_privilege('authenticated', 'public.get_public_creator(text)', 'EXECUTE')
     or has_function_privilege('service_role', 'public.get_public_creator(text)', 'EXECUTE')
     or has_function_privilege('anon', 'public.get_my_public_delivery_status()', 'EXECUTE')
     or not has_function_privilege('authenticated', 'public.get_my_public_delivery_status()', 'EXECUTE')
     or has_function_privilege('service_role', 'public.get_my_public_delivery_status()', 'EXECUTE')
     or not has_function_privilege('anon', 'public.can_read_public_storage_object(text,text,text)', 'EXECUTE')
     or has_function_privilege('service_role', 'public.can_read_public_storage_object(text,text,text)', 'EXECUTE') then
    raise exception 'public delivery RPC grants do not match the explicit allowlist';
  end if;

  if has_table_privilege('anon', 'public.images', 'SELECT')
     or has_table_privilege('anon', 'public.image_versions', 'SELECT')
     or has_table_privilege('authenticated', 'public.images', 'SELECT')
     or has_table_privilege('authenticated', 'public.image_versions', 'SELECT') then
    raise exception 'public roles retain raw image/version SELECT privileges';
  end if;

  for proc_row in
    select p.oid::regprocedure::text as identity, p.prosecdef, p.proconfig
    from pg_proc p
    where p.oid in (
      'public.public_delivery_asset_json(uuid,uuid)'::regprocedure,
      'public.public_delivery_work_json(uuid)'::regprocedure,
      'public.get_public_works(text,integer,integer)'::regprocedure,
      'public.get_public_creator(text)'::regprocedure,
      'public.get_my_public_delivery_status()'::regprocedure,
      'public.can_read_public_storage_object(text,text,text)'::regprocedure
    )
  loop
    if not proc_row.prosecdef then
      raise exception '% is not SECURITY DEFINER', proc_row.identity;
    end if;
    if not coalesce(proc_row.proconfig, '{}'::text[]) @> array['search_path=""']::text[] then
      raise exception '% does not pin an empty search_path', proc_row.identity;
    end if;
  end loop;
end
$$;

select 'public_delivery_database_pg_proc_security=yes';
select 'public_delivery_database_acl_boundary=yes';

do $$
begin
  if not exists (
    select 1 from storage.buckets where id = 'image-originals'
  ) or not exists (
    select 1 from storage.buckets where id = 'image-display'
  ) or not exists (
    select 1 from storage.buckets where id = 'image-thumbnails'
  ) then
    raise exception 'public delivery Storage buckets are not deployed';
  end if;
  if exists (select 1 from public.users where id in (
    '00000000-0000-4000-8000-00000000f601',
    '00000000-0000-4000-8000-00000000f602',
    '00000000-0000-4000-8000-00000000f603'
  )) or exists (select 1 from public.folders where id in (
    '00000000-0000-4000-8000-00000000f607',
    '00000000-0000-4000-8000-00000000f608',
    '00000000-0000-4000-8000-00000000f609'
  )) or exists (
    select 1 from storage.objects where id between
      '00000000-0000-4000-8000-00000000f641'::uuid and
      '00000000-0000-4000-8000-00000000f64d'::uuid
  ) then
    raise exception 'fixed public delivery database fixtures already exist';
  end if;
end
$$;

create function pg_temp.set_public_delivery_claims(actor_id uuid)
returns void
language plpgsql
as $$
begin
  perform set_config(
    'request.jwt.claims',
    jsonb_build_object(
      'sub', actor_id,
      'role', 'authenticated',
      'aal', 'aal1',
      'amr', jsonb_build_array(jsonb_build_object('method', 'password'))
    )::text,
    true
  );
end
$$;

insert into public.users (id, auth_subject, email, email_verified_at, account_status) values
  ('00000000-0000-4000-8000-00000000f601', '00000000-0000-4000-8000-00000000f601', 'delivery-active@example.test', now(), 'active'),
  ('00000000-0000-4000-8000-00000000f602', '00000000-0000-4000-8000-00000000f602', 'delivery-suspended@example.test', now(), 'suspended'),
  ('00000000-0000-4000-8000-00000000f603', '00000000-0000-4000-8000-00000000f603', 'delivery-deletion@example.test', now(), 'deletion_requested');

insert into public.folders (id, owner_user_id, name, sort_order, is_system) values
  ('00000000-0000-4000-8000-00000000f607', '00000000-0000-4000-8000-00000000f601', 'Inbox', 0, true),
  ('00000000-0000-4000-8000-00000000f608', '00000000-0000-4000-8000-00000000f602', 'Inbox', 0, true),
  ('00000000-0000-4000-8000-00000000f609', '00000000-0000-4000-8000-00000000f603', 'Inbox', 0, true);

insert into public.user_profiles (
  user_id, display_name, public_slug, professional_headline, company, city,
  country_code, bio, website_url, availability_status, instagram_url,
  linkedin_url, avatar_url, public_fields
) values
  (
    '00000000-0000-4000-8000-00000000f601', 'Public Delivery Active', 'delivery-active',
    'Editorial photographer', 'MT Test Studio', 'Hangzhou', 'CN',
    'A public creator fixture.', 'https://example.test', 'open',
    'https://instagram.com/mt-test', 'https://linkedin.com/in/mt-test',
    'https://example.test/avatar.jpg',
    '{"professional_headline":true,"company":true,"city":true,"country_code":true,"bio":true,"website_url":true,"availability_status":true,"instagram_url":true,"linkedin_url":true,"avatar_url":true}'::jsonb
  ),
  ('00000000-0000-4000-8000-00000000f602', 'Public Delivery Suspended', 'delivery-suspended', null, null, null, null, null, null, 'unavailable', null, null, null, '{}'::jsonb),
  ('00000000-0000-4000-8000-00000000f603', 'Public Delivery Deletion', 'delivery-deletion', null, null, null, null, null, null, 'unavailable', null, null, null, '{}'::jsonb);

insert into public.images (
  id, owner_user_id, processing_status, workflow_status, publication_status,
  original_filename, original_width, original_height, checksum_sha256,
  version, published_at, deleted_at, updated_at
) values
  ('00000000-0000-4000-8000-00000000f611', '00000000-0000-4000-8000-00000000f601', 'ready', 'approved', 'published', 'visible-original-secret.jpg', 1800, 1200, repeat('1', 64), 1, now() - interval '1 hour', null, now()),
  ('00000000-0000-4000-8000-00000000f612', '00000000-0000-4000-8000-00000000f601', 'ready', 'approved', 'never_published', 'approved-only.jpg', 1800, 1200, repeat('2', 64), 1, null, null, now()),
  ('00000000-0000-4000-8000-00000000f613', '00000000-0000-4000-8000-00000000f601', 'ready', 'approved', 'published', 'deleted-published.jpg', 1800, 1200, repeat('3', 64), 1, now() - interval '2 hours', now() - interval '1 hour', now()),
  ('00000000-0000-4000-8000-00000000f614', '00000000-0000-4000-8000-00000000f602', 'ready', 'approved', 'published', 'suspended-published.jpg', 1800, 1200, repeat('4', 64), 1, now() - interval '3 hours', null, now()),
  ('00000000-0000-4000-8000-00000000f615', '00000000-0000-4000-8000-00000000f603', 'ready', 'approved', 'published', 'deletion-published.jpg', 1800, 1200, repeat('5', 64), 1, now() - interval '4 hours', null, now()),
  ('00000000-0000-4000-8000-00000000f616', '00000000-0000-4000-8000-00000000f601', 'ready', 'approved', 'published', 'private-derivative.jpg', 1800, 1200, repeat('6', 64), 1, now() - interval '5 hours', null, now());

insert into public.image_versions (
  id, image_id, version_number, title, caption, description, alt_text, tags,
  content_category, captured_at, location_name, gps_visibility, public_exif,
  created_by_user_id, locked_at
) values
  ('00000000-0000-4000-8000-00000000f621', '00000000-0000-4000-8000-00000000f611', 1, 'Visible public work', 'Public caption', 'Public description', 'Visible work alt text', '["public","delivery"]', 'concrete', now() - interval '1 day', 'private-gps-canary', 'private', '{"camera":"MT Fixture","gps":"private-gps-canary"}', '00000000-0000-4000-8000-00000000f601', now()),
  ('00000000-0000-4000-8000-00000000f622', '00000000-0000-4000-8000-00000000f612', 1, 'Approved only', '', '', '', '[]', 'concrete', null, null, 'private', '{}', '00000000-0000-4000-8000-00000000f601', now()),
  ('00000000-0000-4000-8000-00000000f623', '00000000-0000-4000-8000-00000000f613', 1, 'Deleted public work', '', '', '', '[]', 'concrete', null, null, 'private', '{}', '00000000-0000-4000-8000-00000000f601', now()),
  ('00000000-0000-4000-8000-00000000f624', '00000000-0000-4000-8000-00000000f614', 1, 'Suspended public work', '', '', '', '[]', 'concrete', null, null, 'private', '{}', '00000000-0000-4000-8000-00000000f602', now()),
  ('00000000-0000-4000-8000-00000000f625', '00000000-0000-4000-8000-00000000f615', 1, 'Deletion public work', '', '', '', '[]', 'concrete', null, null, 'private', '{}', '00000000-0000-4000-8000-00000000f603', now()),
  ('00000000-0000-4000-8000-00000000f626', '00000000-0000-4000-8000-00000000f616', 1, 'Private derivative work', '', '', '', '[]', 'concrete', null, null, 'private', '{}', '00000000-0000-4000-8000-00000000f601', now());

update public.images set current_version_id = case id
  when '00000000-0000-4000-8000-00000000f611' then '00000000-0000-4000-8000-00000000f621'::uuid
  when '00000000-0000-4000-8000-00000000f612' then '00000000-0000-4000-8000-00000000f622'::uuid
  when '00000000-0000-4000-8000-00000000f613' then '00000000-0000-4000-8000-00000000f623'::uuid
  when '00000000-0000-4000-8000-00000000f614' then '00000000-0000-4000-8000-00000000f624'::uuid
  when '00000000-0000-4000-8000-00000000f615' then '00000000-0000-4000-8000-00000000f625'::uuid
  else '00000000-0000-4000-8000-00000000f626'::uuid
end
where id between '00000000-0000-4000-8000-00000000f611'::uuid
  and '00000000-0000-4000-8000-00000000f616'::uuid;

create temporary table public_delivery_fixture_assets (
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
  visibility text not null
) on commit drop;

insert into public_delivery_fixture_assets values
  ('00000000-0000-4000-8000-00000000f641', '00000000-0000-4000-8000-00000000f631', '00000000-0000-4000-8000-00000000f611', '00000000-0000-4000-8000-00000000f601', 'original', 'image-originals', '00000000-0000-4000-8000-00000000f601/00000000-0000-4000-8000-00000000f611/original.jpg', 3000, 3000, 2000, 'private'),
  ('00000000-0000-4000-8000-00000000f642', '00000000-0000-4000-8000-00000000f632', '00000000-0000-4000-8000-00000000f611', '00000000-0000-4000-8000-00000000f601', 'display', 'image-display', '00000000-0000-4000-8000-00000000f601/00000000-0000-4000-8000-00000000f611/display.jpg', 1800, 1800, 1200, 'public'),
  ('00000000-0000-4000-8000-00000000f643', '00000000-0000-4000-8000-00000000f633', '00000000-0000-4000-8000-00000000f611', '00000000-0000-4000-8000-00000000f601', 'thumbnail', 'image-thumbnails', '00000000-0000-4000-8000-00000000f601/00000000-0000-4000-8000-00000000f611/thumbnail.jpg', 600, 600, 400, 'public'),
  ('00000000-0000-4000-8000-00000000f644', '00000000-0000-4000-8000-00000000f634', '00000000-0000-4000-8000-00000000f612', '00000000-0000-4000-8000-00000000f601', 'display', 'image-display', '00000000-0000-4000-8000-00000000f601/00000000-0000-4000-8000-00000000f612/display.jpg', 1800, 1800, 1200, 'public'),
  ('00000000-0000-4000-8000-00000000f645', '00000000-0000-4000-8000-00000000f635', '00000000-0000-4000-8000-00000000f612', '00000000-0000-4000-8000-00000000f601', 'thumbnail', 'image-thumbnails', '00000000-0000-4000-8000-00000000f601/00000000-0000-4000-8000-00000000f612/thumbnail.jpg', 600, 600, 400, 'public'),
  ('00000000-0000-4000-8000-00000000f646', '00000000-0000-4000-8000-00000000f636', '00000000-0000-4000-8000-00000000f613', '00000000-0000-4000-8000-00000000f601', 'display', 'image-display', '00000000-0000-4000-8000-00000000f601/00000000-0000-4000-8000-00000000f613/display.jpg', 1800, 1800, 1200, 'public'),
  ('00000000-0000-4000-8000-00000000f647', '00000000-0000-4000-8000-00000000f637', '00000000-0000-4000-8000-00000000f613', '00000000-0000-4000-8000-00000000f601', 'thumbnail', 'image-thumbnails', '00000000-0000-4000-8000-00000000f601/00000000-0000-4000-8000-00000000f613/thumbnail.jpg', 600, 600, 400, 'public'),
  ('00000000-0000-4000-8000-00000000f648', '00000000-0000-4000-8000-00000000f638', '00000000-0000-4000-8000-00000000f614', '00000000-0000-4000-8000-00000000f602', 'display', 'image-display', '00000000-0000-4000-8000-00000000f602/00000000-0000-4000-8000-00000000f614/display.jpg', 1800, 1800, 1200, 'public'),
  ('00000000-0000-4000-8000-00000000f649', '00000000-0000-4000-8000-00000000f639', '00000000-0000-4000-8000-00000000f614', '00000000-0000-4000-8000-00000000f602', 'thumbnail', 'image-thumbnails', '00000000-0000-4000-8000-00000000f602/00000000-0000-4000-8000-00000000f614/thumbnail.jpg', 600, 600, 400, 'public'),
  ('00000000-0000-4000-8000-00000000f64a', '00000000-0000-4000-8000-00000000f63a', '00000000-0000-4000-8000-00000000f615', '00000000-0000-4000-8000-00000000f603', 'display', 'image-display', '00000000-0000-4000-8000-00000000f603/00000000-0000-4000-8000-00000000f615/display.jpg', 1800, 1800, 1200, 'public'),
  ('00000000-0000-4000-8000-00000000f64b', '00000000-0000-4000-8000-00000000f63b', '00000000-0000-4000-8000-00000000f615', '00000000-0000-4000-8000-00000000f603', 'thumbnail', 'image-thumbnails', '00000000-0000-4000-8000-00000000f603/00000000-0000-4000-8000-00000000f615/thumbnail.jpg', 600, 600, 400, 'public'),
  ('00000000-0000-4000-8000-00000000f64c', '00000000-0000-4000-8000-00000000f63c', '00000000-0000-4000-8000-00000000f616', '00000000-0000-4000-8000-00000000f601', 'display', 'image-display', '00000000-0000-4000-8000-00000000f601/00000000-0000-4000-8000-00000000f616/display.jpg', 1800, 1800, 1200, 'private'),
  ('00000000-0000-4000-8000-00000000f64d', '00000000-0000-4000-8000-00000000f63d', '00000000-0000-4000-8000-00000000f616', '00000000-0000-4000-8000-00000000f601', 'thumbnail', 'image-thumbnails', '00000000-0000-4000-8000-00000000f601/00000000-0000-4000-8000-00000000f616/thumbnail.jpg', 600, 600, 400, 'public');

insert into storage.objects (id, bucket_id, name, owner_id, metadata)
select object_id, bucket, storage_key, owner_id::text,
       jsonb_build_object('mimetype', 'image/jpeg', 'size', byte_size)
from public_delivery_fixture_assets;

insert into public.image_assets (
  id, image_id, owner_user_id, kind, storage_key, mime_type, byte_size,
  width, height, checksum_sha256, storage_visibility
)
select asset_id, image_id, owner_id, kind, storage_key, 'image/jpeg', byte_size,
       width, height, repeat('a', 64), visibility
from public_delivery_fixture_assets;

update public.asset_scan_jobs job set
  status = 'clean',
  attempt_count = 1,
  scanner_version = 'public-delivery-fixture',
  engine_name = 'fixture',
  engine_version = '1',
  result_code = 'clean',
  result_details = '{"fixture":true}'::jsonb,
  completed_at = now()
where job.asset_id in (select asset_id from public_delivery_fixture_assets);

update public.image_assets asset set
  scan_status = 'clean',
  scan_result_code = 'clean',
  scan_completed_at = now(),
  scan_policy_version = 'mt-asset-scan-2026-07-v1'
where asset.id in (select asset_id from public_delivery_fixture_assets);

update public.user_profiles
set cover_asset_id = '00000000-0000-4000-8000-00000000f632'
where user_id = '00000000-0000-4000-8000-00000000f601';

set local role anon;
do $$
declare
  works jsonb := public.get_public_works(null, 100, 0);
  creator jsonb := public.get_public_creator('delivery-active');
begin
  if works ->> 'count' <> '1'
     or jsonb_array_length(works -> 'items') <> 1
     or works #>> '{items,0,id}' <> '00000000-0000-4000-8000-00000000f611'
     or works #>> '{items,0,creator,slug}' <> 'delivery-active'
     or works #>> '{items,0,display_asset,kind}' <> 'display'
     or works #>> '{items,0,thumbnail_asset,kind}' <> 'thumbnail'
     or works::text like '%visible-original-secret%'
     or works::text like '%/original.jpg%'
     or works::text like '%private-gps-canary%'
     or works::text like '%delivery-active@example.test%' then
    raise exception 'anonymous Works projection is not published-only or leaks private data';
  end if;
  if creator ->> 'slug' <> 'delivery-active'
     or creator ->> 'display_name' <> 'Public Delivery Active'
     or creator ->> 'work_count' <> '1'
     or jsonb_array_length(creator -> 'works') <> 1
     or creator #>> '{cover_asset,id}' <> '00000000-0000-4000-8000-00000000f632'
     or creator::text like '%delivery-active@example.test%'
     or creator::text like '%private-gps-canary%' then
    raise exception 'anonymous creator projection is incomplete or leaks private data';
  end if;
  if public.get_public_creator('delivery-suspended') <> '{}'::jsonb
     or public.get_public_creator('delivery-deletion') <> '{}'::jsonb
     or public.get_public_works('delivery-suspended', 100, 0) ->> 'count' <> '0'
     or public.get_public_works('delivery-deletion', 100, 0) ->> 'count' <> '0' then
    raise exception 'restricted creator account entered public delivery';
  end if;
end
$$;

select 'public_delivery_database_published_only=yes';
select 'public_delivery_database_account_status=yes';
select 'public_delivery_database_creator_projection=yes';

do $$
declare
  accessible_count integer;
  display_allowed boolean;
  original_allowed boolean;
  suspended_allowed boolean;
  partial_thumbnail_allowed boolean;
begin
  select count(*) into accessible_count
  from storage.objects
  where id between '00000000-0000-4000-8000-00000000f641'::uuid
    and '00000000-0000-4000-8000-00000000f64d'::uuid;
  display_allowed := public.can_read_public_storage_object(
    'image-display',
    '00000000-0000-4000-8000-00000000f601/00000000-0000-4000-8000-00000000f611/display.jpg',
    '00000000-0000-4000-8000-00000000f601'
  );
  original_allowed := public.can_read_public_storage_object(
    'image-originals',
    '00000000-0000-4000-8000-00000000f601/00000000-0000-4000-8000-00000000f611/original.jpg',
    '00000000-0000-4000-8000-00000000f601'
  );
  suspended_allowed := public.can_read_public_storage_object(
    'image-display',
    '00000000-0000-4000-8000-00000000f602/00000000-0000-4000-8000-00000000f614/display.jpg',
    '00000000-0000-4000-8000-00000000f602'
  );
  partial_thumbnail_allowed := public.can_read_public_storage_object(
    'image-thumbnails',
    '00000000-0000-4000-8000-00000000f601/00000000-0000-4000-8000-00000000f616/thumbnail.jpg',
    '00000000-0000-4000-8000-00000000f601'
  );
  if accessible_count <> 2
     or not display_allowed
     or original_allowed
     or suspended_allowed
     or partial_thumbnail_allowed then
    raise exception
      'anonymous Storage boundary mismatch (count=%, display=%, original=%, suspended=%, partial_thumbnail=%)',
      accessible_count, display_allowed, original_allowed, suspended_allowed,
      partial_thumbnail_allowed;
  end if;
end
$$;
reset role;

select 'public_delivery_database_storage_boundary=yes';
select 'public_delivery_database_selected_derivatives=yes';

select pg_temp.set_public_delivery_claims('00000000-0000-4000-8000-00000000f601');
set local role authenticated;
do $$
declare
  status jsonb := public.get_my_public_delivery_status();
  cover jsonb := public.get_my_profile_cover();
begin
  if status ->> 'available' <> 'true'
     or status ->> 'slug' <> 'delivery-active'
     or status ->> 'path' <> '/creators/delivery-active'
     or status ->> 'published_count' <> '1' then
    raise exception 'active creator public delivery status is incorrect';
  end if;
  if cover #>> '{cover_asset,id}' <> '00000000-0000-4000-8000-00000000f632'
     or not exists (
       select 1 from jsonb_array_elements(cover -> 'candidates') candidate
       where candidate ->> 'id' = '00000000-0000-4000-8000-00000000f632'
     ) then
    raise exception 'public derivative is unavailable as the owner profile cover';
  end if;
end
$$;
reset role;

select 'public_delivery_database_owner_cover=yes';
select 'public_delivery_database_status=yes';

select pg_temp.set_public_delivery_claims('00000000-0000-4000-8000-00000000f602');
set local role authenticated;
do $$
begin
  begin
    perform public.get_my_public_delivery_status();
    raise exception 'suspended account read public delivery settings';
  exception when sqlstate '42501' then
    null;
  end;
end
$$;
reset role;

select pg_temp.set_public_delivery_claims('00000000-0000-4000-8000-00000000f603');
set local role authenticated;
do $$
begin
  begin
    perform public.get_my_public_delivery_status();
    raise exception 'deletion-requested account read public delivery settings';
  exception when sqlstate '42501' then
    null;
  end;
end
$$;
reset role;

rollback;
select 'public_delivery_database_fixtures_rolled_back=yes';
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
            "Refusing public delivery database fixtures without MT_TEST_ENVIRONMENT=development"
        )
    if os.environ.get("MT_ALLOW_PRODUCTION") == "yes":
        raise RuntimeError(
            "Refusing public delivery database fixtures while production approval is enabled"
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
    raise RuntimeError("psql is required for the public delivery database acceptance")


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
            "Public delivery database acceptance failed"
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
          + (select count(*) from public.image_versions where image_id in ({sql_values(IMAGE_IDS)}))
          + (select count(*) from public.image_assets where id in ({sql_values(ASSET_IDS)}))
          + (select count(*) from public.asset_scan_jobs where asset_id in ({sql_values(ASSET_IDS)}))
          + (select count(*) from storage.objects where id in ({sql_values(OBJECT_IDS)}))
        );
        """
    ).strip()
    if fixture_count != "0":
        raise RuntimeError("Public delivery database fixture UUIDs remain after rollback")


def main() -> None:
    load_dotenv()
    require_development_environment()
    output = run_psql(SQL)
    lines = {line.strip() for line in output.splitlines() if line.strip()}
    missing = [marker for marker in EXPECTED_MARKERS if marker not in lines]
    if missing:
        raise RuntimeError(f"Public delivery database markers are missing: {', '.join(missing)}")
    assert_fixtures_absent()
    for marker in EXPECTED_MARKERS:
        print(marker)
    print("public_delivery_database_fixtures_absent=yes")


if __name__ == "__main__":
    main()
