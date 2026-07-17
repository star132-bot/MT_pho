-- Phase 1B Account Settings hardening for an existing Supabase project.
-- Generic profile UPDATE is replaced by a strict, owner-only RPC.

begin;

drop policy if exists profiles_update_self on public.user_profiles;
revoke update on public.user_profiles from authenticated;

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
  if profile_patch is null
     or jsonb_typeof(profile_patch) <> 'object'
     or profile_patch = '{}'::jsonb then
    raise exception 'profile_patch must be a non-empty object' using errcode = '22023';
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
    raise exception 'aal2 required for administrator profile updates' using errcode = '42501';
  end if;

  select string_agg(key, ', ' order by key)
    into unsupported_fields
  from jsonb_object_keys(profile_patch) as keys(key)
  where key not in (
    'display_name', 'bio', 'website_url', 'country_code', 'preferred_locale',
    'timezone', 'copyright_name', 'default_license_preference'
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
      else p.default_license_preference end
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
    'default_license_preference', updated_profile.default_license_preference
  );
end;
$$;

grant execute on function public.update_my_profile(jsonb) to authenticated;
revoke all on function public.update_my_profile(jsonb) from anon, public;

commit;
