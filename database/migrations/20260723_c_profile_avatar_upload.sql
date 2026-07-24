-- Owner-scoped profile avatar uploads with stable private Storage locators.
-- Signed URLs are presentation data and are never persisted in user_profiles.

begin;

alter table public.user_profiles
  add column if not exists avatar_storage_bucket text,
  add column if not exists avatar_storage_key text,
  add column if not exists avatar_mime_type text,
  add column if not exists avatar_byte_size bigint,
  add column if not exists avatar_width integer,
  add column if not exists avatar_height integer,
  add column if not exists avatar_updated_at timestamptz;

do $migration$
begin
  if not exists (
    select 1
    from pg_catalog.pg_constraint
    where conrelid = 'public.user_profiles'::regclass
      and conname = 'user_profiles_avatar_storage_metadata_check'
  ) then
    alter table public.user_profiles
      add constraint user_profiles_avatar_storage_metadata_check check (
        (
          avatar_storage_bucket is null
          and avatar_storage_key is null
          and avatar_mime_type is null
          and avatar_byte_size is null
          and avatar_width is null
          and avatar_height is null
        )
        or (
          avatar_storage_bucket = 'profile-avatars'
          and avatar_storage_key ~ (
            '^' || user_id::text ||
            '/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/avatar[.]jpg$'
          )
          and avatar_mime_type = 'image/jpeg'
          and avatar_byte_size between 1 and 1048576
          and avatar_width = 512
          and avatar_height = 512
        )
      );
  end if;
end
$migration$;

create unique index if not exists user_profiles_avatar_storage_key_key
  on public.user_profiles (avatar_storage_key)
  where avatar_storage_key is not null;

create table if not exists public.profile_avatar_upload_intents (
  id uuid primary key default gen_random_uuid(),
  owner_user_id uuid not null references public.users(id) on delete cascade,
  status text not null default 'issued'
    check (status in ('issued', 'completed', 'canceled', 'expired')),
  storage_bucket text not null default 'profile-avatars'
    check (storage_bucket = 'profile-avatars'),
  storage_key text not null unique,
  mime_type text not null check (mime_type = 'image/jpeg'),
  byte_size bigint not null check (byte_size between 1 and 1048576),
  width integer not null check (width = 512),
  height integer not null check (height = 512),
  previous_storage_bucket text,
  previous_storage_key text,
  previous_mime_type text,
  previous_byte_size bigint,
  previous_width integer,
  previous_height integer,
  expires_at timestamptz not null default (now() + interval '15 minutes'),
  completed_at timestamptz,
  canceled_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  check (
    storage_key ~ (
      '^' || owner_user_id::text || '/' || id::text || '/avatar[.]jpg$'
    )
  ),
  check (expires_at > created_at),
  check ((status = 'completed') = (completed_at is not null)),
  check ((status = 'canceled') = (canceled_at is not null)),
  check (
    (
      previous_storage_bucket is null
      and previous_storage_key is null
      and previous_mime_type is null
      and previous_byte_size is null
      and previous_width is null
      and previous_height is null
    )
    or (
      status = 'completed'
      and previous_storage_bucket = 'profile-avatars'
      and previous_storage_key ~ (
        '^' || owner_user_id::text ||
        '/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/avatar[.]jpg$'
      )
      and previous_mime_type = 'image/jpeg'
      and previous_byte_size between 1 and 1048576
      and previous_width = 512
      and previous_height = 512
    )
  )
);

create unique index if not exists profile_avatar_upload_intents_owner_issued_key
  on public.profile_avatar_upload_intents (owner_user_id)
  where status = 'issued';
create index if not exists profile_avatar_upload_intents_owner_created_idx
  on public.profile_avatar_upload_intents (owner_user_id, created_at desc);
create index if not exists profile_avatar_upload_intents_expiry_idx
  on public.profile_avatar_upload_intents (expires_at)
  where status = 'issued';

alter table public.profile_avatar_upload_intents enable row level security;
revoke all on table public.profile_avatar_upload_intents
  from public, anon, authenticated, service_role;
grant select on table public.profile_avatar_upload_intents to authenticated;

drop policy if exists profile_avatar_upload_intents_owner_select
  on public.profile_avatar_upload_intents;
create policy profile_avatar_upload_intents_owner_select
on public.profile_avatar_upload_intents
for select to authenticated
using (owner_user_id = (select public.current_app_user_id()));

insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values (
  'profile-avatars',
  'profile-avatars',
  false,
  1048576,
  array['image/jpeg']
)
on conflict (id) do update set
  public = excluded.public,
  file_size_limit = excluded.file_size_limit,
  allowed_mime_types = excluded.allowed_mime_types;

create or replace function public.is_profile_avatar_upload_target(
  target_bucket text,
  target_name text
)
returns boolean
language sql
stable
security definer
set search_path = ''
as $$
  select exists (
    select 1
    from public.profile_avatar_upload_intents intent
    join public.users account on account.id = intent.owner_user_id
    where intent.owner_user_id = (select auth.uid())
      and account.account_status = 'active'::public.account_status
      and intent.status = 'issued'
      and intent.expires_at > now()
      and intent.storage_bucket = target_bucket
      and intent.storage_key = target_name
      and target_bucket = 'profile-avatars'
      and target_name ~ (
        '^' || intent.owner_user_id::text || '/' || intent.id::text || '/avatar[.]jpg$'
      )
  )
$$;

create or replace function public.is_public_profile_avatar_object(
  target_bucket text,
  target_name text,
  target_owner_id text
)
returns boolean
language sql
stable
security definer
set search_path = ''
as $$
  select exists (
    select 1
    from public.user_profiles profile
    join public.users account on account.id = profile.user_id
    where account.account_status = 'active'::public.account_status
      and profile.public_fields -> 'avatar_url' = 'true'::jsonb
      and profile.avatar_storage_bucket = 'profile-avatars'
      and profile.avatar_storage_bucket = target_bucket
      and profile.avatar_storage_key = target_name
      and profile.user_id::text = target_owner_id
      and profile.avatar_mime_type = 'image/jpeg'
      and profile.avatar_byte_size between 1 and 1048576
      and profile.avatar_width = 512
      and profile.avatar_height = 512
  )
$$;

revoke all on function public.is_profile_avatar_upload_target(text, text)
  from public, anon, authenticated, service_role;
grant execute on function public.is_profile_avatar_upload_target(text, text)
  to authenticated;
revoke all on function public.is_public_profile_avatar_object(text, text, text)
  from public, anon, authenticated, service_role;
grant execute on function public.is_public_profile_avatar_object(text, text, text)
  to anon, authenticated;

drop policy if exists profile_avatar_owner_insert on storage.objects;
create policy profile_avatar_owner_insert
on storage.objects
for insert to authenticated
with check (
  bucket_id = 'profile-avatars'
  and (storage.foldername(name))[1] = (select auth.uid())::text
  and (select public.is_profile_avatar_upload_target(bucket_id, name))
);

drop policy if exists profile_avatar_owner_select on storage.objects;
create policy profile_avatar_owner_select
on storage.objects
for select to authenticated
using (
  bucket_id = 'profile-avatars'
  and owner_id = (select auth.uid())::text
  and (storage.foldername(name))[1] = (select auth.uid())::text
);

drop policy if exists profile_avatar_owner_delete on storage.objects;
create policy profile_avatar_owner_delete
on storage.objects
for delete to authenticated
using (
  bucket_id = 'profile-avatars'
  and owner_id = (select auth.uid())::text
  and (storage.foldername(name))[1] = (select auth.uid())::text
);

drop policy if exists profile_avatar_public_current_select on storage.objects;
create policy profile_avatar_public_current_select
on storage.objects
for select to anon, authenticated
using (
  bucket_id = 'profile-avatars'
  and (select public.is_public_profile_avatar_object(bucket_id, name, owner_id))
);

create or replace function public.create_my_profile_avatar_upload(
  avatar_mime_type text,
  avatar_byte_size bigint,
  avatar_width integer,
  avatar_height integer
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  app_user_id uuid;
  locked_profile_id uuid;
  intent_id uuid := gen_random_uuid();
  intent_key text;
  normalized_mime_type text := lower(coalesce(btrim(avatar_mime_type), ''));
  intent_row public.profile_avatar_upload_intents%rowtype;
  superseded_uploads jsonb;
begin
  app_user_id := public.require_creator_profile_user();

  if normalized_mime_type <> 'image/jpeg'
     or avatar_byte_size is null
     or avatar_byte_size not between 1 and 1048576
     or avatar_width is distinct from 512
     or avatar_height is distinct from 512 then
    return jsonb_build_object(
      'error', jsonb_build_object(
        'code', 'PROFILE_AVATAR_UPLOAD_INVALID',
        'message', 'Use a 512 by 512 JPEG no larger than 1 MiB.'
      )
    );
  end if;

  select profile.user_id
  into locked_profile_id
  from public.user_profiles profile
  where profile.user_id = app_user_id
  for update;
  if locked_profile_id is null then
    return jsonb_build_object(
      'error', jsonb_build_object(
        'code', 'PROFILE_AVATAR_PROFILE_UNAVAILABLE',
        'message', 'The profile is unavailable.'
      )
    );
  end if;

  select coalesce(
    jsonb_agg(
      jsonb_build_object(
        'upload_id', intent.id,
        'storage_bucket', intent.storage_bucket,
        'storage_key', intent.storage_key
      )
      order by intent.created_at, intent.id
    ),
    '[]'::jsonb
  )
  into superseded_uploads
  from public.profile_avatar_upload_intents intent
  where intent.owner_user_id = app_user_id
    and intent.status = 'issued';

  update public.profile_avatar_upload_intents intent
  set
    status = case when intent.expires_at <= now() then 'expired' else 'canceled' end,
    canceled_at = case when intent.expires_at > now() then now() else null end,
    updated_at = now()
  where intent.owner_user_id = app_user_id
    and intent.status = 'issued';

  intent_key := app_user_id::text || '/' || intent_id::text || '/avatar.jpg';
  insert into public.profile_avatar_upload_intents (
    id,
    owner_user_id,
    storage_bucket,
    storage_key,
    mime_type,
    byte_size,
    width,
    height
  ) values (
    intent_id,
    app_user_id,
    'profile-avatars',
    intent_key,
    normalized_mime_type,
    avatar_byte_size,
    avatar_width,
    avatar_height
  )
  returning * into intent_row;

  return jsonb_build_object(
    'upload_id', intent_row.id,
    'storage_bucket', intent_row.storage_bucket,
    'storage_key', intent_row.storage_key,
    'mime_type', intent_row.mime_type,
    'byte_size', intent_row.byte_size,
    'width', intent_row.width,
    'height', intent_row.height,
    'expires_at', intent_row.expires_at,
    'superseded_uploads', superseded_uploads
  );
end;
$$;

create or replace function public.complete_my_profile_avatar_upload(upload_id uuid)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  app_user_id uuid;
  profile_row public.user_profiles%rowtype;
  intent_row public.profile_avatar_upload_intents%rowtype;
  object_matches boolean;
  previous_avatar jsonb;
begin
  app_user_id := public.require_creator_profile_user();

  select profile.*
  into profile_row
  from public.user_profiles profile
  where profile.user_id = app_user_id
  for update;
  if profile_row.user_id is null then
    return jsonb_build_object(
      'error', jsonb_build_object(
        'code', 'PROFILE_AVATAR_PROFILE_UNAVAILABLE',
        'message', 'The profile is unavailable.'
      )
    );
  end if;

  select intent.*
  into intent_row
  from public.profile_avatar_upload_intents intent
  where intent.id = upload_id
    and intent.owner_user_id = app_user_id
  for update;
  if intent_row.id is null then
    return jsonb_build_object(
      'error', jsonb_build_object(
        'code', 'PROFILE_AVATAR_UPLOAD_NOT_FOUND',
        'message', 'The avatar upload is unavailable.'
      )
    );
  end if;

  if intent_row.status = 'completed' then
    if profile_row.avatar_storage_key is distinct from intent_row.storage_key then
      return jsonb_build_object(
        'error', jsonb_build_object(
          'code', 'PROFILE_AVATAR_UPLOAD_SUPERSEDED',
          'message', 'A newer avatar is already active.'
        )
      );
    end if;
    previous_avatar := case
      when intent_row.previous_storage_key is null then null
      else jsonb_build_object(
        'storage_bucket', intent_row.previous_storage_bucket,
        'storage_key', intent_row.previous_storage_key,
        'mime_type', intent_row.previous_mime_type,
        'byte_size', intent_row.previous_byte_size,
        'width', intent_row.previous_width,
        'height', intent_row.previous_height
      )
    end;
    return jsonb_build_object(
      'avatar', jsonb_build_object(
        'storage_bucket', intent_row.storage_bucket,
        'storage_key', intent_row.storage_key,
        'mime_type', intent_row.mime_type,
        'byte_size', intent_row.byte_size,
        'width', intent_row.width,
        'height', intent_row.height,
        'updated_at', intent_row.completed_at
      ),
      'previous_avatar', previous_avatar,
      'replayed', true
    );
  end if;

  if intent_row.status <> 'issued' then
    return jsonb_build_object(
      'error', jsonb_build_object(
        'code', 'PROFILE_AVATAR_UPLOAD_INACTIVE',
        'message', 'The avatar upload is no longer active.'
      )
    );
  end if;
  if intent_row.expires_at <= now() then
    update public.profile_avatar_upload_intents
    set status = 'expired', updated_at = now()
    where id = intent_row.id;
    return jsonb_build_object(
      'error', jsonb_build_object(
        'code', 'PROFILE_AVATAR_UPLOAD_EXPIRED',
        'message', 'The avatar upload has expired.'
      )
    );
  end if;

  select exists (
    select 1
    from storage.objects object
    where object.bucket_id = intent_row.storage_bucket
      and object.name = intent_row.storage_key
      and object.owner_id = app_user_id::text
      and lower(coalesce(object.metadata ->> 'mimetype', '')) = intent_row.mime_type
      and coalesce(object.metadata ->> 'size', '') = intent_row.byte_size::text
  )
  into object_matches;
  if not object_matches then
    return jsonb_build_object(
      'error', jsonb_build_object(
        'code', 'PROFILE_AVATAR_UPLOAD_INCOMPLETE',
        'message', 'The uploaded avatar is missing or does not match the upload intent.'
      )
    );
  end if;

  previous_avatar := case
    when profile_row.avatar_storage_key is null then null
    else jsonb_build_object(
      'storage_bucket', profile_row.avatar_storage_bucket,
      'storage_key', profile_row.avatar_storage_key,
      'mime_type', profile_row.avatar_mime_type,
      'byte_size', profile_row.avatar_byte_size,
      'width', profile_row.avatar_width,
      'height', profile_row.avatar_height
    )
  end;

  update public.user_profiles profile
  set
    avatar_url = null,
    avatar_storage_bucket = intent_row.storage_bucket,
    avatar_storage_key = intent_row.storage_key,
    avatar_mime_type = intent_row.mime_type,
    avatar_byte_size = intent_row.byte_size,
    avatar_width = intent_row.width,
    avatar_height = intent_row.height,
    avatar_updated_at = now()
  where profile.user_id = app_user_id;

  update public.profile_avatar_upload_intents intent
  set
    status = 'completed',
    previous_storage_bucket = profile_row.avatar_storage_bucket,
    previous_storage_key = profile_row.avatar_storage_key,
    previous_mime_type = profile_row.avatar_mime_type,
    previous_byte_size = profile_row.avatar_byte_size,
    previous_width = profile_row.avatar_width,
    previous_height = profile_row.avatar_height,
    completed_at = now(),
    updated_at = now()
  where intent.id = intent_row.id
  returning * into intent_row;

  return jsonb_build_object(
    'avatar', jsonb_build_object(
      'storage_bucket', intent_row.storage_bucket,
      'storage_key', intent_row.storage_key,
      'mime_type', intent_row.mime_type,
      'byte_size', intent_row.byte_size,
      'width', intent_row.width,
      'height', intent_row.height,
      'updated_at', intent_row.completed_at
    ),
    'previous_avatar', previous_avatar,
    'replayed', false
  );
end;
$$;

create or replace function public.cancel_my_profile_avatar_upload(upload_id uuid)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  app_user_id uuid;
  locked_profile_id uuid;
  intent_row public.profile_avatar_upload_intents%rowtype;
begin
  app_user_id := public.require_creator_profile_user();

  select profile.user_id
  into locked_profile_id
  from public.user_profiles profile
  where profile.user_id = app_user_id
  for update;
  if locked_profile_id is null then
    return jsonb_build_object(
      'error', jsonb_build_object(
        'code', 'PROFILE_AVATAR_PROFILE_UNAVAILABLE',
        'message', 'The profile is unavailable.'
      )
    );
  end if;

  select intent.*
  into intent_row
  from public.profile_avatar_upload_intents intent
  where intent.id = upload_id
    and intent.owner_user_id = app_user_id
  for update;
  if intent_row.id is null then
    return jsonb_build_object(
      'error', jsonb_build_object(
        'code', 'PROFILE_AVATAR_UPLOAD_NOT_FOUND',
        'message', 'The avatar upload is unavailable.'
      )
    );
  end if;
  if intent_row.status = 'completed' then
    return jsonb_build_object(
      'error', jsonb_build_object(
        'code', 'PROFILE_AVATAR_UPLOAD_COMPLETED',
        'message', 'The active avatar cannot be canceled.'
      )
    );
  end if;

  if intent_row.status = 'issued' then
    update public.profile_avatar_upload_intents intent
    set
      status = case when intent.expires_at <= now() then 'expired' else 'canceled' end,
      canceled_at = case when intent.expires_at > now() then now() else null end,
      updated_at = now()
    where intent.id = intent_row.id
    returning * into intent_row;
  end if;

  return jsonb_build_object(
    'canceled', true,
    'status', intent_row.status,
    'upload', jsonb_build_object(
      'upload_id', intent_row.id,
      'storage_bucket', intent_row.storage_bucket,
      'storage_key', intent_row.storage_key
    )
  );
end;
$$;

create or replace function public.remove_my_profile_avatar()
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  app_user_id uuid;
  profile_row public.user_profiles%rowtype;
  previous_avatar jsonb;
  canceled_uploads jsonb;
  removed_avatar boolean;
begin
  app_user_id := public.require_creator_profile_user();

  select profile.*
  into profile_row
  from public.user_profiles profile
  where profile.user_id = app_user_id
  for update;
  if profile_row.user_id is null then
    return jsonb_build_object(
      'error', jsonb_build_object(
        'code', 'PROFILE_AVATAR_PROFILE_UNAVAILABLE',
        'message', 'The profile is unavailable.'
      )
    );
  end if;

  select coalesce(
    jsonb_agg(
      jsonb_build_object(
        'upload_id', intent.id,
        'storage_bucket', intent.storage_bucket,
        'storage_key', intent.storage_key
      )
      order by intent.created_at, intent.id
    ),
    '[]'::jsonb
  )
  into canceled_uploads
  from public.profile_avatar_upload_intents intent
  where intent.owner_user_id = app_user_id
    and intent.status = 'issued';

  update public.profile_avatar_upload_intents intent
  set
    status = case when intent.expires_at <= now() then 'expired' else 'canceled' end,
    canceled_at = case when intent.expires_at > now() then now() else null end,
    updated_at = now()
  where intent.owner_user_id = app_user_id
    and intent.status = 'issued';

  previous_avatar := case
    when profile_row.avatar_storage_key is null then null
    else jsonb_build_object(
      'storage_bucket', profile_row.avatar_storage_bucket,
      'storage_key', profile_row.avatar_storage_key,
      'mime_type', profile_row.avatar_mime_type,
      'byte_size', profile_row.avatar_byte_size,
      'width', profile_row.avatar_width,
      'height', profile_row.avatar_height
    )
  end;
  removed_avatar := profile_row.avatar_storage_key is not null
    or profile_row.avatar_url is not null;

  update public.user_profiles profile
  set
    avatar_url = null,
    avatar_storage_bucket = null,
    avatar_storage_key = null,
    avatar_mime_type = null,
    avatar_byte_size = null,
    avatar_width = null,
    avatar_height = null,
    avatar_updated_at = now()
  where profile.user_id = app_user_id;

  return jsonb_build_object(
    'removed', removed_avatar,
    'previous_avatar', previous_avatar,
    'canceled_uploads', canceled_uploads
  );
end;
$$;

create or replace function public.get_public_creator_avatar(target_creator_slug text)
returns jsonb
language plpgsql
stable
security definer
set search_path = ''
as $$
declare
  normalized_slug text := lower(coalesce(btrim(target_creator_slug), ''));
  avatar_result jsonb;
begin
  if length(normalized_slug) > 96
     or normalized_slug !~ '^[a-z0-9]([a-z0-9-]{0,94}[a-z0-9])?$' then
    return '{}'::jsonb;
  end if;

  select jsonb_build_object(
    'owner_user_id', profile.user_id,
    'storage_bucket', profile.avatar_storage_bucket,
    'storage_key', profile.avatar_storage_key,
    'mime_type', profile.avatar_mime_type,
    'byte_size', profile.avatar_byte_size,
    'width', profile.avatar_width,
    'height', profile.avatar_height,
    'updated_at', profile.avatar_updated_at
  )
  into avatar_result
  from public.user_profiles profile
  join public.users account on account.id = profile.user_id
  join storage.objects object
    on object.bucket_id = profile.avatar_storage_bucket
   and object.name = profile.avatar_storage_key
   and object.owner_id = profile.user_id::text
  where profile.public_slug = normalized_slug
    and account.account_status = 'active'::public.account_status
    and profile.avatar_storage_bucket = 'profile-avatars'
    and profile.avatar_mime_type = 'image/jpeg'
    and profile.avatar_byte_size between 1 and 1048576
    and profile.avatar_width = 512
    and profile.avatar_height = 512
    and lower(coalesce(object.metadata ->> 'mimetype', '')) = profile.avatar_mime_type
    and coalesce(object.metadata ->> 'size', '') = profile.avatar_byte_size::text
    and public.is_public_profile_avatar_object(
      object.bucket_id,
      object.name,
      object.owner_id
    )
  limit 1;

  return coalesce(avatar_result, '{}'::jsonb);
end;
$$;

revoke all on function public.create_my_profile_avatar_upload(text, bigint, integer, integer)
  from public, anon, authenticated, service_role;
grant execute on function public.create_my_profile_avatar_upload(text, bigint, integer, integer)
  to authenticated;
revoke all on function public.complete_my_profile_avatar_upload(uuid)
  from public, anon, authenticated, service_role;
grant execute on function public.complete_my_profile_avatar_upload(uuid)
  to authenticated;
revoke all on function public.cancel_my_profile_avatar_upload(uuid)
  from public, anon, authenticated, service_role;
grant execute on function public.cancel_my_profile_avatar_upload(uuid)
  to authenticated;
revoke all on function public.remove_my_profile_avatar()
  from public, anon, authenticated, service_role;
grant execute on function public.remove_my_profile_avatar()
  to authenticated;
revoke all on function public.get_public_creator_avatar(text)
  from public, anon, authenticated, service_role;
grant execute on function public.get_public_creator_avatar(text)
  to anon, authenticated;

commit;
