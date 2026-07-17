-- Phase 1: Supabase Auth identity mapping, owner isolation, RBAC and MFA gates.
-- Run after database/product_schema.sql in a Supabase PostgreSQL project.

-- Supabase Auth UUID is the business user UUID. This makes auth.uid() joins
-- explicit and prevents a second mutable identity mapping.
create or replace function public.handle_new_auth_user()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
  insert into public.users (
    id, auth_subject, email, email_verified_at, account_status, created_at, updated_at
  ) values (
    new.id,
    new.id::text,
    new.email,
    new.email_confirmed_at,
    case when new.email_confirmed_at is null
      then 'pending_verification'::public.account_status
      else 'active'::public.account_status
    end,
    coalesce(new.created_at, now()),
    now()
  )
  on conflict (id) do update set
    email = excluded.email,
    email_verified_at = excluded.email_verified_at,
    account_status = case
      when public.users.account_status = 'pending_verification'
       and excluded.email_verified_at is not null then 'active'::public.account_status
      else public.users.account_status
    end,
    updated_at = now();

  insert into public.user_profiles (user_id, display_name)
  values (new.id, coalesce(nullif(trim(new.raw_user_meta_data ->> 'display_name'), ''), 'Member'))
  on conflict (user_id) do nothing;

  insert into public.user_roles (user_id, role, assigned_by, reason)
  values (new.id, 'user'::public.role_code, null, 'Default role assigned at registration')
  on conflict (user_id, role) do nothing;

  return new;
end;
$$;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created
after insert or update of email, email_confirmed_at on auth.users
for each row execute function public.handle_new_auth_user();

revoke all on function public.handle_new_auth_user() from public, anon, authenticated;

create or replace function public.current_app_user_id()
returns uuid
language sql
stable
security definer
set search_path = ''
as $$
  select u.id
  from public.users u
  where u.id = (select auth.uid())
    and u.auth_subject = (select auth.uid())::text
  limit 1
$$;

create or replace function public.has_any_role(required_roles public.role_code[])
returns boolean
language sql
stable
security definer
set search_path = ''
as $$
  select exists (
    select 1
    from public.user_roles ur
    join public.users u on u.id = ur.user_id
    where ur.user_id = (select public.current_app_user_id())
      and ur.role = any(required_roles)
      and u.account_status = 'active'::public.account_status
  )
$$;

create or replace function public.has_aal2()
returns boolean
language sql
stable
set search_path = ''
as $$
  select coalesce((select auth.jwt() ->> 'aal') = 'aal2', false)
$$;

create or replace function public.current_authorization()
returns jsonb
language sql
stable
security definer
set search_path = ''
as $$
  select jsonb_build_object(
    'user_id', (select public.current_app_user_id()),
    'account_status', (
      select u.account_status
      from public.users u
      where u.id = (select public.current_app_user_id())
    ),
    'roles', coalesce((
      select jsonb_agg(ur.role order by ur.role)
      from public.user_roles ur
      where ur.user_id = (select public.current_app_user_id())
    ), '[]'::jsonb),
    'aal', coalesce((select auth.jwt() ->> 'aal'), 'aal1')
  )
$$;

grant execute on function public.current_app_user_id() to authenticated;
grant execute on function public.has_any_role(public.role_code[]) to authenticated;
grant execute on function public.has_aal2() to authenticated;
grant execute on function public.current_authorization() to authenticated;
revoke all on function public.current_app_user_id() from anon;
revoke all on function public.has_any_role(public.role_code[]) from anon;
revoke all on function public.has_aal2() from anon;
revoke all on function public.current_authorization() from anon;

alter table public.users enable row level security;
alter table public.user_profiles enable row level security;
alter table public.user_roles enable row level security;
alter table public.folders enable row level security;
alter table public.images enable row level security;
alter table public.image_versions enable row level security;
alter table public.image_assets enable row level security;
alter table public.review_submissions enable row level security;
alter table public.review_decisions enable row level security;
alter table public.notifications enable row level security;
alter table public.takedown_cases enable row level security;
alter table public.audit_logs enable row level security;

-- Identity and profile. Users may not change account status or roles directly.
create policy users_read_self on public.users
for select to authenticated
using (id = (select public.current_app_user_id()));

create policy profiles_read_self on public.user_profiles
for select to authenticated
using (user_id = (select public.current_app_user_id()));

-- Profile writes use a strict RPC so row ownership alone cannot be used to
-- bypass field, account-state, or administrator AAL validation through the
-- generic PostgREST table endpoint.
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

create policy roles_read_self on public.user_roles
for select to authenticated
using (user_id = (select public.current_app_user_id()));

-- Owner Workspace policies.
create policy folders_owner_select on public.folders
for select to authenticated
using (owner_user_id = (select public.current_app_user_id()));
create policy folders_owner_insert on public.folders
for insert to authenticated
with check (owner_user_id = (select public.current_app_user_id()));
create policy folders_owner_update on public.folders
for update to authenticated
using (owner_user_id = (select public.current_app_user_id()))
with check (owner_user_id = (select public.current_app_user_id()));

create policy images_owner_select on public.images
for select to authenticated
using (owner_user_id = (select public.current_app_user_id()));
create policy images_owner_insert on public.images
for insert to authenticated
with check (owner_user_id = (select public.current_app_user_id()));
create policy images_owner_update on public.images
for update to authenticated
using (owner_user_id = (select public.current_app_user_id()))
with check (owner_user_id = (select public.current_app_user_id()));

create policy versions_owner_select on public.image_versions
for select to authenticated
using (exists (
  select 1 from public.images i
  where i.id = image_id and i.owner_user_id = (select public.current_app_user_id())
));
create policy versions_owner_insert on public.image_versions
for insert to authenticated
with check (
  created_by_user_id = (select public.current_app_user_id())
  and exists (
    select 1 from public.images i
    where i.id = image_id and i.owner_user_id = (select public.current_app_user_id())
  )
);

create policy assets_owner_select on public.image_assets
for select to authenticated
using (owner_user_id = (select public.current_app_user_id()));
create policy assets_owner_insert on public.image_assets
for insert to authenticated
with check (owner_user_id = (select public.current_app_user_id()));

create policy submissions_owner_select on public.review_submissions
for select to authenticated
using (submitted_by_user_id = (select public.current_app_user_id()));
create policy submissions_owner_insert on public.review_submissions
for insert to authenticated
with check (
  submitted_by_user_id = (select public.current_app_user_id())
  and exists (
    select 1 from public.images i
    where i.id = image_id and i.owner_user_id = (select public.current_app_user_id())
  )
);

create policy notifications_owner_select on public.notifications
for select to authenticated
using (recipient_user_id = (select public.current_app_user_id()));
create policy notifications_owner_update on public.notifications
for update to authenticated
using (recipient_user_id = (select public.current_app_user_id()))
with check (recipient_user_id = (select public.current_app_user_id()));

create policy audit_owner_activity_select on public.audit_logs
for select to authenticated
using (actor_user_id = (select public.current_app_user_id()));

-- Reviewer scope. Decisions remain append-only because product_schema.sql
-- rejects UPDATE/DELETE, while inserts are constrained to the current actor.
create policy reviewer_submissions_select on public.review_submissions
for select to authenticated
using ((select public.has_any_role(array['reviewer','admin','super_admin']::public.role_code[])));

create policy reviewer_decisions_select on public.review_decisions
for select to authenticated
using (
  reviewer_id = (select public.current_app_user_id())
  or (select public.has_any_role(array['admin','super_admin']::public.role_code[]))
);

create policy reviewer_decisions_insert on public.review_decisions
for insert to authenticated
with check (
  reviewer_id = (select public.current_app_user_id())
  and (select public.has_any_role(array['reviewer','admin','super_admin']::public.role_code[]))
);

-- Admin read scope requires MFA. Mutations are intentionally exposed only
-- through audited server RPC/API operations, not generic table UPDATE/DELETE.
create policy admin_users_select on public.users
for select to authenticated
using (
  (select public.has_any_role(array['admin','super_admin']::public.role_code[]))
  and (select public.has_aal2())
);
create policy admin_profiles_select on public.user_profiles
for select to authenticated
using (
  (select public.has_any_role(array['admin','super_admin']::public.role_code[]))
  and (select public.has_aal2())
);
create policy admin_roles_select on public.user_roles
for select to authenticated
using (
  (select public.has_any_role(array['admin','super_admin']::public.role_code[]))
  and (select public.has_aal2())
);
create policy admin_images_select on public.images
for select to authenticated
using (
  (select public.has_any_role(array['admin','super_admin']::public.role_code[]))
  and (select public.has_aal2())
);
create policy admin_versions_select on public.image_versions
for select to authenticated
using (
  (select public.has_any_role(array['admin','super_admin']::public.role_code[]))
  and (select public.has_aal2())
);
create policy admin_assets_select on public.image_assets
for select to authenticated
using (
  (select public.has_any_role(array['admin','super_admin']::public.role_code[]))
  and (select public.has_aal2())
);
create policy admin_takedowns_select on public.takedown_cases
for select to authenticated
using (
  (select public.has_any_role(array['admin','super_admin']::public.role_code[]))
  and (select public.has_aal2())
);
create policy admin_audit_select on public.audit_logs
for select to authenticated
using (
  (select public.has_any_role(array['admin','super_admin']::public.role_code[]))
  and (select public.has_aal2())
);

-- Public Works defense in depth. Only the published current version is public.
create policy images_public_select on public.images
for select to anon, authenticated
using (publication_status = 'published' and deleted_at is null);
create policy versions_public_select on public.image_versions
for select to anon, authenticated
using (exists (
  select 1 from public.images i
  where i.current_version_id = id
    and i.publication_status = 'published'
    and i.deleted_at is null
));

-- PostgreSQL 15+ makes the view obey underlying RLS.
alter view public.public_works set (security_invoker = true);
grant select on public.public_works to anon, authenticated;

-- Private storage objects are namespaced by auth user UUID. Bucket creation,
-- MIME/size limits and image processing are Phase 2 deployment steps.
create policy storage_owner_insert on storage.objects
for insert to authenticated
with check (
  bucket_id in ('image-originals', 'image-display', 'image-thumbnails')
  and (storage.foldername(name))[1] = (select auth.uid())::text
);
create policy storage_owner_select on storage.objects
for select to authenticated
using (
  bucket_id in ('image-originals', 'image-display', 'image-thumbnails')
  and owner_id = (select auth.uid()::text)
);

-- Role assignment has no authenticated INSERT/UPDATE/DELETE policy. Super
-- Admin role changes must use a service-side audited transaction in Phase 4.
