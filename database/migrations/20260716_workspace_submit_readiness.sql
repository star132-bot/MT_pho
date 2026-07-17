-- Phase 2E: authoritative Submit readiness and immutable review snapshots.
begin;

alter table public.review_submissions
  add column if not exists idempotency_key uuid,
  add column if not exists readiness_snapshot jsonb,
  add column if not exists asset_snapshot jsonb;

update public.review_submissions
set idempotency_key = gen_random_uuid()
where idempotency_key is null;

update public.review_submissions s
set readiness_snapshot = jsonb_build_object(
  'image_id', s.image_id,
  'lock_version', coalesce((select i.version from public.images i where i.id = s.image_id), 1),
  'workflow_status', coalesce((select i.workflow_status::text from public.images i where i.id = s.image_id), 'submitted'),
  'status', 'blocked',
  'ready', false,
  'blocker_count', 5,
  'field_errors', jsonb_build_object('submission_state', 'Legacy submission snapshots require verification.'),
  'checks', jsonb_build_array(
    jsonb_build_object('code', 'work_details', 'label', 'Work details', 'state', 'fail', 'message', 'Legacy readiness was not recorded.'),
    jsonb_build_object('code', 'rights_disclosures', 'label', 'Rights & disclosures', 'state', 'fail', 'message', 'Legacy readiness was not recorded.'),
    jsonb_build_object('code', 'image_assets', 'label', 'Image assets', 'state', 'fail', 'message', 'Legacy readiness was not recorded.'),
    jsonb_build_object('code', 'security_scan', 'label', 'Security scan', 'state', 'fail', 'message', 'Legacy readiness was not recorded.'),
    jsonb_build_object('code', 'submission_state', 'label', 'Submission state', 'state', 'fail', 'message', 'Legacy readiness was not recorded.')
  )
)
where readiness_snapshot is null;

update public.review_submissions s
set asset_snapshot = coalesce((
  select jsonb_agg(jsonb_build_object(
    'id', a.id,
    'kind', a.kind,
    'mime_type', a.mime_type,
    'byte_size', a.byte_size,
    'width', a.width,
    'height', a.height,
    'checksum_sha256', a.checksum_sha256,
    'scan_status', a.scan_status,
    'scan_policy_version', to_jsonb(a) ->> 'scan_policy_version'
  ) order by case a.kind when 'original' then 1 when 'display' then 2 else 3 end)
  from public.image_assets a
  where a.image_id = s.image_id and a.deleted_at is null
), '[]'::jsonb)
where asset_snapshot is null;

alter table public.review_submissions
  alter column idempotency_key set not null,
  alter column readiness_snapshot set not null,
  alter column asset_snapshot set not null;

create unique index if not exists review_submissions_idempotency_key
  on public.review_submissions (idempotency_key);

do $$
begin
  if not exists (
    select 1 from pg_constraint
    where conrelid = 'public.review_submissions'::regclass
      and conname = 'review_submissions_lock_version_positive'
  ) then
    alter table public.review_submissions
      add constraint review_submissions_lock_version_positive
      check (lock_version > 0);
  end if;
  if not exists (
    select 1 from pg_constraint
    where conrelid = 'public.review_submissions'::regclass
      and conname = 'review_submissions_readiness_snapshot_object'
  ) then
    alter table public.review_submissions
      add constraint review_submissions_readiness_snapshot_object
      check (
        jsonb_typeof(readiness_snapshot) = 'object'
        and jsonb_typeof(readiness_snapshot -> 'checks') = 'array'
        and jsonb_array_length(readiness_snapshot -> 'checks') = 5
      );
  end if;
  if not exists (
    select 1 from pg_constraint
    where conrelid = 'public.review_submissions'::regclass
      and conname = 'review_submissions_asset_snapshot_complete'
  ) then
    alter table public.review_submissions
      add constraint review_submissions_asset_snapshot_complete
      check (jsonb_typeof(asset_snapshot) = 'array' and jsonb_array_length(asset_snapshot) = 3)
      not valid;
  end if;
end
$$;

-- Submission creation is a business transaction. Owners may read their own
-- rows, but cannot forge status, reviewer, policy, or snapshot fields.
drop policy if exists submissions_owner_insert on public.review_submissions;
revoke insert, update, delete on public.review_submissions from authenticated;

create or replace function public.protect_locked_image_version()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
  if old.locked_at is not null then
    raise exception 'locked image versions are immutable' using errcode = '55000';
  end if;
  if tg_op = 'DELETE' then
    return old;
  end if;
  return new;
end;
$$;
revoke all on function public.protect_locked_image_version() from public, anon, authenticated;

drop trigger if exists image_versions_locked_immutable on public.image_versions;
create trigger image_versions_locked_immutable
before update or delete on public.image_versions
for each row execute function public.protect_locked_image_version();

create or replace function public.protect_review_submission_snapshot()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
  if tg_op = 'DELETE' then
    raise exception 'review submission snapshots are immutable' using errcode = '55000';
  end if;
  if new.image_id is distinct from old.image_id
     or new.image_version_id is distinct from old.image_version_id
     or new.submitted_by_user_id is distinct from old.submitted_by_user_id
     or new.idempotency_key is distinct from old.idempotency_key
     or new.policy_version is distinct from old.policy_version
     or new.readiness_snapshot is distinct from old.readiness_snapshot
     or new.asset_snapshot is distinct from old.asset_snapshot
     or new.submitted_at is distinct from old.submitted_at then
    raise exception 'review submission snapshots are immutable' using errcode = '55000';
  end if;
  return new;
end;
$$;
revoke all on function public.protect_review_submission_snapshot() from public, anon, authenticated;

drop trigger if exists review_submissions_snapshot_immutable on public.review_submissions;
create trigger review_submissions_snapshot_immutable
before update or delete on public.review_submissions
for each row execute function public.protect_review_submission_snapshot();

-- Canceled upload intents have no image_assets rows and can still be cleaned
-- with the owner token. Once an object is registered as an asset, only a
-- privileged retention worker may remove it from Storage.
drop policy if exists storage_owner_delete on storage.objects;
create policy storage_owner_delete on storage.objects
for delete to authenticated
using (
  bucket_id in ('image-originals', 'image-display', 'image-thumbnails')
  and owner_id = (select auth.uid()::text)
  and not exists (
    select 1
    from public.image_assets a
    where a.owner_user_id = (select public.current_app_user_id())
      and a.storage_key = name
      and case a.kind
        when 'original' then 'image-originals'
        when 'display' then 'image-display'
        else 'image-thumbnails'
      end = bucket_id
  )
);

create or replace function public.workspace_submit_readiness_json(
  target_image_id uuid,
  app_user_id uuid
)
returns jsonb
language plpgsql
stable
security definer
set search_path = ''
as $$
declare
  image_row public.images%rowtype;
  version_row public.image_versions%rowtype;
  field_errors jsonb := '{}'::jsonb;
  work_state text := 'pass';
  work_message text := 'Required work details are complete.';
  rights_state text := 'pass';
  rights_message text := 'Rights and disclosure selections are complete.';
  assets_state text := 'pass';
  assets_message text := 'Original, display, and thumbnail assets are available.';
  scan_state text := 'pass';
  scan_message text := 'All asset security scans passed.';
  submission_state text := 'pass';
  submission_message text := 'This Draft can enter the review queue.';
  result_status text;
  blocker_count integer;
  active_asset_count integer := 0;
  active_asset_kind_count integer := 0;
  storage_object_count integer := 0;
  asset_metadata_valid boolean := false;
  all_scans_clean boolean := false;
  has_pending_scan boolean := false;
  has_blocked_scan boolean := false;
  has_open_submission boolean := false;
begin
  select * into image_row
  from public.images i
  where i.id = target_image_id and i.owner_user_id = app_user_id;

  if image_row.id is not null and image_row.current_version_id is not null then
    select * into version_row
    from public.image_versions v
    where v.id = image_row.current_version_id and v.image_id = image_row.id;
  end if;

  if version_row.id is null then
    work_state := 'fail';
    work_message := 'The current Draft version is unavailable.';
    rights_state := 'fail';
    rights_message := 'The current Draft version is unavailable.';
    field_errors := field_errors || jsonb_build_object('submission_state', 'Reload an available Draft before submitting.');
  else
    if nullif(btrim(version_row.title), '') is null then
      field_errors := field_errors || jsonb_build_object('title', 'Title is required.');
    end if;
    if nullif(btrim(version_row.alt_text), '') is null then
      field_errors := field_errors || jsonb_build_object('alt_text', 'Alt text is required.');
    end if;
    if version_row.content_category is null or version_row.content_category not in ('abstract', 'concrete') then
      field_errors := field_errors || jsonb_build_object('content_category', 'Choose a content category.');
    end if;
    if field_errors ?| array['title', 'alt_text', 'content_category'] then
      work_state := 'fail';
      work_message := 'Complete the required title, alt text, and content category.';
    end if;

    if nullif(btrim(version_row.copyright_holder), '') is null then
      field_errors := field_errors || jsonb_build_object('copyright_holder', 'Copyright holder is required.');
    end if;
    if version_row.copyright_year is null
       or version_row.copyright_year not between 1000 and extract(year from current_date)::integer + 1 then
      field_errors := field_errors || jsonb_build_object('copyright_year', 'Confirm a valid copyright year.');
    end if;
    if version_row.contains_recognizable_people is null then
      field_errors := field_errors || jsonb_build_object('contains_recognizable_people', 'Choose whether the image contains recognizable people.');
    elsif version_row.contains_recognizable_people and (
      version_row.model_release_status is null
      or version_row.model_release_status not in ('available', 'not_available', 'pending')
    ) then
      field_errors := field_errors || jsonb_build_object('model_release_status', 'Choose a model release status.');
    elsif not version_row.contains_recognizable_people
          and version_row.model_release_status is distinct from 'not_applicable' then
      field_errors := field_errors || jsonb_build_object('model_release_status', 'Model release must be Not Applicable when no recognizable people are present.');
    end if;
    if version_row.property_release_status is null then
      field_errors := field_errors || jsonb_build_object('property_release_status', 'Choose a property release status, including Not Applicable.');
    end if;
    if not version_row.rights_declared then
      field_errors := field_errors || jsonb_build_object('rights_declared', 'Confirm that you own or control the required rights.');
    end if;
    if version_row.ai_disclosure is null then
      field_errors := field_errors || jsonb_build_object('ai_disclosure', 'Choose an AI disclosure.');
    end if;
    if version_row.sensitive_content_disclosure is null then
      field_errors := field_errors || jsonb_build_object('sensitive_content_disclosure', 'Choose a sensitive-content disclosure.');
    end if;
    if field_errors ?| array[
      'copyright_holder', 'copyright_year', 'contains_recognizable_people',
      'model_release_status', 'property_release_status', 'rights_declared',
      'ai_disclosure', 'sensitive_content_disclosure'
    ] then
      rights_state := 'fail';
      rights_message := 'Complete the required rights and disclosure fields.';
    end if;
  end if;

  if image_row.id is not null then
    select
      count(*)::integer,
      count(distinct a.kind)::integer,
      coalesce(bool_and(
        a.owner_user_id = app_user_id
        and a.kind in ('original', 'display', 'thumbnail')
        and a.checksum_sha256 is not null
        and a.checksum_sha256::text ~ '^[0-9a-f]{64}$'
        and a.storage_visibility = 'private'
        and case when a.kind = 'original' then
          image_row.original_width is not null
          and image_row.original_height is not null
          and image_row.checksum_sha256 is not null
          and a.width = image_row.original_width
          and a.height = image_row.original_height
          and a.checksum_sha256 = image_row.checksum_sha256
        else true end
      ), false),
      coalesce(bool_and(
        a.scan_status = 'clean'
        and coalesce(to_jsonb(a) ->> 'scan_policy_version', '') = 'mt-asset-scan-2026-07-v1'
      ), false),
      coalesce(bool_or(
        a.scan_status = 'pending'
        or (
          a.scan_status = 'clean'
          and coalesce(to_jsonb(a) ->> 'scan_policy_version', '') <> 'mt-asset-scan-2026-07-v1'
        )
      ), false),
      coalesce(bool_or(a.scan_status in ('flagged', 'failed')), false)
    into
      active_asset_count,
      active_asset_kind_count,
      asset_metadata_valid,
      all_scans_clean,
      has_pending_scan,
      has_blocked_scan
    from public.image_assets a
    where a.image_id = image_row.id and a.deleted_at is null;

    select count(distinct a.id)::integer into storage_object_count
    from public.image_assets a
    join storage.objects o
      on o.name = a.storage_key
     and o.bucket_id = case a.kind
       when 'original' then 'image-originals'
       when 'display' then 'image-display'
       else 'image-thumbnails'
     end
     and o.owner_id = app_user_id::text
     and lower(coalesce(o.metadata ->> 'mimetype', '')) = lower(a.mime_type)
     and coalesce(o.metadata ->> 'size', '') = a.byte_size::text
    where a.image_id = image_row.id and a.deleted_at is null;

    select exists (
      select 1 from public.review_submissions s
      where s.image_id = image_row.id
        and s.status in (
          'submitted'::public.submission_status,
          'in_review'::public.submission_status,
          'escalated'::public.submission_status
        )
    ) into has_open_submission;
  end if;

  if active_asset_count <> 3
     or active_asset_kind_count <> 3
     or not asset_metadata_valid
     or storage_object_count <> 3 then
    assets_state := 'fail';
    assets_message := 'Original, display, and thumbnail assets must be complete and available.';
    field_errors := field_errors || jsonb_build_object('image_assets', 'Three complete private image assets are required.');
  end if;

  if assets_state = 'fail' then
    scan_state := 'fail';
    scan_message := 'Security scans require a complete asset set.';
    field_errors := field_errors || jsonb_build_object('security_scan', 'Complete all image assets before security scanning.');
  elsif has_blocked_scan then
    scan_state := 'fail';
    scan_message := 'One or more asset security scans did not pass.';
    field_errors := field_errors || jsonb_build_object('security_scan', 'Resolve flagged or failed asset scans before submitting.');
  elsif all_scans_clean then
    scan_state := 'pass';
  elsif has_pending_scan then
    scan_state := 'pending';
    scan_message := 'Asset security scanning is still in progress.';
  else
    scan_state := 'fail';
    scan_message := 'Asset security scan state is unavailable.';
    field_errors := field_errors || jsonb_build_object('security_scan', 'Resolve the asset security scan state before submitting.');
  end if;

  if image_row.id is null
     or image_row.deleted_at is not null
     or image_row.processing_status <> 'ready'::public.processing_status
     or image_row.workflow_status not in (
       'draft'::public.workflow_status,
       'changes_requested'::public.workflow_status
     )
     or image_row.publication_status not in (
       'never_published'::public.publication_status,
       'unpublished'::public.publication_status
     )
     or version_row.id is null
     or version_row.locked_at is not null
     or has_open_submission then
    submission_state := 'fail';
    submission_message := 'This image is not in an editable Draft state.';
    field_errors := field_errors || jsonb_build_object('submission_state', 'Reload an active, ready Draft before submitting.');
  end if;

  blocker_count :=
    (case when work_state <> 'pass' then 1 else 0 end)
    + (case when rights_state <> 'pass' then 1 else 0 end)
    + (case when assets_state <> 'pass' then 1 else 0 end)
    + (case when scan_state <> 'pass' then 1 else 0 end)
    + (case when submission_state <> 'pass' then 1 else 0 end);
  result_status := case
    when work_state = 'fail'
      or rights_state = 'fail'
      or assets_state = 'fail'
      or scan_state = 'fail'
      or submission_state = 'fail' then 'blocked'
    when scan_state = 'pending' then 'pending'
    else 'ready'
  end;

  return jsonb_build_object(
    'image_id', image_row.id,
    'lock_version', image_row.version,
    'workflow_status', image_row.workflow_status,
    'status', result_status,
    'ready', result_status = 'ready',
    'blocker_count', blocker_count,
    'field_errors', field_errors,
    'checks', jsonb_build_array(
      jsonb_build_object('code', 'work_details', 'label', 'Work details', 'state', work_state, 'message', work_message),
      jsonb_build_object('code', 'rights_disclosures', 'label', 'Rights & disclosures', 'state', rights_state, 'message', rights_message),
      jsonb_build_object('code', 'image_assets', 'label', 'Image assets', 'state', assets_state, 'message', assets_message),
      jsonb_build_object('code', 'security_scan', 'label', 'Security scan', 'state', scan_state, 'message', scan_message),
      jsonb_build_object('code', 'submission_state', 'label', 'Submission state', 'state', submission_state, 'message', submission_message)
    )
  );
end;
$$;
revoke all on function public.workspace_submit_readiness_json(uuid, uuid) from public, anon, authenticated;

create or replace function public.workspace_get_submit_readiness(image_id uuid)
returns jsonb
language plpgsql
stable
security definer
set search_path = ''
as $$
declare
  app_user_id uuid;
begin
  app_user_id := public.require_active_workspace_user();
  if not exists (
    select 1 from public.images i
    where i.id = image_id
      and i.owner_user_id = app_user_id
      and i.deleted_at is null
  ) then
    return jsonb_build_object('error', jsonb_build_object(
      'code', 'DRAFT_NOT_FOUND',
      'message', 'The Draft is unavailable.'
    ));
  end if;
  return jsonb_build_object(
    'readiness', public.workspace_submit_readiness_json(image_id, app_user_id)
  );
end;
$$;

create or replace function public.workspace_submit_result_json(target_submission_id uuid)
returns jsonb
language sql
stable
security definer
set search_path = ''
as $$
  select jsonb_build_object(
    'submitted', true,
    'submission', jsonb_build_object(
      'id', s.id,
      'image_id', s.image_id,
      'image_version_id', s.image_version_id,
      'status', 'submitted',
      'policy_version', s.policy_version,
      'submitted_at', s.submitted_at
    ),
    'image', jsonb_build_object(
      'id', s.image_id,
      'workflow_status', 'submitted',
      'lock_version', (s.readiness_snapshot ->> 'lock_version')::integer + 1
    )
  )
  from public.review_submissions s
  where s.id = target_submission_id
$$;
revoke all on function public.workspace_submit_result_json(uuid) from public, anon, authenticated;

create or replace function public.workspace_submit_draft_versioned(
  image_id uuid,
  expected_version integer,
  idempotency_key uuid
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  target_image_id alias for $1;
  target_expected_version alias for $2;
  request_key alias for $3;
  app_user_id uuid;
  image_row public.images%rowtype;
  version_row public.image_versions%rowtype;
  submission_row public.review_submissions%rowtype;
  existing_submission public.review_submissions%rowtype;
  readiness jsonb;
  asset_snapshot jsonb;
  scan_check_state text;
  workflow_before public.workflow_status;
  violated_constraint text;
  policy_version_constant constant text := 'mt-submission-2026-07-v1';
begin
  if target_expected_version is null or target_expected_version < 1 then
    return jsonb_build_object('error', jsonb_build_object(
      'code', 'DRAFT_VERSION_REQUIRED',
      'message', 'Reload this Draft before submitting it.'
    ));
  end if;
  if request_key is null then
    return jsonb_build_object('error', jsonb_build_object(
      'code', 'SUBMISSION_IDEMPOTENCY_REQUIRED',
      'message', 'Start a new Submit request before trying again.'
    ));
  end if;

  app_user_id := public.require_active_workspace_user();
  select * into existing_submission
  from public.review_submissions s
  where s.submitted_by_user_id = app_user_id
    and s.idempotency_key = request_key;
  if existing_submission.id is not null then
    if existing_submission.image_id <> target_image_id then
      return jsonb_build_object('error', jsonb_build_object(
        'code', 'SUBMISSION_IDEMPOTENCY_CONFLICT',
        'message', 'This Submit request key was already used for another image.'
      ));
    end if;
    return public.workspace_submit_result_json(existing_submission.id);
  end if;

  select * into image_row
  from public.images i
  where i.id = target_image_id and i.owner_user_id = app_user_id
  for update;
  if image_row.id is null then
    return jsonb_build_object('error', jsonb_build_object(
      'code', 'DRAFT_NOT_FOUND',
      'message', 'The Draft is unavailable.'
    ));
  end if;

  -- Recheck after the image lock so concurrent retries return the first result.
  select * into existing_submission
  from public.review_submissions s
  where s.submitted_by_user_id = app_user_id
    and s.idempotency_key = request_key;
  if existing_submission.id is not null then
    if existing_submission.image_id <> target_image_id then
      return jsonb_build_object('error', jsonb_build_object(
        'code', 'SUBMISSION_IDEMPOTENCY_CONFLICT',
        'message', 'This Submit request key was already used for another image.'
      ));
    end if;
    return public.workspace_submit_result_json(existing_submission.id);
  end if;

  if image_row.version <> target_expected_version then
    return jsonb_build_object('error', jsonb_build_object(
      'code', 'DRAFT_VERSION_CONFLICT',
      'message', 'A newer version of this Draft is available. Reload before submitting.'
    ));
  end if;
  workflow_before := image_row.workflow_status;

  select * into version_row
  from public.image_versions v
  where v.id = image_row.current_version_id and v.image_id = image_row.id
  for update;

  perform a.id
  from public.image_assets a
  where a.image_id = image_row.id and a.deleted_at is null
  for share;

  perform o.id
  from storage.objects o
  join public.image_assets a
    on a.storage_key = o.name
   and o.bucket_id = case a.kind
     when 'original' then 'image-originals'
     when 'display' then 'image-display'
     else 'image-thumbnails'
   end
  where a.image_id = image_row.id and a.deleted_at is null
  for share of o;

  readiness := public.workspace_submit_readiness_json(image_row.id, app_user_id);
  if not coalesce((readiness ->> 'ready')::boolean, false) then
    select entry ->> 'state' into scan_check_state
    from jsonb_array_elements(readiness -> 'checks') entry
    where entry ->> 'code' = 'security_scan';
    return jsonb_build_object('error', jsonb_build_object(
      'code', 'DRAFT_NOT_READY',
      'message', case when scan_check_state = 'pending'
        then 'Security scanning is still in progress.'
        else 'Complete the submission requirements before continuing.'
      end,
      'field_errors', readiness -> 'field_errors',
      'details', readiness
    ));
  end if;

  select jsonb_agg(jsonb_build_object(
    'id', a.id,
    'kind', a.kind,
    'mime_type', a.mime_type,
    'byte_size', a.byte_size,
    'width', a.width,
    'height', a.height,
    'checksum_sha256', a.checksum_sha256,
    'scan_status', a.scan_status,
    'scan_policy_version', to_jsonb(a) ->> 'scan_policy_version'
  ) order by case a.kind when 'original' then 1 when 'display' then 2 else 3 end)
  into asset_snapshot
  from public.image_assets a
  where a.image_id = image_row.id and a.deleted_at is null;

  begin
    insert into public.review_submissions (
      image_id,
      image_version_id,
      submitted_by_user_id,
      idempotency_key,
      status,
      policy_version,
      lock_version,
      readiness_snapshot,
      asset_snapshot
    ) values (
      image_row.id,
      version_row.id,
      app_user_id,
      request_key,
      'submitted'::public.submission_status,
      policy_version_constant,
      1,
      readiness,
      asset_snapshot
    ) returning * into submission_row;
  exception when unique_violation then
    get stacked diagnostics violated_constraint = constraint_name;
    select * into existing_submission
    from public.review_submissions s
    where s.submitted_by_user_id = app_user_id
      and s.idempotency_key = request_key;
    if existing_submission.id is not null and existing_submission.image_id = image_row.id then
      return public.workspace_submit_result_json(existing_submission.id);
    end if;
    if violated_constraint = 'review_submissions_one_open_per_image' then
      return jsonb_build_object('error', jsonb_build_object(
        'code', 'SUBMISSION_ALREADY_OPEN',
        'message', 'This image already has an open review submission.'
      ));
    end if;
    return jsonb_build_object('error', jsonb_build_object(
      'code', 'SUBMISSION_IDEMPOTENCY_CONFLICT',
      'message', 'This Submit request conflicts with an existing submission.'
    ));
  end;

  update public.image_versions v set locked_at = now()
  where v.id = version_row.id and v.locked_at is null;

  update public.images i set
    workflow_status = 'submitted'::public.workflow_status,
    version = i.version + 1,
    updated_at = now()
  where i.id = image_row.id
  returning * into image_row;

  insert into public.notifications (recipient_user_id, type, payload)
  values (
    app_user_id,
    'image_submitted',
    jsonb_build_object(
      'image_id', image_row.id,
      'submission_id', submission_row.id,
      'status', submission_row.status
    )
  );

  insert into public.audit_logs (
    actor_user_id,
    actor_role,
    action,
    target_type,
    target_id,
    request_id,
    reason_code,
    before_state,
    after_state,
    policy_version,
    result
  ) values (
    app_user_id,
    'user'::public.role_code,
    'workspace.submit_for_review',
    'review_submission',
    submission_row.id::text,
    request_key::text,
    'user_submit',
    jsonb_build_object(
      'image_id', image_row.id,
      'workflow_status', workflow_before,
      'lock_version', target_expected_version,
      'image_version_id', version_row.id
    ),
    jsonb_build_object(
      'image_id', image_row.id,
      'workflow_status', image_row.workflow_status,
      'lock_version', image_row.version,
      'image_version_id', version_row.id,
      'submission_id', submission_row.id
    ),
    policy_version_constant,
    'success'
  );

  return public.workspace_submit_result_json(submission_row.id);
end;
$$;

grant execute on function public.workspace_get_submit_readiness(uuid) to authenticated;
grant execute on function public.workspace_submit_draft_versioned(uuid, integer, uuid) to authenticated;
revoke all on function public.workspace_get_submit_readiness(uuid) from anon, public;
revoke all on function public.workspace_submit_draft_versioned(uuid, integer, uuid) from anon, public;

commit;
