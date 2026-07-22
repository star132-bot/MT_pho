begin;

-- Creator profile fields and cover selection. Covers intentionally reuse the
-- existing private image pipeline: only current owner assets that completed the
-- trusted scanner may be selected, so profile customization cannot bypass the
-- malware boundary with an unscanned standalone upload.

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

alter table public.user_profiles
  add column if not exists professional_headline text,
  add column if not exists company text,
  add column if not exists city text,
  add column if not exists availability_status public.creator_availability_status
    not null default 'unavailable'::public.creator_availability_status,
  add column if not exists instagram_url text,
  add column if not exists linkedin_url text,
  add column if not exists cover_asset_id uuid;

do $migration$
begin
  if not exists (
    select 1 from pg_catalog.pg_constraint
    where conrelid = 'public.user_profiles'::regclass
      and conname = 'user_profiles_professional_headline_check'
  ) then
    alter table public.user_profiles
      add constraint user_profiles_professional_headline_check check (
        professional_headline is null
        or length(btrim(professional_headline)) between 1 and 160
      );
  end if;
  if not exists (
    select 1 from pg_catalog.pg_constraint
    where conrelid = 'public.user_profiles'::regclass
      and conname = 'user_profiles_company_check'
  ) then
    alter table public.user_profiles
      add constraint user_profiles_company_check check (
        company is null or length(btrim(company)) between 1 and 160
      );
  end if;
  if not exists (
    select 1 from pg_catalog.pg_constraint
    where conrelid = 'public.user_profiles'::regclass
      and conname = 'user_profiles_city_check'
  ) then
    alter table public.user_profiles
      add constraint user_profiles_city_check check (
        city is null or length(btrim(city)) between 1 and 120
      );
  end if;
  if not exists (
    select 1 from pg_catalog.pg_constraint
    where conrelid = 'public.user_profiles'::regclass
      and conname = 'user_profiles_instagram_url_check'
  ) then
    alter table public.user_profiles
      add constraint user_profiles_instagram_url_check check (
        instagram_url is null
        or (
          length(instagram_url) <= 2048
          and instagram_url ~* '^https://(www[.])?instagram[.]com([/?#].*)?$'
          and position(E'\\' in instagram_url) = 0
          and instagram_url !~ '[[:cntrl:]]'
        )
      );
  end if;
  if not exists (
    select 1 from pg_catalog.pg_constraint
    where conrelid = 'public.user_profiles'::regclass
      and conname = 'user_profiles_linkedin_url_check'
  ) then
    alter table public.user_profiles
      add constraint user_profiles_linkedin_url_check check (
        linkedin_url is null
        or (
          length(linkedin_url) <= 2048
          and linkedin_url ~* '^https://(www[.])?linkedin[.]com([/?#].*)?$'
          and position(E'\\' in linkedin_url) = 0
          and linkedin_url !~ '[[:cntrl:]]'
        )
      );
  end if;
  if not exists (
    select 1 from pg_catalog.pg_constraint
    where conrelid = 'public.user_profiles'::regclass
      and conname = 'user_profiles_cover_asset_fk'
  ) then
    alter table public.user_profiles
      add constraint user_profiles_cover_asset_fk
      foreign key (cover_asset_id) references public.image_assets(id) on delete set null;
  end if;
end
$migration$;

create index if not exists user_profiles_cover_asset_idx
  on public.user_profiles (cover_asset_id)
  where cover_asset_id is not null;

drop policy if exists profiles_update_self on public.user_profiles;
revoke update on public.user_profiles from authenticated;

create or replace function public.require_creator_profile_user()
returns uuid
language plpgsql
stable
security definer
set search_path = ''
as $$
declare
  app_user_id uuid;
begin
  if public.is_recovery_auth_session() then
    raise exception 'recovery session cannot access creator profile settings' using errcode = '42501';
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
    raise exception 'aal2 required for administrator creator profile access' using errcode = '42501';
  end if;

  return app_user_id;
end;
$$;
revoke all on function public.require_creator_profile_user()
  from public, anon, authenticated, service_role;

create or replace function public.update_my_profile(profile_patch jsonb)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  app_user_id uuid;
  updated_profile public.user_profiles%rowtype;
  unsupported_fields text;
begin
  app_user_id := public.require_creator_profile_user();

  if profile_patch is null
     or jsonb_typeof(profile_patch) <> 'object'
     or profile_patch = '{}'::jsonb then
    raise exception 'profile_patch must be a non-empty object' using errcode = '22023';
  end if;

  select string_agg(key, ', ' order by key)
    into unsupported_fields
  from jsonb_object_keys(profile_patch) as keys(key)
  where key not in (
    'display_name', 'bio', 'website_url', 'country_code', 'preferred_locale',
    'timezone', 'copyright_name', 'default_license_preference',
    'professional_headline', 'company', 'city', 'availability_status',
    'instagram_url', 'linkedin_url'
  );
  if unsupported_fields is not null then
    raise exception 'unsupported profile fields: %', unsupported_fields using errcode = '22023';
  end if;

  if exists (
    select 1 from jsonb_each(profile_patch) as entries(key, value)
    where jsonb_typeof(value) not in ('string', 'null')
  ) then
    raise exception 'profile values must be strings or null' using errcode = '22023';
  end if;

  if profile_patch ? 'display_name' and (
    jsonb_typeof(profile_patch -> 'display_name') <> 'string'
    or length(btrim(profile_patch ->> 'display_name')) not between 1 and 120
  ) then
    raise exception 'invalid display_name' using errcode = '22023';
  end if;
  if profile_patch ? 'bio'
     and coalesce(length(btrim(profile_patch ->> 'bio')), 0) > 1600 then
    raise exception 'invalid bio' using errcode = '22023';
  end if;
  if profile_patch ? 'website_url'
     and nullif(btrim(profile_patch ->> 'website_url'), '') is not null
     and (
       length(btrim(profile_patch ->> 'website_url')) > 2048
       or btrim(profile_patch ->> 'website_url') !~ '^https://[A-Za-z0-9.-]+(:[0-9]{1,5})?([/?#].*)?$'
       or position(E'\\' in btrim(profile_patch ->> 'website_url')) > 0
       or btrim(profile_patch ->> 'website_url') ~ '[[:cntrl:]]'
     ) then
    raise exception 'invalid website_url' using errcode = '22023';
  end if;
  if profile_patch ? 'country_code'
     and nullif(btrim(profile_patch ->> 'country_code'), '') is not null
     and btrim(profile_patch ->> 'country_code') !~ '^[A-Za-z]{2}$' then
    raise exception 'invalid country_code' using errcode = '22023';
  end if;
  if profile_patch ? 'preferred_locale' and (
    jsonb_typeof(profile_patch -> 'preferred_locale') <> 'string'
    or profile_patch ->> 'preferred_locale' <> 'en'
  ) then
    raise exception 'unsupported preferred_locale' using errcode = '22023';
  end if;
  if profile_patch ? 'timezone' and (
    jsonb_typeof(profile_patch -> 'timezone') <> 'string'
    or not exists (
      select 1 from pg_catalog.pg_timezone_names tz
      where tz.name = profile_patch ->> 'timezone'
    )
  ) then
    raise exception 'invalid timezone' using errcode = '22023';
  end if;
  if profile_patch ? 'copyright_name'
     and coalesce(length(btrim(profile_patch ->> 'copyright_name')), 0) > 160 then
    raise exception 'invalid copyright_name' using errcode = '22023';
  end if;
  if profile_patch ? 'default_license_preference'
     and nullif(btrim(profile_patch ->> 'default_license_preference'), '') is not null
     and btrim(profile_patch ->> 'default_license_preference') not in (
       'all-rights-reserved', 'cc-by-4.0', 'cc-by-sa-4.0',
       'cc-by-nc-4.0', 'cc-by-nc-sa-4.0'
     ) then
    raise exception 'invalid default_license_preference' using errcode = '22023';
  end if;
  if profile_patch ? 'professional_headline'
     and coalesce(length(btrim(profile_patch ->> 'professional_headline')), 0) > 160 then
    raise exception 'invalid professional_headline' using errcode = '22023';
  end if;
  if profile_patch ? 'company'
     and coalesce(length(btrim(profile_patch ->> 'company')), 0) > 160 then
    raise exception 'invalid company' using errcode = '22023';
  end if;
  if profile_patch ? 'city'
     and coalesce(length(btrim(profile_patch ->> 'city')), 0) > 120 then
    raise exception 'invalid city' using errcode = '22023';
  end if;
  if profile_patch ? 'availability_status' and (
    jsonb_typeof(profile_patch -> 'availability_status') <> 'string'
    or profile_patch ->> 'availability_status' not in ('unavailable', 'open', 'limited')
  ) then
    raise exception 'invalid availability_status' using errcode = '22023';
  end if;
  if profile_patch ? 'instagram_url'
     and nullif(btrim(profile_patch ->> 'instagram_url'), '') is not null
     and (
       length(btrim(profile_patch ->> 'instagram_url')) > 2048
       or btrim(profile_patch ->> 'instagram_url') !~* '^https://(www[.])?instagram[.]com([/?#].*)?$'
       or position(E'\\' in btrim(profile_patch ->> 'instagram_url')) > 0
       or btrim(profile_patch ->> 'instagram_url') ~ '[[:cntrl:]]'
     ) then
    raise exception 'invalid instagram_url' using errcode = '22023';
  end if;
  if profile_patch ? 'linkedin_url'
     and nullif(btrim(profile_patch ->> 'linkedin_url'), '') is not null
     and (
       length(btrim(profile_patch ->> 'linkedin_url')) > 2048
       or btrim(profile_patch ->> 'linkedin_url') !~* '^https://(www[.])?linkedin[.]com([/?#].*)?$'
       or position(E'\\' in btrim(profile_patch ->> 'linkedin_url')) > 0
       or btrim(profile_patch ->> 'linkedin_url') ~ '[[:cntrl:]]'
     ) then
    raise exception 'invalid linkedin_url' using errcode = '22023';
  end if;

  update public.user_profiles p set
    display_name = case when profile_patch ? 'display_name'
      then btrim(profile_patch ->> 'display_name') else p.display_name end,
    bio = case when profile_patch ? 'bio'
      then nullif(btrim(profile_patch ->> 'bio'), '') else p.bio end,
    website_url = case when profile_patch ? 'website_url'
      then nullif(btrim(profile_patch ->> 'website_url'), '') else p.website_url end,
    country_code = case when profile_patch ? 'country_code'
      then upper(nullif(btrim(profile_patch ->> 'country_code'), '')) else p.country_code end,
    preferred_locale = case when profile_patch ? 'preferred_locale'
      then profile_patch ->> 'preferred_locale' else p.preferred_locale end,
    timezone = case when profile_patch ? 'timezone'
      then profile_patch ->> 'timezone' else p.timezone end,
    copyright_name = case when profile_patch ? 'copyright_name'
      then nullif(btrim(profile_patch ->> 'copyright_name'), '') else p.copyright_name end,
    default_license_preference = case when profile_patch ? 'default_license_preference'
      then nullif(btrim(profile_patch ->> 'default_license_preference'), '')
      else p.default_license_preference end,
    professional_headline = case when profile_patch ? 'professional_headline'
      then nullif(btrim(profile_patch ->> 'professional_headline'), '')
      else p.professional_headline end,
    company = case when profile_patch ? 'company'
      then nullif(btrim(profile_patch ->> 'company'), '') else p.company end,
    city = case when profile_patch ? 'city'
      then nullif(btrim(profile_patch ->> 'city'), '') else p.city end,
    availability_status = case when profile_patch ? 'availability_status'
      then (profile_patch ->> 'availability_status')::public.creator_availability_status
      else p.availability_status end,
    instagram_url = case when profile_patch ? 'instagram_url'
      then nullif(btrim(profile_patch ->> 'instagram_url'), '') else p.instagram_url end,
    linkedin_url = case when profile_patch ? 'linkedin_url'
      then nullif(btrim(profile_patch ->> 'linkedin_url'), '') else p.linkedin_url end
  where p.user_id = app_user_id
  returning p.* into updated_profile;

  if updated_profile.user_id is null then
    raise exception 'profile not initialized' using errcode = 'P0002';
  end if;

  return jsonb_build_object(
    'display_name', updated_profile.display_name,
    'avatar_url', updated_profile.avatar_url,
    'bio', updated_profile.bio,
    'website_url', updated_profile.website_url,
    'country_code', updated_profile.country_code,
    'preferred_locale', updated_profile.preferred_locale,
    'timezone', updated_profile.timezone,
    'copyright_name', updated_profile.copyright_name,
    'default_license_preference', updated_profile.default_license_preference,
    'professional_headline', updated_profile.professional_headline,
    'company', updated_profile.company,
    'city', updated_profile.city,
    'availability_status', updated_profile.availability_status,
    'instagram_url', updated_profile.instagram_url,
    'linkedin_url', updated_profile.linkedin_url
  );
end;
$$;
revoke all on function public.update_my_profile(jsonb)
  from public, anon, authenticated, service_role;
grant execute on function public.update_my_profile(jsonb) to authenticated;

create or replace function public.creator_profile_cover_asset_json(
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
    'image_id', i.id,
    'title', coalesce(nullif(v.title, ''), i.original_filename),
    'kind', a.kind,
    'storage_bucket', scan_job.storage_bucket,
    'storage_key', a.storage_key,
    'mime_type', a.mime_type,
    'width', a.width,
    'height', a.height,
    'scan_status', a.scan_status,
    'scan_result_code', a.scan_result_code,
    'scan_policy_version', a.scan_policy_version
  )
  from public.image_assets a
  join public.images i
    on i.id = a.image_id and i.owner_user_id = a.owner_user_id
  join public.image_versions v
    on v.id = i.current_version_id and v.image_id = i.id
  join public.asset_scan_jobs scan_job
    on scan_job.asset_id = a.id
  where a.id = target_asset_id
    and a.owner_user_id = expected_owner_id
    and a.kind in ('display', 'thumbnail')
    and a.deleted_at is null
    and a.storage_visibility = 'private'
    and a.scan_status = 'clean'
    and a.scan_result_code = 'clean'
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
$$;
revoke all on function public.creator_profile_cover_asset_json(uuid, uuid)
  from public, anon, authenticated, service_role;

create or replace function public.get_my_profile_cover()
returns jsonb
language plpgsql
stable
security definer
set search_path = ''
as $$
declare
  app_user_id uuid;
  selected_cover jsonb;
  cover_candidates jsonb;
begin
  app_user_id := public.require_creator_profile_user();

  select public.creator_profile_cover_asset_json(p.cover_asset_id, app_user_id)
    into selected_cover
  from public.user_profiles p
  where p.user_id = app_user_id;

  select coalesce(
    jsonb_agg(
      public.creator_profile_cover_asset_json(candidate.asset_id, app_user_id)
      order by candidate.updated_at desc, candidate.kind_order, candidate.asset_id
    ),
    '[]'::jsonb
  )
  into cover_candidates
  from (
    select
      selected_asset.id as asset_id,
      i.updated_at,
      selected_asset.kind_order
    from public.images i
    join public.image_versions v
      on v.id = i.current_version_id and v.image_id = i.id
    join lateral (
      select
        a.id,
        case a.kind when 'display' then 0 else 1 end as kind_order
      from public.image_assets a
      join public.asset_scan_jobs scan_job
        on scan_job.asset_id = a.id
      where a.image_id = i.id
        and a.owner_user_id = app_user_id
        and a.kind in ('display', 'thumbnail')
        and a.deleted_at is null
        and a.storage_visibility = 'private'
        and a.scan_status = 'clean'
        and a.scan_result_code = 'clean'
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
      order by kind_order, a.id
      limit 1
    ) selected_asset on true
    where i.owner_user_id = app_user_id
      and i.deleted_at is null
      and i.processing_status = 'ready'::public.processing_status
    order by i.updated_at desc, selected_asset.kind_order, selected_asset.id
    limit 24
  ) candidate;

  return jsonb_build_object(
    'cover_asset', selected_cover,
    'candidates', cover_candidates
  );
end;
$$;
revoke all on function public.get_my_profile_cover()
  from public, anon, authenticated, service_role;
grant execute on function public.get_my_profile_cover() to authenticated;

create or replace function public.set_my_profile_cover(target_asset_id uuid default null)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  app_user_id uuid;
  selected_cover jsonb;
begin
  app_user_id := public.require_creator_profile_user();

  if target_asset_id is not null then
    selected_cover := public.creator_profile_cover_asset_json(target_asset_id, app_user_id);
    if selected_cover is null then
      return jsonb_build_object(
        'error', jsonb_build_object(
          'code', 'PROFILE_COVER_NOT_AVAILABLE',
          'message', 'Choose one of your current scanner-approved image assets.'
        )
      );
    end if;
  end if;

  update public.user_profiles p
  set cover_asset_id = target_asset_id
  where p.user_id = app_user_id;

  if not found then
    raise exception 'profile not initialized' using errcode = 'P0002';
  end if;

  return jsonb_build_object(
    'cover_asset', selected_cover,
    'saved', true
  );
end;
$$;
revoke all on function public.set_my_profile_cover(uuid)
  from public, anon, authenticated, service_role;
grant execute on function public.set_my_profile_cover(uuid) to authenticated;

commit;
