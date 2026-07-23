begin;

-- Published-only delivery boundary. Public callers receive explicit DTOs from
-- SECURITY DEFINER RPCs; the underlying image/version rows remain private.

do $migration$
begin
  if not exists (
    select 1
    from pg_catalog.pg_type t
    join pg_catalog.pg_namespace n on n.oid = t.typnamespace
    where n.nspname = 'public' and t.typname = 'creator_availability_status'
  ) then
    create type public.creator_availability_status as enum ('unavailable', 'open', 'limited');
  end if;
end
$migration$;

-- This migration sorts before the creator-profile migration on fresh installs,
-- so it establishes the columns its public DTO needs. The later migration adds
-- the complete validation/FK contract with ADD ... IF NOT EXISTS.
alter table public.user_profiles
  add column if not exists professional_headline text,
  add column if not exists company text,
  add column if not exists city text,
  add column if not exists availability_status public.creator_availability_status
    not null default 'unavailable'::public.creator_availability_status,
  add column if not exists instagram_url text,
  add column if not exists linkedin_url text,
  add column if not exists cover_asset_id uuid,
  add column if not exists public_slug text;

update public.user_profiles p
set public_slug = 'creator-' || replace(gen_random_uuid()::text, '-', '')
where p.public_slug is null;

alter table public.user_profiles
  alter column public_slug set default ('creator-' || replace(gen_random_uuid()::text, '-', '')),
  alter column public_slug set not null;

do $migration$
begin
  if not exists (
    select 1 from pg_catalog.pg_constraint
    where conrelid = 'public.user_profiles'::regclass
      and conname = 'user_profiles_public_slug_check'
  ) then
    alter table public.user_profiles
      add constraint user_profiles_public_slug_check check (
        public_slug = lower(public_slug)
        and length(public_slug) between 3 and 64
        and public_slug ~ '^[a-z0-9][a-z0-9-]{1,62}[a-z0-9]$'
      );
  end if;
end
$migration$;

create unique index if not exists user_profiles_public_slug_key
  on public.user_profiles (public_slug);

create index if not exists images_public_delivery_owner_published_idx
  on public.images (owner_user_id, published_at desc, id)
  where publication_status = 'published'
    and processing_status = 'ready'
    and workflow_status = 'approved'
    and deleted_at is null;

create or replace function public.public_delivery_ratio_code(
  target_width integer,
  target_height integer
)
returns text
language sql
immutable
set search_path = ''
as $$
  select case
    when $1 is null or $2 is null or $1 < 1 or $2 < 1 then null
    when ($1::numeric / $2::numeric) >= 2.05
      or ($1::numeric / $2::numeric) <= 0.49 then 'panorama'
    else (
      select candidate.code
      from (values
        ('one_to_one', 1::numeric, 1),
        ('four_to_three', 4::numeric / 3::numeric, 2),
        ('four_to_five', 4::numeric / 5::numeric, 3),
        ('two_to_three', 2::numeric / 3::numeric, 4),
        ('three_to_two', 3::numeric / 2::numeric, 5),
        ('sixteen_to_nine', 16::numeric / 9::numeric, 6)
      ) candidate(code, ratio, priority)
      order by abs(($1::numeric / $2::numeric) - candidate.ratio), candidate.priority
      limit 1
    )
  end
$$;

create or replace function public.public_delivery_tags(raw_tags jsonb)
returns jsonb
language sql
immutable
set search_path = ''
as $$
  select coalesce(jsonb_agg(entry.value order by entry.ordinality), '[]'::jsonb)
  from (
    select item.value, item.ordinality
    from jsonb_array_elements(
      case when jsonb_typeof($1) = 'array' then $1 else '[]'::jsonb end
    ) with ordinality as item(value, ordinality)
    where jsonb_typeof(item.value) = 'string'
      and length(btrim(item.value #>> '{}')) between 1 and 80
    order by item.ordinality
    limit 40
  ) entry
$$;

create or replace function public.public_delivery_exif(raw_exif jsonb)
returns jsonb
language sql
immutable
set search_path = ''
as $$
  select jsonb_strip_nulls(jsonb_build_object(
    'camera', case when jsonb_typeof(coalesce($1, '{}'::jsonb) -> 'camera') in ('string', 'number') then $1 -> 'camera' end,
    'lens', case when jsonb_typeof(coalesce($1, '{}'::jsonb) -> 'lens') in ('string', 'number') then $1 -> 'lens' end,
    'exposure', case when jsonb_typeof(coalesce($1, '{}'::jsonb) -> 'exposure') in ('string', 'number') then $1 -> 'exposure' end,
    'aperture', case when jsonb_typeof(coalesce($1, '{}'::jsonb) -> 'aperture') in ('string', 'number') then $1 -> 'aperture' end,
    'iso', case when jsonb_typeof(coalesce($1, '{}'::jsonb) -> 'iso') in ('string', 'number') then $1 -> 'iso' end,
    'focal_length', case when jsonb_typeof(coalesce($1, '{}'::jsonb) -> 'focal_length') in ('string', 'number') then $1 -> 'focal_length' end
  ))
$$;

create or replace function public.public_delivery_asset_json(
  target_asset_id uuid,
  expected_owner_id uuid
)
returns jsonb
language sql
stable
security definer
set search_path = ''
as $$
  select jsonb_build_object(
    'id', a.id,
    'image_id', a.image_id,
    'kind', a.kind,
    'storage_bucket', scan_job.storage_bucket,
    'storage_key', a.storage_key,
    'mime_type', a.mime_type,
    'width', a.width,
    'height', a.height
  )
  from public.image_assets a
  join public.images i
    on i.id = a.image_id and i.owner_user_id = a.owner_user_id
  join public.image_versions v
    on v.id = i.current_version_id and v.image_id = i.id
  join public.users owner_user on owner_user.id = i.owner_user_id
  join public.asset_scan_jobs scan_job on scan_job.asset_id = a.id
  join storage.objects storage_object
    on storage_object.id = scan_job.expected_storage_object_id
    and storage_object.bucket_id = scan_job.storage_bucket
    and storage_object.name = a.storage_key
    and storage_object.owner_id = i.owner_user_id::text
  where a.id = $1
    and a.owner_user_id = $2
    and a.kind in ('display', 'thumbnail')
    and a.deleted_at is null
    and a.storage_visibility = 'public'
    and a.scan_status = 'clean'
    and a.scan_result_code = 'clean'
    and a.scan_completed_at is not null
    and a.scan_policy_version = 'mt-asset-scan-2026-07-v1'
    and scan_job.status = 'clean'
    and scan_job.result_code = 'clean'
    and scan_job.scan_policy_version = 'mt-asset-scan-2026-07-v1'
    and scan_job.completed_at is not null
    and scan_job.storage_bucket = case a.kind
      when 'display' then 'image-display'
      else 'image-thumbnails'
    end
    and scan_job.storage_key = a.storage_key
    and scan_job.mime_type = a.mime_type
    and scan_job.byte_size = a.byte_size
    and scan_job.width = a.width
    and scan_job.height = a.height
    and scan_job.checksum_sha256 = a.checksum_sha256
    and i.deleted_at is null
    and i.processing_status = 'ready'::public.processing_status
    and i.workflow_status = 'approved'::public.workflow_status
    and i.publication_status = 'published'::public.publication_status
    and i.published_at is not null
    and i.unpublished_at is null
    and owner_user.account_status = 'active'::public.account_status
  limit 1
$$;

create or replace function public.public_delivery_work_json(target_image_id uuid)
returns jsonb
language sql
stable
security definer
set search_path = ''
as $$
  select jsonb_build_object(
    'id', i.id,
    'title', coalesce(nullif(v.title, ''), 'Untitled Work'),
    'caption', left(v.caption, 500),
    'description', left(v.description, 6000),
    'alt_text', left(v.alt_text, 500),
    'tags', public.public_delivery_tags(v.tags),
    'content_category', v.content_category,
    'captured_at', v.captured_at,
    'location_name', case
      when v.gps_visibility in ('approximate', 'public') then nullif(v.location_name, '')
      else null
    end,
    'public_exif', public.public_delivery_exif(v.public_exif),
    'published_at', i.published_at,
    'width', i.original_width,
    'height', i.original_height,
    'ratio_code', public.public_delivery_ratio_code(i.original_width, i.original_height),
    'ratio_label', case public.public_delivery_ratio_code(i.original_width, i.original_height)
      when 'one_to_one' then '1:1'
      when 'four_to_three' then '4:3'
      when 'four_to_five' then '4:5'
      when 'two_to_three' then '2:3'
      when 'three_to_two' then '3:2'
      when 'sixteen_to_nine' then '16:9'
      else 'Panorama'
    end,
    'creator', jsonb_build_object(
      'slug', p.public_slug,
      'display_name', p.display_name
    ),
    'display_asset', display_asset.value,
    'thumbnail_asset', thumbnail_asset.value
  )
  from public.images i
  join public.image_versions v
    on v.id = i.current_version_id and v.image_id = i.id
  join public.users owner_user on owner_user.id = i.owner_user_id
  join public.user_profiles p on p.user_id = i.owner_user_id
  cross join lateral (
    select public.public_delivery_asset_json(a.id, i.owner_user_id) as value
    from public.image_assets a
    where a.image_id = i.id and a.kind = 'display' and a.deleted_at is null
    order by a.created_at desc, a.id
    limit 1
  ) display_asset
  cross join lateral (
    select public.public_delivery_asset_json(a.id, i.owner_user_id) as value
    from public.image_assets a
    where a.image_id = i.id and a.kind = 'thumbnail' and a.deleted_at is null
    order by a.created_at desc, a.id
    limit 1
  ) thumbnail_asset
  where i.id = $1
    and i.deleted_at is null
    and i.processing_status = 'ready'::public.processing_status
    and i.workflow_status = 'approved'::public.workflow_status
    and i.publication_status = 'published'::public.publication_status
    and i.published_at is not null
    and i.unpublished_at is null
    and v.content_category in ('abstract', 'concrete')
    and display_asset.value is not null
    and thumbnail_asset.value is not null
    and owner_user.account_status = 'active'::public.account_status
  limit 1
$$;

create or replace function public.get_public_works(
  target_creator_slug text default null,
  page_limit integer default 100,
  page_offset integer default 0
)
returns jsonb
language plpgsql
stable
security definer
set search_path = ''
as $$
declare
  normalized_slug text := nullif(lower(btrim(coalesce(target_creator_slug, ''))), '');
  total_count integer;
  work_items jsonb;
begin
  if target_creator_slug is not null and (
    normalized_slug is null
    or length(normalized_slug) not between 3 and 64
    or normalized_slug !~ '^[a-z0-9][a-z0-9-]{1,62}[a-z0-9]$'
  ) then
    return jsonb_build_object('items', '[]'::jsonb, 'count', 0);
  end if;
  if page_limit is null or page_limit not between 1 and 100 then
    raise exception 'page_limit must be between 1 and 100' using errcode = '22023';
  end if;
  if page_offset is null or page_offset not between 0 and 10000 then
    raise exception 'page_offset must be between 0 and 10000' using errcode = '22023';
  end if;

  select count(*)::integer
  into total_count
  from public.images i
  join public.user_profiles p on p.user_id = i.owner_user_id
  join public.users u on u.id = i.owner_user_id
  where (normalized_slug is null or p.public_slug = normalized_slug)
    and i.deleted_at is null
    and i.processing_status = 'ready'::public.processing_status
    and i.workflow_status = 'approved'::public.workflow_status
    and i.publication_status = 'published'::public.publication_status
    and i.published_at is not null
    and i.unpublished_at is null
    and u.account_status = 'active'::public.account_status
    and public.public_delivery_work_json(i.id) is not null;

  select coalesce(jsonb_agg(page.work order by page.published_at desc, page.id), '[]'::jsonb)
  into work_items
  from (
    select
      i.id,
      i.published_at,
      public.public_delivery_work_json(i.id) as work
    from public.images i
    join public.user_profiles p on p.user_id = i.owner_user_id
    join public.users u on u.id = i.owner_user_id
    where (normalized_slug is null or p.public_slug = normalized_slug)
      and i.deleted_at is null
      and i.processing_status = 'ready'::public.processing_status
      and i.workflow_status = 'approved'::public.workflow_status
      and i.publication_status = 'published'::public.publication_status
      and i.published_at is not null
      and i.unpublished_at is null
      and u.account_status = 'active'::public.account_status
      and public.public_delivery_work_json(i.id) is not null
    order by i.published_at desc, i.id
    limit page_limit
    offset page_offset
  ) page;

  return jsonb_build_object('items', work_items, 'count', total_count);
end;
$$;

create or replace function public.get_public_creator(target_creator_slug text)
returns jsonb
language plpgsql
stable
security definer
set search_path = ''
as $$
declare
  normalized_slug text := nullif(lower(btrim(coalesce(target_creator_slug, ''))), '');
  profile_row public.user_profiles%rowtype;
  works_result jsonb;
  selected_cover jsonb;
begin
  if normalized_slug is null
     or length(normalized_slug) not between 3 and 64
     or normalized_slug !~ '^[a-z0-9][a-z0-9-]{1,62}[a-z0-9]$' then
    return '{}'::jsonb;
  end if;

  select p.*
  into profile_row
  from public.user_profiles p
  join public.users u on u.id = p.user_id
  where p.public_slug = normalized_slug
    and u.account_status = 'active'::public.account_status
  limit 1;
  if profile_row.user_id is null then
    return '{}'::jsonb;
  end if;

  works_result := public.get_public_works(normalized_slug, 100, 0);
  if coalesce((works_result ->> 'count')::integer, 0) = 0 then
    return '{}'::jsonb;
  end if;

  if profile_row.cover_asset_id is not null then
    selected_cover := public.public_delivery_asset_json(
      profile_row.cover_asset_id,
      profile_row.user_id
    );
  end if;
  if selected_cover is null then
    select public.public_delivery_asset_json(a.id, profile_row.user_id)
    into selected_cover
    from public.images i
    join public.image_assets a
      on a.image_id = i.id and a.kind = 'display' and a.deleted_at is null
    where i.owner_user_id = profile_row.user_id
      and public.public_delivery_asset_json(a.id, profile_row.user_id) is not null
    order by i.published_at desc, i.id, a.id
    limit 1;
  end if;

  return jsonb_build_object(
    'slug', profile_row.public_slug,
    'display_name', profile_row.display_name,
    'professional_headline', case when profile_row.public_fields -> 'professional_headline' = 'true'::jsonb then profile_row.professional_headline end,
    'company', case when profile_row.public_fields -> 'company' = 'true'::jsonb then profile_row.company end,
    'city', case when profile_row.public_fields -> 'city' = 'true'::jsonb then profile_row.city end,
    'country_code', case when profile_row.public_fields -> 'country_code' = 'true'::jsonb then profile_row.country_code end,
    'bio', case when profile_row.public_fields -> 'bio' = 'true'::jsonb then profile_row.bio end,
    'website_url', case when profile_row.public_fields -> 'website_url' = 'true'::jsonb then profile_row.website_url end,
    'availability_status', case when profile_row.public_fields -> 'availability_status' = 'true'::jsonb then profile_row.availability_status end,
    'instagram_url', case when profile_row.public_fields -> 'instagram_url' = 'true'::jsonb then profile_row.instagram_url end,
    'linkedin_url', case when profile_row.public_fields -> 'linkedin_url' = 'true'::jsonb then profile_row.linkedin_url end,
    'avatar_url', case
      when profile_row.public_fields -> 'avatar_url' = 'true'::jsonb
        and profile_row.avatar_url ~ '^https://'
      then profile_row.avatar_url
    end,
    'cover_asset', selected_cover,
    'works', works_result -> 'items',
    'work_count', (works_result ->> 'count')::integer
  );
end;
$$;

create or replace function public.get_my_public_delivery_status()
returns jsonb
language plpgsql
stable
security definer
set search_path = ''
as $$
declare
  app_user_id uuid;
  creator_slug text;
  works_result jsonb;
  published_count integer;
begin
  if public.is_recovery_auth_session() then
    raise exception 'recovery session cannot access public delivery settings' using errcode = '42501';
  end if;
  select public.current_app_user_id() into app_user_id;
  if app_user_id is null or not exists (
    select 1 from public.users u
    where u.id = app_user_id and u.account_status = 'active'::public.account_status
  ) then
    raise exception 'active account required' using errcode = '42501';
  end if;
  if exists (
    select 1 from public.user_roles ur
    where ur.user_id = app_user_id
      and ur.role in ('admin'::public.role_code, 'super_admin'::public.role_code)
  ) and not (select public.has_aal2()) then
    raise exception 'aal2 required for administrator public delivery access' using errcode = '42501';
  end if;

  select p.public_slug into creator_slug
  from public.user_profiles p
  where p.user_id = app_user_id;
  if creator_slug is null then
    raise exception 'profile not initialized' using errcode = 'P0002';
  end if;

  works_result := public.get_public_works(creator_slug, 100, 0);
  published_count := coalesce((works_result ->> 'count')::integer, 0);
  return jsonb_build_object(
    'available', published_count > 0,
    'slug', creator_slug,
    'path', case when published_count > 0 then '/creators/' || creator_slug else null end,
    'published_count', published_count,
    'reason', case when published_count > 0 then null else 'no_published_works' end
  );
end;
$$;

-- Public consumers may not bypass the DTO and select every column of a
-- published image/version row. Owner/reviewer/admin reads continue through the
-- existing scoped RPCs.
drop policy if exists images_public_select on public.images;
drop policy if exists versions_public_select on public.image_versions;
revoke select on public.images from anon, authenticated;
revoke select on public.image_versions from anon, authenticated;
drop view if exists public.public_works;

create or replace function public.can_read_public_storage_object(
  target_bucket text,
  target_key text,
  target_owner text
)
returns boolean
language sql
stable
security definer
set search_path = ''
as $$
  select exists (
    select 1
    from public.image_assets a
    cross join lateral (
      select public.public_delivery_work_json(a.image_id) as value
    ) work
    where a.storage_key = $2
      and a.owner_user_id::text = $3
      and (
        (a.kind = 'display' and $1 = 'image-display')
        or (a.kind = 'thumbnail' and $1 = 'image-thumbnails')
      )
      and public.public_delivery_asset_json(a.id, a.owner_user_id) is not null
      and work.value is not null
      and a.id::text in (
        work.value #>> '{display_asset,id}',
        work.value #>> '{thumbnail_asset,id}'
      )
  )
$$;

drop policy if exists public_derivative_storage_select on storage.objects;
create policy public_derivative_storage_select on storage.objects
for select to anon, authenticated
using (
  (select public.can_read_public_storage_object(
    storage.objects.bucket_id,
    storage.objects.name,
    storage.objects.owner_id
  ))
);

revoke all on function public.public_delivery_ratio_code(integer, integer)
  from public, anon, authenticated, service_role;
revoke all on function public.public_delivery_tags(jsonb)
  from public, anon, authenticated, service_role;
revoke all on function public.public_delivery_exif(jsonb)
  from public, anon, authenticated, service_role;
revoke all on function public.public_delivery_asset_json(uuid, uuid)
  from public, anon, authenticated, service_role;
revoke all on function public.public_delivery_work_json(uuid)
  from public, anon, authenticated, service_role;

revoke all on function public.get_public_works(text, integer, integer)
  from public, anon, authenticated, service_role;
grant execute on function public.get_public_works(text, integer, integer)
  to anon, authenticated;

revoke all on function public.get_public_creator(text)
  from public, anon, authenticated, service_role;
grant execute on function public.get_public_creator(text)
  to anon, authenticated;

revoke all on function public.get_my_public_delivery_status()
  from public, anon, authenticated, service_role;
grant execute on function public.get_my_public_delivery_status()
  to authenticated;

revoke all on function public.can_read_public_storage_object(text, text, text)
  from public, anon, authenticated, service_role;
grant execute on function public.can_read_public_storage_object(text, text, text)
  to anon, authenticated;

commit;
