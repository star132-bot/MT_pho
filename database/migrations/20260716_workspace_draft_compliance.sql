-- Phase 2C: owner-scoped Draft accessibility, rights, and disclosure metadata.
begin;

do $$
begin
  if not exists (
    select 1 from pg_constraint
    where conrelid = 'public.image_versions'::regclass
      and conname = 'image_versions_copyright_holder_length'
  ) then
    alter table public.image_versions
      add constraint image_versions_copyright_holder_length
      check (copyright_holder is null or length(copyright_holder) <= 160);
  end if;
  if not exists (
    select 1 from pg_constraint
    where conrelid = 'public.image_versions'::regclass
      and conname = 'image_versions_copyright_year_range'
  ) then
    alter table public.image_versions
      add constraint image_versions_copyright_year_range
      check (copyright_year is null or copyright_year between 1000 and 2200);
  end if;
  if not exists (
    select 1 from pg_constraint
    where conrelid = 'public.image_versions'::regclass
      and conname = 'image_versions_model_release_status'
  ) then
    alter table public.image_versions
      add constraint image_versions_model_release_status
      check (model_release_status is null or model_release_status in ('not_applicable', 'available', 'not_available', 'pending'));
  end if;
  if not exists (
    select 1 from pg_constraint
    where conrelid = 'public.image_versions'::regclass
      and conname = 'image_versions_property_release_status'
  ) then
    alter table public.image_versions
      add constraint image_versions_property_release_status
      check (property_release_status is null or property_release_status in ('not_applicable', 'available', 'not_available', 'pending'));
  end if;
  if not exists (
    select 1 from pg_constraint
    where conrelid = 'public.image_versions'::regclass
      and conname = 'image_versions_ai_disclosure'
  ) then
    alter table public.image_versions
      add constraint image_versions_ai_disclosure
      check (ai_disclosure is null or ai_disclosure in ('none', 'ai_edited', 'ai_generated'));
  end if;
  if not exists (
    select 1 from pg_constraint
    where conrelid = 'public.image_versions'::regclass
      and conname = 'image_versions_sensitive_disclosure'
  ) then
    alter table public.image_versions
      add constraint image_versions_sensitive_disclosure
      check (sensitive_content_disclosure is null or sensitive_content_disclosure in ('none', 'contains_sensitive_content'));
  end if;
end
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
  copyright_year_value integer;
begin
  app_user_id := public.require_active_workspace_user();
  if patch is null or jsonb_typeof(patch) <> 'object' or patch = '{}'::jsonb then
    return jsonb_build_object('error', jsonb_build_object('code', 'DRAFT_VALIDATION_FAILED', 'message', 'Choose at least one Draft field to update.'));
  end if;
  select string_agg(key, ', ' order by key) into unsupported_fields
  from jsonb_object_keys(patch) keys(key)
  where key not in (
    'folder_id','title','caption','description','alt_text','tags','content_category','captured_at','location_name',
    'copyright_holder','copyright_year','contains_recognizable_people','model_release_status',
    'property_release_status','rights_declared','ai_disclosure','sensitive_content_disclosure'
  );
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
  if patch ? 'copyright_holder' and (
    jsonb_typeof(patch -> 'copyright_holder') not in ('string', 'null')
    or length(btrim(patch ->> 'copyright_holder')) > 160
  ) then
    return jsonb_build_object('error', jsonb_build_object('code', 'DRAFT_VALIDATION_FAILED', 'message', 'Copyright holder must use 160 characters or fewer.'));
  end if;
  if patch ? 'content_category' and (
    jsonb_typeof(patch -> 'content_category') not in ('string', 'null')
    or (nullif(btrim(patch ->> 'content_category'), '') is not null and btrim(patch ->> 'content_category') not in ('abstract', 'concrete'))
  ) then
    return jsonb_build_object('error', jsonb_build_object('code', 'DRAFT_VALIDATION_FAILED', 'message', 'Content category is invalid.'));
  end if;
  tags_value := case when patch ? 'tags' then patch -> 'tags' else version_row.tags end;
  if jsonb_typeof(tags_value) <> 'array'
     or jsonb_array_length(tags_value) > 30
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
  if patch ? 'copyright_year' and (
    jsonb_typeof(patch -> 'copyright_year') not in ('number', 'null')
    or (jsonb_typeof(patch -> 'copyright_year') = 'number' and patch ->> 'copyright_year' !~ '^[0-9]+$')
  ) then
    return jsonb_build_object('error', jsonb_build_object('code', 'DRAFT_VALIDATION_FAILED', 'message', 'Copyright year is invalid.'));
  end if;
  if patch ? 'copyright_year' and jsonb_typeof(patch -> 'copyright_year') = 'number' then
    begin
      copyright_year_value := (patch ->> 'copyright_year')::integer;
    exception when invalid_text_representation or numeric_value_out_of_range then
      return jsonb_build_object('error', jsonb_build_object('code', 'DRAFT_VALIDATION_FAILED', 'message', 'Copyright year is invalid.'));
    end;
    if copyright_year_value not between 1000 and extract(year from current_date)::integer + 1 then
      return jsonb_build_object('error', jsonb_build_object('code', 'DRAFT_VALIDATION_FAILED', 'message', 'Copyright year is invalid.'));
    end if;
  else
    copyright_year_value := case when patch ? 'copyright_year' then null else version_row.copyright_year end;
  end if;
  if patch ? 'contains_recognizable_people' and jsonb_typeof(patch -> 'contains_recognizable_people') not in ('boolean', 'null') then
    return jsonb_build_object('error', jsonb_build_object('code', 'DRAFT_VALIDATION_FAILED', 'message', 'Recognizable people selection is invalid.'));
  end if;
  if patch ? 'rights_declared' and jsonb_typeof(patch -> 'rights_declared') <> 'boolean' then
    return jsonb_build_object('error', jsonb_build_object('code', 'DRAFT_VALIDATION_FAILED', 'message', 'Rights declaration is invalid.'));
  end if;
  if patch ? 'model_release_status' and (
    jsonb_typeof(patch -> 'model_release_status') not in ('string', 'null')
    or (nullif(patch ->> 'model_release_status', '') is not null and patch ->> 'model_release_status' not in ('not_applicable', 'available', 'not_available', 'pending'))
  ) then
    return jsonb_build_object('error', jsonb_build_object('code', 'DRAFT_VALIDATION_FAILED', 'message', 'Model release status is invalid.'));
  end if;
  if patch ? 'property_release_status' and (
    jsonb_typeof(patch -> 'property_release_status') not in ('string', 'null')
    or (nullif(patch ->> 'property_release_status', '') is not null and patch ->> 'property_release_status' not in ('not_applicable', 'available', 'not_available', 'pending'))
  ) then
    return jsonb_build_object('error', jsonb_build_object('code', 'DRAFT_VALIDATION_FAILED', 'message', 'Property release status is invalid.'));
  end if;
  if patch ? 'ai_disclosure' and (
    jsonb_typeof(patch -> 'ai_disclosure') not in ('string', 'null')
    or (nullif(patch ->> 'ai_disclosure', '') is not null and patch ->> 'ai_disclosure' not in ('none', 'ai_edited', 'ai_generated'))
  ) then
    return jsonb_build_object('error', jsonb_build_object('code', 'DRAFT_VALIDATION_FAILED', 'message', 'AI disclosure is invalid.'));
  end if;
  if patch ? 'sensitive_content_disclosure' and (
    jsonb_typeof(patch -> 'sensitive_content_disclosure') not in ('string', 'null')
    or (nullif(patch ->> 'sensitive_content_disclosure', '') is not null and patch ->> 'sensitive_content_disclosure' not in ('none', 'contains_sensitive_content'))
  ) then
    return jsonb_build_object('error', jsonb_build_object('code', 'DRAFT_VALIDATION_FAILED', 'message', 'Sensitive content disclosure is invalid.'));
  end if;
  update public.image_versions set
    title = case when patch ? 'title' then btrim(patch ->> 'title') else title end,
    caption = case when patch ? 'caption' then btrim(patch ->> 'caption') else caption end,
    description = case when patch ? 'description' then btrim(patch ->> 'description') else description end,
    alt_text = case when patch ? 'alt_text' then btrim(patch ->> 'alt_text') else alt_text end,
    tags = tags_value,
    content_category = case when patch ? 'content_category' then nullif(btrim(patch ->> 'content_category'), '') else content_category end,
    captured_at = captured_value,
    location_name = case when patch ? 'location_name' then nullif(btrim(patch ->> 'location_name'), '') else location_name end,
    copyright_holder = case when patch ? 'copyright_holder' then nullif(btrim(patch ->> 'copyright_holder'), '') else copyright_holder end,
    copyright_year = copyright_year_value,
    contains_recognizable_people = case when patch ? 'contains_recognizable_people' then (patch ->> 'contains_recognizable_people')::boolean else contains_recognizable_people end,
    model_release_status = case when patch ? 'model_release_status' then nullif(patch ->> 'model_release_status', '') else model_release_status end,
    property_release_status = case when patch ? 'property_release_status' then nullif(patch ->> 'property_release_status', '') else property_release_status end,
    rights_declared = case when patch ? 'rights_declared' then (patch ->> 'rights_declared')::boolean else rights_declared end,
    ai_disclosure = case when patch ? 'ai_disclosure' then nullif(patch ->> 'ai_disclosure', '') else ai_disclosure end,
    sensitive_content_disclosure = case when patch ? 'sensitive_content_disclosure' then nullif(patch ->> 'sensitive_content_disclosure', '') else sensitive_content_disclosure end
  where id = version_row.id;
  update public.images set folder_id = selected_folder_id, updated_at = now(), version = version + 1 where id = image_row.id;
  return jsonb_build_object('draft', public.workspace_draft_json(image_row.id));
end;
$$;

grant execute on function public.workspace_update_draft(uuid, jsonb) to authenticated;
revoke all on function public.workspace_update_draft(uuid, jsonb) from anon, public;

commit;
