begin;

-- A deliberately narrow exception to the normal no-self-review boundary.
-- Only an active Super Admin at AAL2 may publish their own untouched,
-- unassigned submission. The regular assignment/start/decision RPCs retain
-- their existing self-review prohibition.
create or replace function public.review_super_admin_self_publish(
  submission_id uuid,
  expected_lock_version integer,
  reason_codes jsonb,
  user_message text,
  internal_note text,
  checklist_result jsonb,
  idempotency_key uuid
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  target_submission_id alias for $1;
  target_expected_lock_version alias for $2;
  submitted_reason_codes alias for $3;
  submitted_user_message alias for $4;
  submitted_internal_note alias for $5;
  submitted_checklist alias for $6;
  request_key alias for $7;
  actor_id uuid;
  actor_role public.role_code;
  submission_row public.review_submissions%rowtype;
  image_row public.images%rowtype;
  version_row public.image_versions%rowtype;
  existing_decision public.review_decisions%rowtype;
  decision_row public.review_decisions%rowtype;
  decision_id uuid;
  decision_created_at timestamptz;
  decision_completed_at timestamptz;
  decision_published_at timestamptz;
  decision_result_snapshot jsonb;
  active_asset_count integer;
  active_asset_kind_count integer;
  all_active_assets_clean boolean;
  violated_constraint text;
  before_state_snapshot jsonb;
  after_state_snapshot jsonb;
  before_asset_visibility jsonb;
  after_asset_visibility jsonb;
  decision_policy constant text := 'mt-review-2026-07-v1';
  checklist_codes constant text[] := array[
    'file_integrity', 'rights', 'privacy', 'minors', 'sensitive_content',
    'hate_illegal', 'property_release', 'third_party_ip', 'ai_disclosure', 'public_metadata'
  ];
begin
  actor_id := public.review_require_actor();
  actor_role := public.review_actor_role(actor_id);
  if actor_role <> 'super_admin'::public.role_code then
    return public.review_error(
      'REVIEW_SELF_PUBLISH_FORBIDDEN',
      'Only a Super Admin may use the audited self-publish action.'
    );
  end if;

  submitted_user_message := btrim(coalesce(submitted_user_message, ''));
  submitted_internal_note := nullif(btrim(coalesce(submitted_internal_note, '')), '');
  if request_key is null then
    return public.review_error('REVIEW_IDEMPOTENCY_REQUIRED', 'Start a new self-publish request.');
  end if;

  -- Replay only an exact, already-completed request before evaluating mutable
  -- submission state. The actor still has to be a current AAL2 Super Admin.
  select * into existing_decision
  from public.review_decisions d
  where d.idempotency_key = request_key::text;
  if existing_decision.id is not null then
    if existing_decision.submission_id is distinct from target_submission_id
       or existing_decision.reviewer_id is distinct from actor_id
       or existing_decision.decision <> 'approve_and_publish'::public.review_decision
       or existing_decision.reason_codes is distinct from submitted_reason_codes
       or existing_decision.user_message is distinct from submitted_user_message
       or existing_decision.internal_note is distinct from submitted_internal_note
       or existing_decision.checklist_result is distinct from submitted_checklist then
      return public.review_error(
        'REVIEW_IDEMPOTENCY_CONFLICT',
        'This self-publish key was already used with different review data.'
      );
    end if;
    return public.review_decision_result(existing_decision.id);
  end if;

  if target_expected_lock_version is null or target_expected_lock_version < 1 then
    return public.review_error('REVIEW_VERSION_REQUIRED', 'Reload the submission before publishing it.');
  end if;
  if submitted_reason_codes is null
     or jsonb_typeof(submitted_reason_codes) is distinct from 'array'
     or submitted_reason_codes <> '["policy_complete"]'::jsonb then
    return public.review_error('REVIEW_DECISION_INVALID', 'Confirm the complete review policy.');
  end if;
  if length(submitted_user_message) not between 5 and 1000
     or coalesce(length(submitted_internal_note), 0) > 2000 then
    return public.review_error(
      'REVIEW_DECISION_INVALID',
      'Provide a concise publication message and optional internal note.'
    );
  end if;
  if submitted_checklist is null
     or jsonb_typeof(submitted_checklist) is distinct from 'object'
     or not (submitted_checklist ?& checklist_codes)
     or (select count(*) from jsonb_object_keys(submitted_checklist)) <> cardinality(checklist_codes)
     or exists (
       select 1 from jsonb_each(submitted_checklist) item
       where item.key <> all(checklist_codes) or item.value <> 'true'::jsonb
     ) then
    return public.review_error(
      'REVIEW_CHECKLIST_INCOMPLETE',
      'Complete every policy checklist item before publishing.'
    );
  end if;

  select * into submission_row
  from public.review_submissions s
  where s.id = target_submission_id
  for update;
  if submission_row.id is null then
    return public.review_error('REVIEW_SUBMISSION_NOT_FOUND', 'The review submission is unavailable.');
  end if;

  -- A concurrent request with the same key can commit while this transaction
  -- waits for the submission lock.
  select * into existing_decision
  from public.review_decisions d
  where d.idempotency_key = request_key::text;
  if existing_decision.id is not null then
    if existing_decision.submission_id is distinct from target_submission_id
       or existing_decision.reviewer_id is distinct from actor_id
       or existing_decision.decision <> 'approve_and_publish'::public.review_decision
       or existing_decision.reason_codes is distinct from submitted_reason_codes
       or existing_decision.user_message is distinct from submitted_user_message
       or existing_decision.internal_note is distinct from submitted_internal_note
       or existing_decision.checklist_result is distinct from submitted_checklist then
      return public.review_error(
        'REVIEW_IDEMPOTENCY_CONFLICT',
        'This self-publish key was already used with different review data.'
      );
    end if;
    return public.review_decision_result(existing_decision.id);
  end if;

  if submission_row.submitted_by_user_id is distinct from actor_id then
    return public.review_error(
      'REVIEW_SELF_PUBLISH_FORBIDDEN',
      'This action is limited to the Super Admin owner of the submission.'
    );
  end if;
  if submission_row.assigned_reviewer_id is not null
     or submission_row.review_started_at is not null then
    return public.review_error(
      'REVIEW_ALREADY_ASSIGNED',
      'This submission has already entered the independent review workflow.'
    );
  end if;
  if submission_row.status <> 'submitted'::public.submission_status
     or submission_row.completed_at is not null then
    return public.review_error(
      'REVIEW_STATE_CONFLICT',
      'Only an untouched submitted work can use Super Admin self-publish.'
    );
  end if;
  if submission_row.lock_version <> target_expected_lock_version then
    return public.review_error('REVIEW_VERSION_CONFLICT', 'This submission changed. Reload before publishing it.');
  end if;

  select * into image_row
  from public.images i
  where i.id = submission_row.image_id
  for update;
  select * into version_row
  from public.image_versions v
  where v.id = submission_row.image_version_id
  for share;
  if image_row.id is null or version_row.id is null then
    return public.review_error('REVIEW_STATE_CONFLICT', 'The submitted image version is unavailable.');
  end if;
  if image_row.deleted_at is not null
     or image_row.processing_status <> 'ready'::public.processing_status
     or image_row.workflow_status <> 'submitted'::public.workflow_status
     or image_row.current_version_id is distinct from submission_row.image_version_id
     or version_row.image_id is distinct from image_row.id
     or version_row.locked_at is null
     or submission_row.readiness_snapshot -> 'ready' is distinct from 'true'::jsonb then
    return public.review_error(
      'REVIEW_STATE_CONFLICT',
      'The submitted image is no longer ready for this publication decision.'
    );
  end if;
  if image_row.publication_status = 'published'::public.publication_status then
    return public.review_error('REVIEW_ALREADY_PUBLISHED', 'This work is already published.');
  end if;

  select
    count(*)::integer,
    count(distinct a.kind)::integer,
    coalesce(bool_and(
      a.scan_status = 'clean'
      and a.scan_policy_version = 'mt-asset-scan-2026-07-v1'
    ), false)
  into active_asset_count, active_asset_kind_count, all_active_assets_clean
  from public.image_assets a
  where a.image_id = image_row.id
    and a.deleted_at is null
    and a.kind in ('original', 'display', 'thumbnail');
  if active_asset_count <> 3
     or active_asset_kind_count <> 3
     or not all_active_assets_clean then
    return public.review_error(
      'REVIEW_ASSETS_NOT_READY',
      'All three current image assets must pass security scanning.'
    );
  end if;

  select coalesce(
    jsonb_object_agg(a.kind, a.storage_visibility order by a.kind),
    '{}'::jsonb
  ) into before_asset_visibility
  from public.image_assets a
  where a.image_id = image_row.id
    and a.kind in ('display', 'thumbnail')
    and a.deleted_at is null;

  before_state_snapshot := jsonb_build_object(
    'submission_status', submission_row.status,
    'assigned_reviewer_id', submission_row.assigned_reviewer_id,
    'review_started_at', submission_row.review_started_at,
    'completed_at', submission_row.completed_at,
    'submission_lock_version', submission_row.lock_version,
    'workflow_status', image_row.workflow_status,
    'publication_status', image_row.publication_status,
    'image_version_id', image_row.current_version_id,
    'published_at', image_row.published_at,
    'unpublished_at', image_row.unpublished_at,
    'image_lock_version', image_row.version,
    'asset_storage_visibility', before_asset_visibility,
    'self_publish_override', true
  );

  decision_id := gen_random_uuid();
  decision_created_at := now();
  decision_completed_at := now();
  decision_published_at := coalesce(image_row.published_at, now());
  decision_result_snapshot := jsonb_build_object(
    'decision', jsonb_build_object(
      'id', decision_id,
      'decision', 'approve_and_publish',
      'created_at', decision_created_at
    ),
    'submission', jsonb_build_object(
      'id', submission_row.id,
      'status', 'approved',
      'lock_version', submission_row.lock_version + 1,
      'completed_at', decision_completed_at
    ),
    'image', jsonb_build_object(
      'id', image_row.id,
      'workflow_status', 'approved',
      'publication_status', 'published',
      'current_version_id', image_row.current_version_id,
      'published_at', decision_published_at
    )
  );

  begin
    insert into public.review_decisions (
      id, submission_id, reviewer_id, decision, reason_codes, user_message,
      internal_note, checklist_result, policy_version, idempotency_key,
      expected_lock_version, result_snapshot, created_at
    ) values (
      decision_id, submission_row.id, actor_id, 'approve_and_publish', submitted_reason_codes,
      submitted_user_message, submitted_internal_note, submitted_checklist, decision_policy,
      request_key::text, target_expected_lock_version, decision_result_snapshot,
      decision_created_at
    ) returning * into decision_row;
  exception when unique_violation then
    get stacked diagnostics violated_constraint = constraint_name;
    if violated_constraint is distinct from 'review_decisions_idempotency_key_key' then
      raise;
    end if;
    select * into existing_decision
    from public.review_decisions d
    where d.idempotency_key = request_key::text;
    if existing_decision.id is not null
       and existing_decision.submission_id is not distinct from target_submission_id
       and existing_decision.reviewer_id is not distinct from actor_id
       and existing_decision.decision = 'approve_and_publish'::public.review_decision
       and existing_decision.reason_codes is not distinct from submitted_reason_codes
       and existing_decision.user_message is not distinct from submitted_user_message
       and existing_decision.internal_note is not distinct from submitted_internal_note
       and existing_decision.checklist_result is not distinct from submitted_checklist then
      return public.review_decision_result(existing_decision.id);
    end if;
    return public.review_error('REVIEW_IDEMPOTENCY_CONFLICT', 'This self-publish key conflicts with another action.');
  end;

  update public.review_submissions s set
    status = 'approved'::public.submission_status,
    completed_at = decision_completed_at,
    lock_version = s.lock_version + 1
  where s.id = submission_row.id
  returning * into submission_row;

  update public.images i set
    workflow_status = 'approved'::public.workflow_status,
    publication_status = 'published'::public.publication_status,
    published_at = decision_published_at,
    unpublished_at = null,
    version = i.version + 1,
    updated_at = now()
  where i.id = image_row.id
  returning * into image_row;

  update public.image_assets a set storage_visibility = 'public'
  where a.image_id = image_row.id
    and a.kind in ('display', 'thumbnail')
    and a.deleted_at is null;

  select coalesce(
    jsonb_object_agg(a.kind, a.storage_visibility order by a.kind),
    '{}'::jsonb
  ) into after_asset_visibility
  from public.image_assets a
  where a.image_id = image_row.id
    and a.kind in ('display', 'thumbnail')
    and a.deleted_at is null;

  insert into public.notifications (recipient_user_id, type, payload)
  values (submission_row.submitted_by_user_id, 'image_published', jsonb_build_object(
    'image_id', image_row.id,
    'submission_id', submission_row.id,
    'decision_id', decision_row.id,
    'decision', 'approve_and_publish',
    'reason_codes', submitted_reason_codes,
    'message', submitted_user_message,
    'publication_status', image_row.publication_status,
    'self_publish_override', true
  ));

  after_state_snapshot := jsonb_build_object(
    'submission_status', submission_row.status,
    'assigned_reviewer_id', submission_row.assigned_reviewer_id,
    'review_started_at', submission_row.review_started_at,
    'completed_at', submission_row.completed_at,
    'submission_lock_version', submission_row.lock_version,
    'workflow_status', image_row.workflow_status,
    'publication_status', image_row.publication_status,
    'image_version_id', image_row.current_version_id,
    'published_at', image_row.published_at,
    'unpublished_at', image_row.unpublished_at,
    'image_lock_version', image_row.version,
    'asset_storage_visibility', after_asset_visibility,
    'decision_id', decision_row.id,
    'self_publish_override', true
  );

  insert into public.audit_logs (
    actor_user_id, actor_role, action, target_type, target_id, request_id,
    reason_code, before_state, after_state, policy_version, result
  ) values (
    actor_id, actor_role, 'review.super_admin_self_publish', 'review_submission',
    submission_row.id::text, request_key::text, submitted_reason_codes ->> 0,
    before_state_snapshot, after_state_snapshot, decision_policy, 'success'
  );

  return public.review_decision_result(decision_row.id);
end;
$$;

revoke all on function public.review_super_admin_self_publish(
  uuid, integer, jsonb, text, text, jsonb, uuid
) from public, anon, authenticated, service_role;
grant execute on function public.review_super_admin_self_publish(
  uuid, integer, jsonb, text, text, jsonb, uuid
) to authenticated;

commit;
