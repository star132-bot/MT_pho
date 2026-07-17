-- Phase 2D: optimistic concurrency for Draft autosave and manual save.
begin;

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
    'lock_version', i.version,
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
      'copyright_year', v.copyright_year,
      'contains_recognizable_people', v.contains_recognizable_people,
      'model_release_status', v.model_release_status,
      'property_release_status', v.property_release_status,
      'rights_declared', v.rights_declared,
      'ai_disclosure', v.ai_disclosure,
      'sensitive_content_disclosure', v.sensitive_content_disclosure,
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
    update public.images set
      folder_id = inbox_id,
      updated_at = now(),
      version = version + 1
    where owner_user_id = app_user_id and folder_id = target_folder.id and deleted_at is null;
  end if;
  update public.folders set deleted_at = now(), updated_at = now() where id = target_folder.id;
  return jsonb_build_object('deleted', true, 'folder_id', target_folder.id, 'moved_image_count', image_count);
end;
$$;
grant execute on function public.workspace_delete_folder(uuid, text) to authenticated;
revoke all on function public.workspace_delete_folder(uuid, text) from anon, public;

create or replace function public.workspace_update_draft_versioned(
  image_id uuid,
  patch jsonb,
  expected_version integer
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  app_user_id uuid;
  image_row public.images%rowtype;
begin
  if expected_version is null or expected_version < 1 then
    return jsonb_build_object('error', jsonb_build_object(
      'code', 'DRAFT_VERSION_REQUIRED',
      'message', 'Reload this Draft before saving changes.'
    ));
  end if;
  app_user_id := public.require_active_workspace_user();
  select * into image_row from public.images i
  where i.id = image_id and i.owner_user_id = app_user_id and i.deleted_at is null
  for update;
  if image_row.id is null then
    return jsonb_build_object('error', jsonb_build_object(
      'code', 'DRAFT_NOT_FOUND',
      'message', 'The Draft is unavailable.'
    ));
  end if;
  if image_row.version <> expected_version then
    return jsonb_build_object('error', jsonb_build_object(
      'code', 'DRAFT_VERSION_CONFLICT',
      'message', 'A newer version of this Draft is available. Reload before saving.'
    ));
  end if;
  return public.workspace_update_draft(image_id, patch);
end;
$$;

create or replace function public.workspace_trash_draft_versioned(
  image_id uuid,
  expected_version integer
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  app_user_id uuid;
  image_row public.images%rowtype;
begin
  if expected_version is null or expected_version < 1 then
    return jsonb_build_object('error', jsonb_build_object(
      'code', 'DRAFT_VERSION_REQUIRED',
      'message', 'Reload this Draft before moving it to Trash.'
    ));
  end if;
  app_user_id := public.require_active_workspace_user();
  select * into image_row from public.images i
  where i.id = image_id and i.owner_user_id = app_user_id and i.deleted_at is null
  for update;
  if image_row.id is null then
    return jsonb_build_object('error', jsonb_build_object(
      'code', 'DRAFT_NOT_FOUND',
      'message', 'The Draft is unavailable.'
    ));
  end if;
  if image_row.version <> expected_version then
    return jsonb_build_object('error', jsonb_build_object(
      'code', 'DRAFT_VERSION_CONFLICT',
      'message', 'A newer version of this Draft is available. Reload before moving it to Trash.'
    ));
  end if;
  return public.workspace_trash_draft(image_id);
end;
$$;

revoke execute on function public.workspace_update_draft(uuid, jsonb) from authenticated;
revoke execute on function public.workspace_trash_draft(uuid) from authenticated;
grant execute on function public.workspace_update_draft_versioned(uuid, jsonb, integer) to authenticated;
grant execute on function public.workspace_trash_draft_versioned(uuid, integer) to authenticated;
revoke all on function public.workspace_update_draft_versioned(uuid, jsonb, integer) from anon, public;
revoke all on function public.workspace_trash_draft_versioned(uuid, integer) from anon, public;

commit;
