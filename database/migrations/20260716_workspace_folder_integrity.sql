-- Phase 2D: serialize folder deletion with every image/upload folder assignment.
begin;

create or replace function public.workspace_folder_assignment_guard()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
declare
  active_folder_id uuid;
begin
  perform pg_catalog.pg_advisory_xact_lock(
    pg_catalog.hashtextextended('mt-workspace-folders:' || new.owner_user_id::text, 0)
  );

  select f.id into active_folder_id
  from public.folders f
  where f.id = new.folder_id
    and f.owner_user_id = new.owner_user_id
    and f.deleted_at is null;

  if active_folder_id is null then
    select f.id into active_folder_id
    from public.folders f
    where f.owner_user_id = new.owner_user_id
      and f.is_system
      and f.deleted_at is null
    limit 1;
    if active_folder_id is null then
      raise exception using
        errcode = '23503',
        message = 'The Workspace Inbox is unavailable.';
    end if;
    new.folder_id := active_folder_id;
  end if;

  return new;
end;
$$;
revoke all on function public.workspace_folder_assignment_guard() from public, anon, authenticated;

drop trigger if exists images_workspace_folder_assignment_guard on public.images;
create trigger images_workspace_folder_assignment_guard
before insert or update of folder_id on public.images
for each row execute function public.workspace_folder_assignment_guard();

drop trigger if exists upload_intents_workspace_folder_assignment_guard on public.upload_intents;
create trigger upload_intents_workspace_folder_assignment_guard
before insert or update of folder_id on public.upload_intents
for each row execute function public.workspace_folder_assignment_guard();

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
  perform pg_catalog.pg_advisory_xact_lock(
    pg_catalog.hashtextextended('mt-workspace-folders:' || app_user_id::text, 0)
  );
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
  selected_folder_id uuid;
begin
  if expected_version is null or expected_version < 1 then
    return jsonb_build_object('error', jsonb_build_object(
      'code', 'DRAFT_VERSION_REQUIRED',
      'message', 'Reload this Draft before saving changes.'
    ));
  end if;
  app_user_id := public.require_active_workspace_user();
  perform pg_catalog.pg_advisory_xact_lock(
    pg_catalog.hashtextextended('mt-workspace-folders:' || app_user_id::text, 0)
  );
  if jsonb_typeof(patch) = 'object' and patch ? 'folder_id' then
    begin
      selected_folder_id := (patch ->> 'folder_id')::uuid;
    exception when invalid_text_representation then
      return jsonb_build_object('error', jsonb_build_object(
        'code', 'FOLDER_NOT_FOUND',
        'message', 'The selected folder is unavailable.'
      ));
    end;
    if not exists (
      select 1 from public.folders f
      where f.id = selected_folder_id
        and f.owner_user_id = app_user_id
        and f.deleted_at is null
    ) then
      return jsonb_build_object('error', jsonb_build_object(
        'code', 'FOLDER_NOT_FOUND',
        'message', 'The selected folder is unavailable.'
      ));
    end if;
  end if;
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

create or replace function public.workspace_restore_draft(image_id uuid)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  app_user_id uuid;
  image_row public.images%rowtype;
  restore_folder_id uuid;
begin
  app_user_id := public.require_active_workspace_user();
  perform pg_catalog.pg_advisory_xact_lock(
    pg_catalog.hashtextextended('mt-workspace-folders:' || app_user_id::text, 0)
  );
  select * into image_row from public.images i
  where i.id = image_id
    and i.owner_user_id = app_user_id
    and i.deleted_at is not null
    and i.workflow_status in ('draft'::public.workflow_status, 'changes_requested'::public.workflow_status)
  for update;
  if image_row.id is null then
    return jsonb_build_object('error', jsonb_build_object(
      'code', 'DRAFT_NOT_FOUND',
      'message', 'The Draft is unavailable or cannot be restored.'
    ));
  end if;
  select f.id into restore_folder_id from public.folders f
  where f.id = image_row.folder_id
    and f.owner_user_id = app_user_id
    and f.deleted_at is null;
  if restore_folder_id is null then
    select f.id into restore_folder_id from public.folders f
    where f.owner_user_id = app_user_id
      and f.is_system
      and f.deleted_at is null
    limit 1;
  end if;
  if restore_folder_id is null then
    return jsonb_build_object('error', jsonb_build_object(
      'code', 'FOLDER_NOT_FOUND',
      'message', 'The Workspace Inbox is unavailable.'
    ));
  end if;
  update public.images i set
    folder_id = restore_folder_id,
    publication_status = 'never_published'::public.publication_status,
    deleted_at = null,
    updated_at = now(),
    version = version + 1
  where i.id = image_row.id;
  return jsonb_build_object('draft', public.workspace_draft_json(image_row.id));
end;
$$;

grant execute on function public.workspace_delete_folder(uuid, text) to authenticated;
grant execute on function public.workspace_update_draft_versioned(uuid, jsonb, integer) to authenticated;
grant execute on function public.workspace_restore_draft(uuid) to authenticated;
revoke all on function public.workspace_delete_folder(uuid, text) from anon, public;
revoke all on function public.workspace_update_draft_versioned(uuid, jsonb, integer) from anon, public;
revoke all on function public.workspace_restore_draft(uuid) from anon, public;

commit;
