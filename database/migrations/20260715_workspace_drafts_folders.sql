-- Phase 2A: owner-scoped folders, signed upload intents, and server drafts.
begin;

create table if not exists public.upload_intents (
  id uuid primary key default gen_random_uuid(),
  owner_user_id uuid not null references public.users(id) on delete restrict,
  image_id uuid not null unique default gen_random_uuid(),
  folder_id uuid references public.folders(id) on delete restrict,
  status text not null default 'issued' check (status in ('issued', 'completed', 'expired', 'canceled')),
  original_filename text not null,
  original_width integer not null check (original_width > 0),
  original_height integer not null check (original_height > 0),
  checksum_sha256 char(64) not null,
  expected_assets jsonb not null check (jsonb_typeof(expected_assets) = 'array'),
  expires_at timestamptz not null default (now() + interval '2 hours'),
  completed_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index if not exists upload_intents_owner_status_idx
  on public.upload_intents (owner_user_id, status, created_at desc);

alter table public.upload_intents enable row level security;
drop policy if exists upload_intents_owner_select on public.upload_intents;
create policy upload_intents_owner_select on public.upload_intents
for select to authenticated
using (owner_user_id = (select public.current_app_user_id()));

-- Business writes go through validated RPCs. Generic table writes would let a
-- client alter system folders, publication state, versions, or asset records.
drop policy if exists folders_owner_insert on public.folders;
drop policy if exists folders_owner_update on public.folders;
drop policy if exists images_owner_insert on public.images;
drop policy if exists images_owner_update on public.images;
drop policy if exists versions_owner_insert on public.image_versions;
drop policy if exists assets_owner_insert on public.image_assets;
revoke insert, update, delete on public.folders from authenticated;
revoke insert, update, delete on public.images from authenticated;
revoke insert, update, delete on public.image_versions from authenticated;
revoke insert, update, delete on public.image_assets from authenticated;
revoke insert, update, delete on public.upload_intents from authenticated;

-- Buckets remain private. SQL is used only for bucket configuration; object
-- writes and deletes continue through the Storage API so object metadata and
-- the underlying provider stay consistent.
insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values
  ('image-originals', 'image-originals', false, 52428800, array['image/jpeg','image/png','image/webp']),
  ('image-display', 'image-display', false, 20971520, array['image/jpeg','image/png','image/webp']),
  ('image-thumbnails', 'image-thumbnails', false, 10485760, array['image/jpeg','image/png','image/webp'])
on conflict (id) do update set
  public = excluded.public,
  file_size_limit = excluded.file_size_limit,
  allowed_mime_types = excluded.allowed_mime_types;

drop policy if exists storage_owner_delete on storage.objects;
create policy storage_owner_delete on storage.objects
for delete to authenticated
using (
  bucket_id in ('image-originals', 'image-display', 'image-thumbnails')
  and owner_id = (select auth.uid()::text)
);

-- Convert an existing active Inbox to the protected system folder, then seed
-- one for every existing account that does not have one.
update public.folders f
set is_system = true, updated_at = now()
where lower(f.name) = 'inbox'
  and f.deleted_at is null
  and not exists (
    select 1 from public.folders system_folder
    where system_folder.owner_user_id = f.owner_user_id
      and system_folder.is_system
      and system_folder.deleted_at is null
  );

insert into public.folders (owner_user_id, name, sort_order, is_system)
select u.id, 'Inbox', 0, true
from public.users u
where not exists (
  select 1 from public.folders f
  where f.owner_user_id = u.id and f.is_system and f.deleted_at is null
);

create unique index if not exists folders_owner_active_system_key
  on public.folders (owner_user_id) where is_system and deleted_at is null;

create or replace function public.ensure_workspace_inbox()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
  insert into public.folders (owner_user_id, name, sort_order, is_system)
  select new.id, 'Inbox', 0, true
  where exists (select 1 from public.users u where u.id = new.id)
  on conflict do nothing;
  return new;
end;
$$;

drop trigger if exists on_auth_user_workspace_created on auth.users;
create trigger on_auth_user_workspace_created
after insert or update of email, email_confirmed_at on auth.users
for each row execute function public.ensure_workspace_inbox();
revoke all on function public.ensure_workspace_inbox() from public, anon, authenticated;

create or replace function public.require_active_workspace_user()
returns uuid
language plpgsql
stable
security definer
set search_path = ''
as $$
declare
  app_user_id uuid;
begin
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
    raise exception 'aal2 required for administrator workspace writes' using errcode = '42501';
  end if;
  return app_user_id;
end;
$$;
revoke all on function public.require_active_workspace_user() from public, anon, authenticated;

create or replace function public.workspace_folder_json(folder_row public.folders)
returns jsonb
language sql
stable
security definer
set search_path = ''
as $$
  select jsonb_build_object(
    'id', folder_row.id,
    'name', folder_row.name,
    'sort_order', folder_row.sort_order,
    'is_system', folder_row.is_system,
    'deleted_at', folder_row.deleted_at,
    'created_at', folder_row.created_at,
    'updated_at', folder_row.updated_at,
    'image_count', (
      select count(*) from public.images i
      where i.folder_id = folder_row.id and i.deleted_at is null
    )
  )
$$;
revoke all on function public.workspace_folder_json(public.folders) from public, anon, authenticated;

create or replace function public.workspace_list_folders()
returns jsonb
language plpgsql
stable
security definer
set search_path = ''
as $$
declare
  app_user_id uuid;
  folder_rows jsonb;
begin
  app_user_id := public.require_active_workspace_user();
  select coalesce(jsonb_agg(public.workspace_folder_json(f) order by f.is_system desc, f.sort_order, lower(f.name)), '[]'::jsonb)
  into folder_rows
  from public.folders f
  where f.owner_user_id = app_user_id and f.deleted_at is null;
  return jsonb_build_object('folders', folder_rows);
end;
$$;

create or replace function public.workspace_create_folder(folder_name text)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  app_user_id uuid;
  normalized_name text := btrim(folder_name);
  created_folder public.folders%rowtype;
begin
  app_user_id := public.require_active_workspace_user();
  if normalized_name is null or length(normalized_name) not between 1 and 120
     or normalized_name ~ '[[:cntrl:]]' then
    return jsonb_build_object('error', jsonb_build_object('code', 'FOLDER_VALIDATION_FAILED', 'message', 'Use a folder name between 1 and 120 characters.'));
  end if;
  if exists (
    select 1 from public.folders f
    where f.owner_user_id = app_user_id and f.deleted_at is null and lower(f.name) = lower(normalized_name)
  ) then
    return jsonb_build_object('error', jsonb_build_object('code', 'FOLDER_NAME_CONFLICT', 'message', 'A folder with this name already exists.'));
  end if;
  insert into public.folders (owner_user_id, name, sort_order, is_system)
  values (
    app_user_id,
    normalized_name,
    coalesce((select max(f.sort_order) + 10 from public.folders f where f.owner_user_id = app_user_id), 10),
    false
  ) returning * into created_folder;
  return jsonb_build_object('folder', public.workspace_folder_json(created_folder));
exception when unique_violation then
  return jsonb_build_object('error', jsonb_build_object('code', 'FOLDER_NAME_CONFLICT', 'message', 'A folder with this name already exists.'));
end;
$$;

create or replace function public.workspace_rename_folder(folder_id uuid, folder_name text)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  app_user_id uuid;
  normalized_name text := btrim(folder_name);
  updated_folder public.folders%rowtype;
begin
  app_user_id := public.require_active_workspace_user();
  if normalized_name is null or length(normalized_name) not between 1 and 120
     or normalized_name ~ '[[:cntrl:]]' then
    return jsonb_build_object('error', jsonb_build_object('code', 'FOLDER_VALIDATION_FAILED', 'message', 'Use a folder name between 1 and 120 characters.'));
  end if;
  update public.folders f set name = normalized_name, updated_at = now()
  where f.id = folder_id and f.owner_user_id = app_user_id
    and not f.is_system and f.deleted_at is null
  returning * into updated_folder;
  if updated_folder.id is null then
    return jsonb_build_object('error', jsonb_build_object('code', 'FOLDER_NOT_FOUND', 'message', 'The folder is unavailable or cannot be renamed.'));
  end if;
  return jsonb_build_object('folder', public.workspace_folder_json(updated_folder));
exception when unique_violation then
  return jsonb_build_object('error', jsonb_build_object('code', 'FOLDER_NAME_CONFLICT', 'message', 'A folder with this name already exists.'));
end;
$$;

create or replace function public.workspace_delete_folder(folder_id uuid, non_empty_policy text default 'reject')
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  app_user_id uuid;
  target_folder public.folders%rowtype;
  inbox_id uuid;
  image_count integer;
begin
  app_user_id := public.require_active_workspace_user();
  select * into target_folder from public.folders f
  where f.id = folder_id and f.owner_user_id = app_user_id and f.deleted_at is null
  for update;
  if target_folder.id is null or target_folder.is_system then
    return jsonb_build_object('error', jsonb_build_object('code', 'FOLDER_NOT_FOUND', 'message', 'The folder is unavailable or cannot be deleted.'));
  end if;
  select count(*) into image_count from public.images i
  where i.folder_id = target_folder.id and i.deleted_at is null;
  if image_count > 0 and non_empty_policy <> 'move_to_inbox' then
    return jsonb_build_object('error', jsonb_build_object('code', 'FOLDER_NOT_EMPTY', 'message', 'Move this folder''s images to Inbox before deleting it.', 'image_count', image_count));
  end if;
  if image_count > 0 then
    select f.id into inbox_id from public.folders f
    where f.owner_user_id = app_user_id and f.is_system and f.deleted_at is null limit 1;
    update public.images set folder_id = inbox_id, updated_at = now(), version = version + 1
    where owner_user_id = app_user_id and folder_id = target_folder.id and deleted_at is null;
  end if;
  update public.folders set deleted_at = now(), updated_at = now() where id = target_folder.id;
  return jsonb_build_object('deleted', true, 'folder_id', target_folder.id, 'moved_image_count', image_count);
end;
$$;

create or replace function public.workspace_restore_folder(folder_id uuid)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  app_user_id uuid;
  restored_folder public.folders%rowtype;
begin
  app_user_id := public.require_active_workspace_user();
  update public.folders f set deleted_at = null, updated_at = now()
  where f.id = folder_id and f.owner_user_id = app_user_id and not f.is_system and f.deleted_at is not null
    and not exists (
      select 1 from public.folders active_folder
      where active_folder.owner_user_id = app_user_id and active_folder.deleted_at is null
        and lower(active_folder.name) = lower(f.name)
    )
  returning * into restored_folder;
  if restored_folder.id is null then
    return jsonb_build_object('error', jsonb_build_object('code', 'FOLDER_RESTORE_CONFLICT', 'message', 'The folder cannot be restored because its name is already in use or it is unavailable.'));
  end if;
  return jsonb_build_object('folder', public.workspace_folder_json(restored_folder));
end;
$$;

create or replace function public.workspace_create_upload_intent(intent jsonb)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  app_user_id uuid;
  auth_user_id uuid := (select auth.uid());
  intent_id uuid := gen_random_uuid();
  image_id uuid := gen_random_uuid();
  selected_folder_id uuid;
  original_filename text;
  original_width integer;
  original_height integer;
  original_checksum text;
  asset jsonb;
  kind text;
  mime_type text;
  extension text;
  storage_bucket text;
  storage_key text;
  normalized_assets jsonb := '[]'::jsonb;
  unsupported_fields text;
begin
  app_user_id := public.require_active_workspace_user();
  if intent is null or jsonb_typeof(intent) <> 'object' then
    return jsonb_build_object('error', jsonb_build_object('code', 'UPLOAD_INTENT_INVALID', 'message', 'Upload metadata must be an object.'));
  end if;
  select string_agg(key, ', ' order by key) into unsupported_fields
  from jsonb_object_keys(intent) keys(key)
  where key not in ('folder_id','original_filename','original_width','original_height','checksum_sha256','assets');
  if unsupported_fields is not null then
    return jsonb_build_object('error', jsonb_build_object('code', 'UPLOAD_INTENT_INVALID', 'message', 'Unsupported upload fields: ' || unsupported_fields));
  end if;
  original_filename := btrim(intent ->> 'original_filename');
  if original_filename is null or length(original_filename) not between 1 and 512
     or original_filename ~ '[[:cntrl:]]' then
    return jsonb_build_object('error', jsonb_build_object('code', 'UPLOAD_INTENT_INVALID', 'message', 'Original filename is invalid.'));
  end if;
  if coalesce(intent ->> 'original_width', '') !~ '^[0-9]{1,6}$'
     or coalesce(intent ->> 'original_height', '') !~ '^[0-9]{1,6}$' then
    return jsonb_build_object('error', jsonb_build_object('code', 'UPLOAD_INTENT_INVALID', 'message', 'Image dimensions are invalid.'));
  end if;
  original_width := (intent ->> 'original_width')::integer;
  original_height := (intent ->> 'original_height')::integer;
  if original_width < 1 or original_height < 1 or original_width > 100000 or original_height > 100000 then
    return jsonb_build_object('error', jsonb_build_object('code', 'UPLOAD_INTENT_INVALID', 'message', 'Image dimensions are invalid.'));
  end if;
  original_checksum := lower(coalesce(intent ->> 'checksum_sha256', ''));
  if original_checksum !~ '^[0-9a-f]{64}$' then
    return jsonb_build_object('error', jsonb_build_object('code', 'UPLOAD_INTENT_INVALID', 'message', 'Original checksum is invalid.'));
  end if;
  if intent ? 'folder_id' and nullif(intent ->> 'folder_id', '') is not null then
    begin
      selected_folder_id := (intent ->> 'folder_id')::uuid;
    exception when invalid_text_representation then
      return jsonb_build_object('error', jsonb_build_object('code', 'FOLDER_NOT_FOUND', 'message', 'The selected folder is unavailable.'));
    end;
    if not exists (
      select 1 from public.folders f
      where f.id = selected_folder_id and f.owner_user_id = app_user_id and f.deleted_at is null
    ) then
      return jsonb_build_object('error', jsonb_build_object('code', 'FOLDER_NOT_FOUND', 'message', 'The selected folder is unavailable.'));
    end if;
  else
    select f.id into selected_folder_id from public.folders f
    where f.owner_user_id = app_user_id and f.is_system and f.deleted_at is null limit 1;
  end if;
  if jsonb_typeof(intent -> 'assets') <> 'array' then
    return jsonb_build_object('error', jsonb_build_object('code', 'UPLOAD_ASSETS_INVALID', 'message', 'Original, display, and thumbnail assets are required.'));
  end if;
  if jsonb_array_length(intent -> 'assets') <> 3 then
    return jsonb_build_object('error', jsonb_build_object('code', 'UPLOAD_ASSETS_INVALID', 'message', 'Original, display, and thumbnail assets are required.'));
  end if;
  if (
    select count(distinct value ->> 'kind') from jsonb_array_elements(intent -> 'assets')
  ) <> 3 or exists (
    select 1 from jsonb_array_elements(intent -> 'assets') entry
    where entry ->> 'kind' not in ('original', 'display', 'thumbnail')
  ) then
    return jsonb_build_object('error', jsonb_build_object('code', 'UPLOAD_ASSETS_INVALID', 'message', 'Asset kinds must be original, display, and thumbnail.'));
  end if;
  for asset in select value from jsonb_array_elements(intent -> 'assets') loop
    kind := asset ->> 'kind';
    mime_type := lower(coalesce(asset ->> 'mime_type', ''));
    if mime_type not in ('image/jpeg', 'image/png', 'image/webp')
       or coalesce(asset ->> 'byte_size', '') !~ '^[0-9]{1,12}$'
       or coalesce(asset ->> 'width', '') !~ '^[0-9]{1,6}$'
       or coalesce(asset ->> 'height', '') !~ '^[0-9]{1,6}$'
       or lower(coalesce(asset ->> 'checksum_sha256', '')) !~ '^[0-9a-f]{64}$' then
      return jsonb_build_object('error', jsonb_build_object('code', 'UPLOAD_ASSETS_INVALID', 'message', 'Asset metadata is invalid.'));
    end if;
    if (asset ->> 'byte_size')::bigint < 1 or (asset ->> 'width')::integer < 1 or (asset ->> 'height')::integer < 1 then
      return jsonb_build_object('error', jsonb_build_object('code', 'UPLOAD_ASSETS_INVALID', 'message', 'Asset metadata is invalid.'));
    end if;
    if (asset ->> 'byte_size')::bigint > (case kind
         when 'original' then 52428800
         when 'display' then 20971520
         else 10485760
       end)
       or (asset ->> 'width')::integer > 100000
       or (asset ->> 'height')::integer > 100000 then
      return jsonb_build_object('error', jsonb_build_object('code', 'UPLOAD_ASSETS_INVALID', 'message', 'Asset metadata exceeds the allowed limits.'));
    end if;
    if kind = 'original' and (
      (asset ->> 'width')::integer <> original_width
      or (asset ->> 'height')::integer <> original_height
      or lower(asset ->> 'checksum_sha256') <> original_checksum
    ) then
      return jsonb_build_object('error', jsonb_build_object('code', 'UPLOAD_ASSETS_INVALID', 'message', 'Original asset metadata must match the upload metadata.'));
    end if;
    extension := case mime_type when 'image/png' then 'png' when 'image/webp' then 'webp' else 'jpg' end;
    storage_bucket := case kind
      when 'original' then 'image-originals'
      when 'display' then 'image-display'
      else 'image-thumbnails'
    end;
    storage_key := auth_user_id::text || '/' || image_id::text || '/' || kind || '.' || extension;
    normalized_assets := normalized_assets || jsonb_build_array(jsonb_build_object(
      'kind', kind,
      'storage_bucket', storage_bucket,
      'storage_key', storage_key,
      'mime_type', mime_type,
      'byte_size', (asset ->> 'byte_size')::bigint,
      'width', (asset ->> 'width')::integer,
      'height', (asset ->> 'height')::integer,
      'checksum_sha256', lower(asset ->> 'checksum_sha256')
    ));
  end loop;
  insert into public.upload_intents (
    id, owner_user_id, image_id, folder_id, original_filename, original_width,
    original_height, checksum_sha256, expected_assets
  ) values (
    intent_id, app_user_id, image_id, selected_folder_id, original_filename,
    original_width, original_height, original_checksum, normalized_assets
  );
  return jsonb_build_object(
    'upload_id', intent_id,
    'image_id', image_id,
    'folder_id', selected_folder_id,
    'expires_at', now() + interval '2 hours',
    'assets', normalized_assets
  );
end;
$$;

create or replace function public.workspace_draft_json(target_image_id uuid)
returns jsonb
language sql
stable
security definer
set search_path = ''
as $$
  select jsonb_build_object(
    'id', i.id,
    'folder_id', i.folder_id,
    'processing_status', i.processing_status,
    'workflow_status', i.workflow_status,
    'publication_status', i.publication_status,
    'original_filename', i.original_filename,
    'original_width', i.original_width,
    'original_height', i.original_height,
    'checksum_sha256', i.checksum_sha256,
    'created_at', i.created_at,
    'updated_at', i.updated_at,
    'version', jsonb_build_object(
      'id', v.id,
      'version_number', v.version_number,
      'title', v.title,
      'caption', v.caption,
      'description', v.description,
      'alt_text', v.alt_text,
      'tags', v.tags,
      'content_category', v.content_category,
      'captured_at', v.captured_at,
      'location_name', v.location_name,
      'copyright_holder', v.copyright_holder,
      'rights_declared', v.rights_declared,
      'created_at', v.created_at,
      'locked_at', v.locked_at
    ),
    'assets', coalesce((
      select jsonb_agg(jsonb_build_object(
        'id', a.id,
        'kind', a.kind,
        'storage_bucket', case a.kind when 'original' then 'image-originals' when 'display' then 'image-display' else 'image-thumbnails' end,
        'storage_key', a.storage_key,
        'mime_type', a.mime_type,
        'byte_size', a.byte_size,
        'width', a.width,
        'height', a.height,
        'checksum_sha256', a.checksum_sha256,
        'scan_status', a.scan_status
      ) order by case a.kind when 'original' then 1 when 'display' then 2 else 3 end)
      from public.image_assets a where a.image_id = i.id and a.deleted_at is null
    ), '[]'::jsonb)
  )
  from public.images i
  join public.image_versions v on v.id = i.current_version_id
  where i.id = target_image_id
$$;
revoke all on function public.workspace_draft_json(uuid) from public, anon, authenticated;

create or replace function public.workspace_complete_upload(upload_id uuid, draft jsonb default '{}'::jsonb)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  app_user_id uuid;
  upload_row public.upload_intents%rowtype;
  version_id uuid := gen_random_uuid();
  asset jsonb;
  draft_title text;
  draft_caption text;
  draft_description text;
  draft_tags jsonb;
  draft_category text;
  draft_captured_at timestamptz;
  draft_alt_text text;
  draft_location_name text;
  selected_folder_id uuid;
  unsupported_fields text;
begin
  app_user_id := public.require_active_workspace_user();
  select * into upload_row from public.upload_intents u
  where u.id = upload_id and u.owner_user_id = app_user_id for update;
  if upload_row.id is null then
    return jsonb_build_object('error', jsonb_build_object('code', 'UPLOAD_INTENT_NOT_FOUND', 'message', 'The upload intent is unavailable.'));
  end if;
  if upload_row.status <> 'issued' or upload_row.expires_at <= now() then
    if upload_row.status = 'issued' and upload_row.expires_at <= now() then
      update public.upload_intents set status = 'expired', updated_at = now() where id = upload_row.id;
    end if;
    return jsonb_build_object('error', jsonb_build_object('code', 'UPLOAD_INTENT_EXPIRED', 'message', 'The upload intent has expired or was already completed.'));
  end if;
  if exists (
    select 1 from jsonb_array_elements(upload_row.expected_assets) expected
    where not exists (
      select 1 from storage.objects o
      where o.bucket_id = expected ->> 'storage_bucket'
        and o.name = expected ->> 'storage_key'
        and o.owner_id = (select auth.uid()::text)
        and lower(coalesce(o.metadata ->> 'mimetype', '')) = lower(expected ->> 'mime_type')
        and coalesce(o.metadata ->> 'size', '') = expected ->> 'byte_size'
    )
  ) then
    return jsonb_build_object('error', jsonb_build_object('code', 'UPLOAD_ASSETS_INCOMPLETE', 'message', 'One or more uploaded assets are missing or do not match the intent.'));
  end if;
  if draft is null or jsonb_typeof(draft) <> 'object' then
    return jsonb_build_object('error', jsonb_build_object('code', 'DRAFT_VALIDATION_FAILED', 'message', 'Draft metadata must be an object.'));
  end if;
  select string_agg(key, ', ' order by key) into unsupported_fields
  from jsonb_object_keys(draft) keys(key)
  where key not in ('folder_id','title','caption','description','alt_text','tags','content_category','captured_at','location_name');
  if unsupported_fields is not null then
    return jsonb_build_object('error', jsonb_build_object('code', 'DRAFT_VALIDATION_FAILED', 'message', 'Unsupported Draft fields: ' || unsupported_fields));
  end if;
  if (draft ? 'title' and jsonb_typeof(draft -> 'title') <> 'string')
     or (draft ? 'caption' and jsonb_typeof(draft -> 'caption') <> 'string')
     or (draft ? 'description' and jsonb_typeof(draft -> 'description') <> 'string')
     or (draft ? 'alt_text' and jsonb_typeof(draft -> 'alt_text') <> 'string')
     or (draft ? 'location_name' and jsonb_typeof(draft -> 'location_name') not in ('string', 'null'))
     or (draft ? 'content_category' and jsonb_typeof(draft -> 'content_category') not in ('string', 'null'))
     or (draft ? 'captured_at' and jsonb_typeof(draft -> 'captured_at') not in ('string', 'null')) then
    return jsonb_build_object('error', jsonb_build_object('code', 'DRAFT_VALIDATION_FAILED', 'message', 'Draft metadata contains an invalid field type.'));
  end if;
  selected_folder_id := upload_row.folder_id;
  if draft ? 'folder_id' then
    begin
      selected_folder_id := (draft ->> 'folder_id')::uuid;
    exception when invalid_text_representation then
      return jsonb_build_object('error', jsonb_build_object('code', 'FOLDER_NOT_FOUND', 'message', 'The selected folder is unavailable.'));
    end;
    if not exists (
      select 1 from public.folders f
      where f.id = selected_folder_id and f.owner_user_id = app_user_id and f.deleted_at is null
    ) then
      return jsonb_build_object('error', jsonb_build_object('code', 'FOLDER_NOT_FOUND', 'message', 'The selected folder is unavailable.'));
    end if;
  end if;
  draft_title := btrim(case when draft ? 'title' then draft ->> 'title' else regexp_replace(upload_row.original_filename, '\.[^.]+$', '') end);
  draft_caption := btrim(coalesce(draft ->> 'caption', ''));
  draft_description := btrim(coalesce(draft ->> 'description', ''));
  draft_alt_text := btrim(coalesce(draft ->> 'alt_text', ''));
  draft_location_name := nullif(btrim(draft ->> 'location_name'), '');
  draft_tags := coalesce(draft -> 'tags', '[]'::jsonb);
  draft_category := nullif(btrim(draft ->> 'content_category'), '');
  if length(draft_title) > 180 or length(draft_caption) > 500 or length(draft_description) > 10000
     or length(draft_alt_text) > 500 or length(draft_location_name) > 500
     or (draft_category is not null and draft_category not in ('abstract', 'concrete')) then
    return jsonb_build_object('error', jsonb_build_object('code', 'DRAFT_VALIDATION_FAILED', 'message', 'Draft metadata is invalid.'));
  end if;
  if jsonb_typeof(draft_tags) <> 'array' then
    return jsonb_build_object('error', jsonb_build_object('code', 'DRAFT_VALIDATION_FAILED', 'message', 'Draft metadata is invalid.'));
  end if;
  if jsonb_array_length(draft_tags) > 30
     or exists (select 1 from jsonb_array_elements(draft_tags) tag where jsonb_typeof(tag) <> 'string')
     or exists (select 1 from jsonb_array_elements_text(draft_tags) tag where length(btrim(tag)) not between 1 and 64) then
    return jsonb_build_object('error', jsonb_build_object('code', 'DRAFT_VALIDATION_FAILED', 'message', 'Draft metadata is invalid.'));
  end if;
  if nullif(draft ->> 'captured_at', '') is not null then
    begin
      draft_captured_at := (draft ->> 'captured_at')::timestamptz;
    exception when invalid_datetime_format then
      return jsonb_build_object('error', jsonb_build_object('code', 'DRAFT_VALIDATION_FAILED', 'message', 'Captured date is invalid.'));
    end;
  end if;
  insert into public.images (
    id, owner_user_id, folder_id, processing_status, workflow_status,
    publication_status, original_filename, original_width, original_height,
    checksum_sha256
  ) values (
    upload_row.image_id, app_user_id, selected_folder_id, 'ready', 'draft',
    'never_published', upload_row.original_filename, upload_row.original_width,
    upload_row.original_height, upload_row.checksum_sha256
  );
  insert into public.image_versions (
    id, image_id, version_number, title, caption, description, alt_text, tags,
    content_category, captured_at, location_name, created_by_user_id
  ) values (
    version_id, upload_row.image_id, 1, draft_title, draft_caption,
    draft_description, draft_alt_text, draft_tags, draft_category,
    draft_captured_at, draft_location_name, app_user_id
  );
  update public.images set current_version_id = version_id, updated_at = now()
  where id = upload_row.image_id;
  for asset in select value from jsonb_array_elements(upload_row.expected_assets) loop
    insert into public.image_assets (
      image_id, owner_user_id, kind, storage_key, mime_type, byte_size,
      width, height, checksum_sha256, scan_status, storage_visibility
    ) values (
      upload_row.image_id, app_user_id, asset ->> 'kind', asset ->> 'storage_key',
      asset ->> 'mime_type', (asset ->> 'byte_size')::bigint,
      (asset ->> 'width')::integer, (asset ->> 'height')::integer,
      asset ->> 'checksum_sha256', 'pending', 'private'
    );
  end loop;
  update public.upload_intents set status = 'completed', completed_at = now(), updated_at = now()
  where id = upload_row.id;
  return jsonb_build_object('draft', public.workspace_draft_json(upload_row.image_id));
exception when unique_violation then
  return jsonb_build_object('error', jsonb_build_object('code', 'UPLOAD_ALREADY_COMPLETED', 'message', 'This upload has already created a draft.'));
end;
$$;

create or replace function public.workspace_list_drafts()
returns jsonb
language plpgsql
stable
security definer
set search_path = ''
as $$
declare
  app_user_id uuid;
  draft_rows jsonb;
begin
  app_user_id := public.require_active_workspace_user();
  select coalesce(jsonb_agg(public.workspace_draft_json(i.id) order by i.updated_at desc), '[]'::jsonb)
  into draft_rows
  from public.images i
  where i.owner_user_id = app_user_id
    and i.workflow_status in ('draft'::public.workflow_status, 'changes_requested'::public.workflow_status)
    and i.deleted_at is null;
  return jsonb_build_object('images', draft_rows);
end;
$$;

create or replace function public.workspace_update_draft(image_id uuid, patch jsonb)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  app_user_id uuid;
  image_row public.images%rowtype;
  version_row public.image_versions%rowtype;
  selected_folder_id uuid;
  unsupported_fields text;
  tags_value jsonb;
  captured_value timestamptz;
begin
  app_user_id := public.require_active_workspace_user();
  if patch is null or jsonb_typeof(patch) <> 'object' or patch = '{}'::jsonb then
    return jsonb_build_object('error', jsonb_build_object('code', 'DRAFT_VALIDATION_FAILED', 'message', 'Choose at least one Draft field to update.'));
  end if;
  select string_agg(key, ', ' order by key) into unsupported_fields
  from jsonb_object_keys(patch) keys(key)
  where key not in ('folder_id','title','caption','description','alt_text','tags','content_category','captured_at','location_name');
  if unsupported_fields is not null then
    return jsonb_build_object('error', jsonb_build_object('code', 'DRAFT_VALIDATION_FAILED', 'message', 'Unsupported Draft fields: ' || unsupported_fields));
  end if;
  select * into image_row from public.images i
  where i.id = image_id and i.owner_user_id = app_user_id and i.deleted_at is null for update;
  if image_row.id is null then
    return jsonb_build_object('error', jsonb_build_object('code', 'DRAFT_NOT_FOUND', 'message', 'The Draft is unavailable.'));
  end if;
  if image_row.workflow_status not in ('draft'::public.workflow_status, 'changes_requested'::public.workflow_status) then
    return jsonb_build_object('error', jsonb_build_object('code', 'DRAFT_LOCKED', 'message', 'Submitted or reviewed images cannot be edited as Drafts.'));
  end if;
  select * into version_row from public.image_versions v where v.id = image_row.current_version_id for update;
  if version_row.id is null or version_row.locked_at is not null then
    return jsonb_build_object('error', jsonb_build_object('code', 'DRAFT_LOCKED', 'message', 'This Draft version is locked.'));
  end if;
  if patch ? 'folder_id' then
    begin
      selected_folder_id := (patch ->> 'folder_id')::uuid;
    exception when invalid_text_representation then
      return jsonb_build_object('error', jsonb_build_object('code', 'FOLDER_NOT_FOUND', 'message', 'The selected folder is unavailable.'));
    end;
    if not exists (
      select 1 from public.folders f
      where f.id = selected_folder_id and f.owner_user_id = app_user_id and f.deleted_at is null
    ) then
      return jsonb_build_object('error', jsonb_build_object('code', 'FOLDER_NOT_FOUND', 'message', 'The selected folder is unavailable.'));
    end if;
  else
    selected_folder_id := image_row.folder_id;
  end if;
  if patch ? 'title' and (jsonb_typeof(patch -> 'title') <> 'string' or length(btrim(patch ->> 'title')) > 180) then
    return jsonb_build_object('error', jsonb_build_object('code', 'DRAFT_VALIDATION_FAILED', 'message', 'Title must use 180 characters or fewer.'));
  end if;
  if patch ? 'caption' and (jsonb_typeof(patch -> 'caption') <> 'string' or length(btrim(patch ->> 'caption')) > 500) then
    return jsonb_build_object('error', jsonb_build_object('code', 'DRAFT_VALIDATION_FAILED', 'message', 'Caption must use 500 characters or fewer.'));
  end if;
  if patch ? 'description' and (jsonb_typeof(patch -> 'description') <> 'string' or length(btrim(patch ->> 'description')) > 10000) then
    return jsonb_build_object('error', jsonb_build_object('code', 'DRAFT_VALIDATION_FAILED', 'message', 'Description must use 10,000 characters or fewer.'));
  end if;
  if patch ? 'alt_text' and (jsonb_typeof(patch -> 'alt_text') <> 'string' or length(btrim(patch ->> 'alt_text')) > 500) then
    return jsonb_build_object('error', jsonb_build_object('code', 'DRAFT_VALIDATION_FAILED', 'message', 'Alt text must use 500 characters or fewer.'));
  end if;
  if patch ? 'location_name' and (
    jsonb_typeof(patch -> 'location_name') not in ('string', 'null')
    or length(btrim(patch ->> 'location_name')) > 500
  ) then
    return jsonb_build_object('error', jsonb_build_object('code', 'DRAFT_VALIDATION_FAILED', 'message', 'Location must use 500 characters or fewer.'));
  end if;
  if patch ? 'content_category' and jsonb_typeof(patch -> 'content_category') not in ('string', 'null') then
    return jsonb_build_object('error', jsonb_build_object('code', 'DRAFT_VALIDATION_FAILED', 'message', 'Content category is invalid.'));
  end if;
  if patch ? 'content_category' and nullif(btrim(patch ->> 'content_category'), '') is not null
     and btrim(patch ->> 'content_category') not in ('abstract', 'concrete') then
    return jsonb_build_object('error', jsonb_build_object('code', 'DRAFT_VALIDATION_FAILED', 'message', 'Content category is invalid.'));
  end if;
  tags_value := case when patch ? 'tags' then patch -> 'tags' else version_row.tags end;
  if jsonb_typeof(tags_value) <> 'array' then
    return jsonb_build_object('error', jsonb_build_object('code', 'DRAFT_VALIDATION_FAILED', 'message', 'Use at most 30 tags of 64 characters or fewer.'));
  end if;
  if jsonb_array_length(tags_value) > 30
     or exists (select 1 from jsonb_array_elements(tags_value) tag where jsonb_typeof(tag) <> 'string')
     or exists (select 1 from jsonb_array_elements_text(tags_value) tag where length(btrim(tag)) not between 1 and 64) then
    return jsonb_build_object('error', jsonb_build_object('code', 'DRAFT_VALIDATION_FAILED', 'message', 'Use at most 30 tags of 64 characters or fewer.'));
  end if;
  if patch ? 'captured_at' and jsonb_typeof(patch -> 'captured_at') not in ('string', 'null') then
    return jsonb_build_object('error', jsonb_build_object('code', 'DRAFT_VALIDATION_FAILED', 'message', 'Captured date is invalid.'));
  end if;
  if patch ? 'captured_at' and nullif(patch ->> 'captured_at', '') is not null then
    begin
      captured_value := (patch ->> 'captured_at')::timestamptz;
    exception when invalid_datetime_format then
      return jsonb_build_object('error', jsonb_build_object('code', 'DRAFT_VALIDATION_FAILED', 'message', 'Captured date is invalid.'));
    end;
  else
    captured_value := case when patch ? 'captured_at' then null else version_row.captured_at end;
  end if;
  update public.image_versions set
    title = case when patch ? 'title' then btrim(patch ->> 'title') else title end,
    caption = case when patch ? 'caption' then btrim(patch ->> 'caption') else caption end,
    description = case when patch ? 'description' then btrim(patch ->> 'description') else description end,
    alt_text = case when patch ? 'alt_text' then btrim(patch ->> 'alt_text') else alt_text end,
    tags = tags_value,
    content_category = case when patch ? 'content_category' then nullif(btrim(patch ->> 'content_category'), '') else content_category end,
    captured_at = captured_value,
    location_name = case when patch ? 'location_name' then nullif(btrim(patch ->> 'location_name'), '') else location_name end
  where id = version_row.id;
  update public.images set folder_id = selected_folder_id, updated_at = now(), version = version + 1 where id = image_row.id;
  return jsonb_build_object('draft', public.workspace_draft_json(image_row.id));
end;
$$;

create or replace function public.workspace_trash_draft(image_id uuid)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  app_user_id uuid;
  changed_id uuid;
begin
  app_user_id := public.require_active_workspace_user();
  update public.images i set
    publication_status = 'deleted'::public.publication_status,
    deleted_at = now(),
    updated_at = now(),
    version = version + 1
  where i.id = image_id and i.owner_user_id = app_user_id and i.deleted_at is null
    and i.workflow_status in ('draft'::public.workflow_status, 'changes_requested'::public.workflow_status)
  returning i.id into changed_id;
  if changed_id is null then
    return jsonb_build_object('error', jsonb_build_object('code', 'DRAFT_NOT_FOUND', 'message', 'The Draft is unavailable or cannot be moved to Trash.'));
  end if;
  return jsonb_build_object('trashed', true, 'image_id', changed_id);
end;
$$;

create or replace function public.workspace_restore_draft(image_id uuid)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  app_user_id uuid;
  changed_id uuid;
begin
  app_user_id := public.require_active_workspace_user();
  update public.images i set
    publication_status = 'never_published'::public.publication_status,
    deleted_at = null,
    updated_at = now(),
    version = version + 1
  where i.id = image_id and i.owner_user_id = app_user_id and i.deleted_at is not null
    and i.workflow_status in ('draft'::public.workflow_status, 'changes_requested'::public.workflow_status)
  returning i.id into changed_id;
  if changed_id is null then
    return jsonb_build_object('error', jsonb_build_object('code', 'DRAFT_NOT_FOUND', 'message', 'The Draft is unavailable or cannot be restored.'));
  end if;
  return jsonb_build_object('draft', public.workspace_draft_json(changed_id));
end;
$$;

grant execute on function public.workspace_list_folders() to authenticated;
grant execute on function public.workspace_create_folder(text) to authenticated;
grant execute on function public.workspace_rename_folder(uuid, text) to authenticated;
grant execute on function public.workspace_delete_folder(uuid, text) to authenticated;
grant execute on function public.workspace_restore_folder(uuid) to authenticated;
grant execute on function public.workspace_create_upload_intent(jsonb) to authenticated;
grant execute on function public.workspace_complete_upload(uuid, jsonb) to authenticated;
grant execute on function public.workspace_list_drafts() to authenticated;
grant execute on function public.workspace_update_draft(uuid, jsonb) to authenticated;
grant execute on function public.workspace_trash_draft(uuid) to authenticated;
grant execute on function public.workspace_restore_draft(uuid) to authenticated;

revoke all on function public.workspace_list_folders() from anon, public;
revoke all on function public.workspace_create_folder(text) from anon, public;
revoke all on function public.workspace_rename_folder(uuid, text) from anon, public;
revoke all on function public.workspace_delete_folder(uuid, text) from anon, public;
revoke all on function public.workspace_restore_folder(uuid) from anon, public;
revoke all on function public.workspace_create_upload_intent(jsonb) from anon, public;
revoke all on function public.workspace_complete_upload(uuid, jsonb) from anon, public;
revoke all on function public.workspace_list_drafts() from anon, public;
revoke all on function public.workspace_update_draft(uuid, jsonb) from anon, public;
revoke all on function public.workspace_trash_draft(uuid) from anon, public;
revoke all on function public.workspace_restore_draft(uuid) from anon, public;

commit;
