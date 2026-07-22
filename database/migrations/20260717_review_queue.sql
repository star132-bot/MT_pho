begin;

-- Phase 3: reviewer queue, atomic assignment, review decisions, and publish.
-- Browser and Web server callers keep using the authenticated user's token;
-- all state changes are validated again inside these SECURITY DEFINER RPCs.

drop policy if exists reviewer_decisions_insert on public.review_decisions;
revoke insert, update, delete, truncate on public.review_decisions
  from public, anon, authenticated, service_role;
revoke insert, update, delete, truncate on public.review_submissions
  from public, anon, authenticated, service_role;
revoke insert, update, delete, truncate on public.audit_logs
  from public, anon, authenticated, service_role;

alter table public.review_decisions
  add column if not exists expected_lock_version integer,
  add column if not exists result_snapshot jsonb;

do $$
begin
  if exists (
    select 1
    from public.review_submissions s
    where s.status in (
      'in_review'::public.submission_status,
      'escalated'::public.submission_status
    )
      and s.assigned_reviewer_id is null
  ) then
    raise exception 'active review submissions require an assigned reviewer'
      using errcode = '23514';
  end if;
  if not exists (
    select 1
    from pg_constraint
    where conname = 'review_submissions_active_assignment'
      and conrelid = 'public.review_submissions'::regclass
  ) then
    alter table public.review_submissions
      add constraint review_submissions_active_assignment check (
        status not in (
          'in_review'::public.submission_status,
          'escalated'::public.submission_status
        )
        or assigned_reviewer_id is not null
      ) not valid;
  end if;
  alter table public.review_submissions
    validate constraint review_submissions_active_assignment;
end;
$$;

do $$
begin
  if exists (
    select 1 from public.review_decisions d
    where d.expected_lock_version is null or d.result_snapshot is null
  ) then
    raise exception 'existing review decisions require a controlled result snapshot backfill'
      using errcode = '23514';
  end if;
  alter table public.review_decisions
    alter column expected_lock_version set not null,
    alter column result_snapshot set not null;
end;
$$;

do $$
begin
  if not exists (
    select 1 from pg_constraint
    where conname = 'review_decisions_expected_lock_version_positive'
      and conrelid = 'public.review_decisions'::regclass
  ) then
    alter table public.review_decisions
      add constraint review_decisions_expected_lock_version_positive check (
        expected_lock_version is null or expected_lock_version > 0
      );
  end if;
  if not exists (
    select 1 from pg_constraint
    where conname = 'review_decisions_result_snapshot_object'
      and conrelid = 'public.review_decisions'::regclass
  ) then
    alter table public.review_decisions
      add constraint review_decisions_result_snapshot_object check (
        result_snapshot is null or jsonb_typeof(result_snapshot) = 'object'
      );
  end if;
end;
$$;

create or replace function public.is_recovery_auth_session()
returns boolean
language sql
stable
set search_path = ''
as $$
  select coalesce((
    select bool_or(entry ->> 'method' = 'recovery')
    from jsonb_array_elements(
      case
        when jsonb_typeof((select auth.jwt()) -> 'amr') = 'array'
          then (select auth.jwt()) -> 'amr'
        else '[]'::jsonb
      end
    ) entry
  ), false)
$$;

revoke all on function public.is_recovery_auth_session()
  from public, anon, authenticated, service_role;
grant execute on function public.is_recovery_auth_session() to authenticated;

create or replace function public.review_require_actor()
returns uuid
language plpgsql
stable
security definer
set search_path = ''
as $$
declare
  app_user_id uuid;
  has_reviewer boolean;
  has_privileged_role boolean;
begin
  if public.is_recovery_auth_session() then
    raise exception 'recovery session cannot access review administration' using errcode = '42501';
  end if;
  select public.current_app_user_id() into app_user_id;
  if app_user_id is null or not exists (
    select 1 from public.users u
    where u.id = app_user_id
      and u.account_status = 'active'::public.account_status
  ) then
    raise exception 'active review account required' using errcode = '42501';
  end if;

  select
    coalesce(bool_or(ur.role = 'reviewer'::public.role_code), false),
    coalesce(bool_or(ur.role in ('admin'::public.role_code, 'super_admin'::public.role_code)), false)
  into has_reviewer, has_privileged_role
  from public.user_roles ur
  where ur.user_id = app_user_id;

  if not has_reviewer and not has_privileged_role then
    raise exception 'review role required' using errcode = '42501';
  end if;
  if has_privileged_role and not (select public.has_aal2()) then
    raise exception 'aal2 required for administrator review access' using errcode = '42501';
  end if;
  return app_user_id;
end;
$$;

create or replace function public.review_actor_role(actor_id uuid)
returns public.role_code
language sql
stable
security definer
set search_path = ''
as $$
  select case
    when exists (
      select 1 from public.user_roles ur
      where ur.user_id = actor_id and ur.role = 'super_admin'::public.role_code
    ) then 'super_admin'::public.role_code
    when exists (
      select 1 from public.user_roles ur
      where ur.user_id = actor_id and ur.role = 'admin'::public.role_code
    ) then 'admin'::public.role_code
    else 'reviewer'::public.role_code
  end
$$;

create or replace function public.review_error(code text, message text)
returns jsonb
language sql
immutable
set search_path = ''
as $$
  select jsonb_build_object('error', jsonb_build_object('code', code, 'message', message))
$$;

revoke all on function public.review_require_actor() from public, anon, authenticated, service_role;
revoke all on function public.review_actor_role(uuid) from public, anon, authenticated, service_role;
revoke all on function public.review_error(text, text) from public, anon, authenticated, service_role;

create or replace function public.review_list_submissions(
  status_filter text default 'open',
  assignment_filter text default 'all',
  page_size integer default 30,
  page_offset integer default 0
)
returns jsonb
language plpgsql
stable
security definer
set search_path = ''
as $$
declare
  actor_id uuid;
  actor_role public.role_code;
  actor_roles jsonb;
  items jsonb;
  total_count integer;
  queue_counts jsonb;
begin
  actor_id := public.review_require_actor();
  actor_role := public.review_actor_role(actor_id);
  status_filter := coalesce(nullif(status_filter, ''), 'open');
  assignment_filter := coalesce(nullif(assignment_filter, ''), 'all');
  page_size := least(greatest(coalesce(page_size, 30), 1), 50);
  page_offset := greatest(coalesce(page_offset, 0), 0);

  if status_filter not in (
    'open', 'completed', 'all', 'submitted', 'in_review',
    'changes_requested', 'rejected', 'approved', 'withdrawn', 'escalated'
  ) then
    return public.review_error('REVIEW_FILTER_INVALID', 'Choose a supported review status filter.');
  end if;
  if assignment_filter not in ('all', 'unassigned', 'mine') then
    return public.review_error('REVIEW_FILTER_INVALID', 'Choose a supported assignment filter.');
  end if;

  select coalesce(jsonb_agg(ur.role order by ur.role), '[]'::jsonb)
  into actor_roles
  from public.user_roles ur
  where ur.user_id = actor_id;

  select count(*)::integer
  into total_count
  from public.review_submissions s
  where (
      actor_role in ('admin'::public.role_code, 'super_admin'::public.role_code)
      or (
        s.submitted_by_user_id <> actor_id
        and (
          (s.status = 'submitted'::public.submission_status and s.assigned_reviewer_id is null)
          or (
            s.assigned_reviewer_id = actor_id
            and s.status in (
              'submitted'::public.submission_status,
              'in_review'::public.submission_status,
              'escalated'::public.submission_status
            )
          )
        )
      )
    )
    and (
      status_filter = 'all'
      or (status_filter = 'open' and s.status in (
        'submitted'::public.submission_status,
        'in_review'::public.submission_status,
        'escalated'::public.submission_status
      ))
      or (status_filter = 'completed' and s.status in (
        'changes_requested'::public.submission_status,
        'rejected'::public.submission_status,
        'approved'::public.submission_status,
        'withdrawn'::public.submission_status
      ))
      or s.status::text = status_filter
    )
    and (
      assignment_filter = 'all'
      or (assignment_filter = 'unassigned' and s.assigned_reviewer_id is null)
      or (assignment_filter = 'mine' and s.assigned_reviewer_id = actor_id)
    );

  select coalesce(jsonb_agg(entry order by sort_rank, sort_submitted_at, sort_id), '[]'::jsonb)
  into items
  from (
    select jsonb_build_object(
      'id', s.id,
      'status', s.status,
      'lock_version', s.lock_version,
      'submitted_at', s.submitted_at,
      'review_started_at', s.review_started_at,
      'completed_at', s.completed_at,
      'policy_version', s.policy_version,
      'assigned_reviewer', case when assigned.id is null then null else jsonb_build_object(
        'id', assigned.id,
        'display_name', coalesce(assigned_profile.display_name, 'Reviewer')
      ) end,
      'owner', jsonb_build_object(
        'id', owner_user.id,
        'display_name', coalesce(owner_profile.display_name, 'Member')
      ),
      'image', jsonb_build_object(
        'id', i.id,
        'title', v.title,
        'original_filename', i.original_filename,
        'content_category', v.content_category,
        'publication_status', i.publication_status,
        'rights', jsonb_build_object(
          'declared', v.rights_declared,
          'recognizable_people', v.contains_recognizable_people,
          'model_release_status', v.model_release_status,
          'property_release_status', v.property_release_status
        ),
        'thumbnail_asset', case when thumbnail.id is null then null else jsonb_build_object(
          'id', thumbnail.id,
          'kind', thumbnail.kind,
          'storage_bucket', 'image-thumbnails',
          'storage_key', thumbnail.storage_key,
          'mime_type', thumbnail.mime_type,
          'width', thumbnail.width,
          'height', thumbnail.height,
          'scan_status', thumbnail.scan_status,
          'scan_policy_version', thumbnail.scan_policy_version
        ) end
      )
    ) as entry,
    case s.status
      when 'submitted'::public.submission_status then 1
      when 'in_review'::public.submission_status then 2
      when 'escalated'::public.submission_status then 3
      else 4
    end as sort_rank,
    s.submitted_at as sort_submitted_at,
    s.id as sort_id
    from public.review_submissions s
    join public.images i on i.id = s.image_id
    join public.image_versions v on v.id = s.image_version_id
    join public.users owner_user on owner_user.id = s.submitted_by_user_id
    left join public.user_profiles owner_profile on owner_profile.user_id = owner_user.id
    left join public.users assigned on assigned.id = s.assigned_reviewer_id
    left join public.user_profiles assigned_profile on assigned_profile.user_id = assigned.id
    left join lateral (
      select a.* from public.image_assets a
      where a.image_id = s.image_id
        and a.kind = 'thumbnail'
        and a.deleted_at is null
        and a.scan_status = 'clean'
        and a.scan_policy_version = 'mt-asset-scan-2026-07-v1'
      limit 1
    ) thumbnail on true
    where (
        actor_role in ('admin'::public.role_code, 'super_admin'::public.role_code)
        or (
          s.submitted_by_user_id <> actor_id
          and (
            (s.status = 'submitted'::public.submission_status and s.assigned_reviewer_id is null)
            or (
              s.assigned_reviewer_id = actor_id
              and s.status in (
                'submitted'::public.submission_status,
                'in_review'::public.submission_status,
                'escalated'::public.submission_status
              )
            )
          )
        )
      )
      and (
        status_filter = 'all'
        or (status_filter = 'open' and s.status in (
          'submitted'::public.submission_status,
          'in_review'::public.submission_status,
          'escalated'::public.submission_status
        ))
        or (status_filter = 'completed' and s.status in (
          'changes_requested'::public.submission_status,
          'rejected'::public.submission_status,
          'approved'::public.submission_status,
          'withdrawn'::public.submission_status
        ))
        or s.status::text = status_filter
      )
      and (
        assignment_filter = 'all'
        or (assignment_filter = 'unassigned' and s.assigned_reviewer_id is null)
        or (assignment_filter = 'mine' and s.assigned_reviewer_id = actor_id)
      )
    order by
      case s.status
        when 'submitted'::public.submission_status then 1
        when 'in_review'::public.submission_status then 2
        when 'escalated'::public.submission_status then 3
        else 4
      end,
      s.submitted_at,
      s.id
    limit page_size offset page_offset
  ) queue_entries;

  select jsonb_build_object(
    'open', count(*) filter (where s.status in (
      'submitted'::public.submission_status,
      'in_review'::public.submission_status,
      'escalated'::public.submission_status
    )),
    'submitted', count(*) filter (where s.status = 'submitted'::public.submission_status),
    'in_review', count(*) filter (where s.status = 'in_review'::public.submission_status),
    'completed', count(*) filter (where s.status in (
      'changes_requested'::public.submission_status,
      'rejected'::public.submission_status,
      'approved'::public.submission_status,
      'withdrawn'::public.submission_status
    ))
  ) into queue_counts
  from public.review_submissions s
  where actor_role in ('admin'::public.role_code, 'super_admin'::public.role_code)
    or (
      s.submitted_by_user_id <> actor_id
      and (
        (s.status = 'submitted'::public.submission_status and s.assigned_reviewer_id is null)
        or (
          s.assigned_reviewer_id = actor_id
          and s.status in (
            'submitted'::public.submission_status,
            'in_review'::public.submission_status,
            'escalated'::public.submission_status
          )
        )
      )
    );

  return jsonb_build_object(
    'actor', jsonb_build_object(
      'id', actor_id,
      'roles', actor_roles,
      'can_publish', actor_roles ?| array['admin', 'super_admin']
    ),
    'items', items,
    'counts', queue_counts,
    'pagination', jsonb_build_object(
      'offset', page_offset,
      'limit', page_size,
      'total', total_count,
      'has_more', page_offset + jsonb_array_length(items) < total_count
    )
  );
end;
$$;

create or replace function public.review_get_submission(submission_id uuid)
returns jsonb
language plpgsql
stable
security definer
set search_path = ''
as $$
declare
  actor_id uuid;
  actor_role public.role_code;
  actor_roles jsonb;
  result jsonb;
begin
  actor_id := public.review_require_actor();
  actor_role := public.review_actor_role(actor_id);
  select coalesce(jsonb_agg(ur.role order by ur.role), '[]'::jsonb)
  into actor_roles from public.user_roles ur where ur.user_id = actor_id;

  select jsonb_build_object(
    'actor', jsonb_build_object(
      'id', actor_id,
      'roles', actor_roles,
      'can_publish', actor_roles ?| array['admin', 'super_admin']
    ),
    'submission', jsonb_build_object(
      'id', s.id,
      'status', s.status,
      'lock_version', s.lock_version,
      'policy_version', s.policy_version,
      'submitted_at', s.submitted_at,
      'review_started_at', s.review_started_at,
      'completed_at', s.completed_at,
      'assigned_reviewer', case when assigned.id is null then null else jsonb_build_object(
        'id', assigned.id,
        'display_name', coalesce(assigned_profile.display_name, 'Reviewer')
      ) end,
      'readiness_snapshot', s.readiness_snapshot
    ),
    'owner', jsonb_build_object(
      'id', owner_user.id,
      'display_name', coalesce(owner_profile.display_name, 'Member'),
      'account_status', owner_user.account_status,
      'created_at', owner_user.created_at
    ),
    'image', jsonb_build_object(
      'id', i.id,
      'workflow_status', i.workflow_status,
      'publication_status', i.publication_status,
      'processing_status', i.processing_status,
      'published_at', i.published_at,
      'original_filename', i.original_filename,
      'original_width', i.original_width,
      'original_height', i.original_height,
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
        'public_exif', v.public_exif,
        'copyright_holder', v.copyright_holder,
        'copyright_year', v.copyright_year,
        'contains_recognizable_people', v.contains_recognizable_people,
        'model_release_status', v.model_release_status,
        'property_release_status', v.property_release_status,
        'rights_declared', v.rights_declared,
        'ai_disclosure', v.ai_disclosure,
        'sensitive_content_disclosure', v.sensitive_content_disclosure
      )
    ),
    'assets', coalesce((
      select jsonb_agg(jsonb_build_object(
        'id', a.id,
        'kind', a.kind,
        'storage_bucket', case a.kind
          when 'original' then 'image-originals'
          when 'display' then 'image-display'
          else 'image-thumbnails'
        end,
        'storage_key', a.storage_key,
        'mime_type', a.mime_type,
        'byte_size', a.byte_size,
        'width', a.width,
        'height', a.height,
        'checksum_sha256', a.checksum_sha256,
        'scan_status', a.scan_status,
        'scan_result_code', a.scan_result_code,
        'scan_policy_version', a.scan_policy_version
      ) order by case a.kind when 'original' then 1 when 'display' then 2 else 3 end)
      from public.image_assets a
      where a.image_id = s.image_id
        and a.deleted_at is null
        and a.scan_status = 'clean'
        and a.scan_policy_version = 'mt-asset-scan-2026-07-v1'
    ), '[]'::jsonb),
    'decisions', coalesce((
      select jsonb_agg(jsonb_build_object(
        'id', d.id,
        'decision', d.decision,
        'reason_codes', d.reason_codes,
        'user_message', d.user_message,
        'internal_note', case
          when actor_role in ('admin'::public.role_code, 'super_admin'::public.role_code)
            or d.reviewer_id = actor_id then d.internal_note
          else null
        end,
        'checklist_result', d.checklist_result,
        'policy_version', d.policy_version,
        'created_at', d.created_at,
        'reviewer', jsonb_build_object(
          'id', d.reviewer_id,
          'display_name', coalesce(decision_profile.display_name, 'Reviewer')
        )
      ) order by d.created_at)
      from public.review_decisions d
      left join public.user_profiles decision_profile on decision_profile.user_id = d.reviewer_id
      where d.submission_id = s.id
    ), '[]'::jsonb)
  ) into result
  from public.review_submissions s
  join public.images i on i.id = s.image_id
  join public.image_versions v on v.id = s.image_version_id
  join public.users owner_user on owner_user.id = s.submitted_by_user_id
  left join public.user_profiles owner_profile on owner_profile.user_id = owner_user.id
  left join public.users assigned on assigned.id = s.assigned_reviewer_id
  left join public.user_profiles assigned_profile on assigned_profile.user_id = assigned.id
  where s.id = submission_id
    and (
      actor_role in ('admin'::public.role_code, 'super_admin'::public.role_code)
      or (
        s.assigned_reviewer_id = actor_id
        and s.submitted_by_user_id <> actor_id
        and s.status in (
          'submitted'::public.submission_status,
          'in_review'::public.submission_status,
          'escalated'::public.submission_status
        )
      )
    );

  if result is null then
    return public.review_error('REVIEW_SUBMISSION_NOT_FOUND', 'The review submission is unavailable.');
  end if;
  return result;
end;
$$;

create or replace function public.review_decision_result(decision_id uuid)
returns jsonb
language sql
stable
security definer
set search_path = ''
as $$
  select d.result_snapshot
  from public.review_decisions d
  where d.id = decision_id
$$;

revoke all on function public.review_decision_result(uuid)
  from public, anon, authenticated, service_role;

create or replace function public.review_assign_submission(
  submission_id uuid,
  expected_lock_version integer
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  actor_id uuid;
  actor_role public.role_code;
  submission_row public.review_submissions%rowtype;
begin
  actor_id := public.review_require_actor();
  actor_role := public.review_actor_role(actor_id);
  if expected_lock_version is null or expected_lock_version < 1 then
    return public.review_error('REVIEW_VERSION_REQUIRED', 'Reload the submission before assigning it.');
  end if;

  select * into submission_row from public.review_submissions s
  where s.id = submission_id for update;
  if submission_row.id is null then
    return public.review_error('REVIEW_SUBMISSION_NOT_FOUND', 'The review submission is unavailable.');
  end if;
  if submission_row.submitted_by_user_id = actor_id then
    return public.review_error('REVIEW_SELF_REVIEW_FORBIDDEN', 'A submission cannot be reviewed by its owner.');
  end if;
  if submission_row.assigned_reviewer_id = actor_id
     and submission_row.status = 'submitted'::public.submission_status then
    return jsonb_build_object('submission', jsonb_build_object(
      'id', submission_row.id,
      'status', submission_row.status,
      'assigned_reviewer_id', actor_id,
      'lock_version', submission_row.lock_version
    ));
  end if;
  if submission_row.lock_version <> expected_lock_version then
    return public.review_error('REVIEW_VERSION_CONFLICT', 'This submission changed. Reload before assigning it.');
  end if;
  if submission_row.status <> 'submitted'::public.submission_status then
    return public.review_error('REVIEW_STATE_CONFLICT', 'Only waiting submissions can be assigned.');
  end if;
  if submission_row.assigned_reviewer_id is not null then
    return public.review_error('REVIEW_ALREADY_ASSIGNED', 'Another reviewer already owns this submission.');
  end if;

  update public.review_submissions s set
    assigned_reviewer_id = actor_id,
    lock_version = s.lock_version + 1
  where s.id = submission_row.id
  returning * into submission_row;

  insert into public.audit_logs (
    actor_user_id, actor_role, action, target_type, target_id, request_id,
    reason_code, before_state, after_state, policy_version, result
  ) values (
    actor_id, actor_role, 'review.assign_to_self', 'review_submission', submission_row.id::text,
    gen_random_uuid()::text, 'review_assignment',
    jsonb_build_object('assigned_reviewer_id', null, 'lock_version', expected_lock_version),
    jsonb_build_object('assigned_reviewer_id', actor_id, 'lock_version', submission_row.lock_version),
    submission_row.policy_version, 'success'
  );

  return jsonb_build_object('submission', jsonb_build_object(
    'id', submission_row.id,
    'status', submission_row.status,
    'assigned_reviewer_id', actor_id,
    'lock_version', submission_row.lock_version
  ));
end;
$$;

create or replace function public.review_start_submission(
  submission_id uuid,
  expected_lock_version integer
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  actor_id uuid;
  actor_role public.role_code;
  submission_row public.review_submissions%rowtype;
  image_row public.images%rowtype;
  before_state_snapshot jsonb;
  after_state_snapshot jsonb;
begin
  actor_id := public.review_require_actor();
  actor_role := public.review_actor_role(actor_id);
  if expected_lock_version is null or expected_lock_version < 1 then
    return public.review_error('REVIEW_VERSION_REQUIRED', 'Reload the submission before starting review.');
  end if;

  select * into submission_row from public.review_submissions s
  where s.id = submission_id for update;
  if submission_row.id is null then
    return public.review_error('REVIEW_SUBMISSION_NOT_FOUND', 'The review submission is unavailable.');
  end if;
  if submission_row.submitted_by_user_id = actor_id then
    return public.review_error('REVIEW_SELF_REVIEW_FORBIDDEN', 'A submission cannot be reviewed by its owner.');
  end if;
  if submission_row.status = 'in_review'::public.submission_status
     and submission_row.assigned_reviewer_id = actor_id then
    return jsonb_build_object('submission', jsonb_build_object(
      'id', submission_row.id, 'status', submission_row.status,
      'assigned_reviewer_id', actor_id, 'lock_version', submission_row.lock_version,
      'review_started_at', submission_row.review_started_at
    ));
  end if;
  if submission_row.lock_version <> expected_lock_version then
    return public.review_error('REVIEW_VERSION_CONFLICT', 'This submission changed. Reload before starting review.');
  end if;
  if submission_row.status <> 'submitted'::public.submission_status then
    return public.review_error('REVIEW_STATE_CONFLICT', 'This submission is not waiting for review.');
  end if;
  if submission_row.assigned_reviewer_id is not null
     and submission_row.assigned_reviewer_id <> actor_id then
    return public.review_error('REVIEW_ALREADY_ASSIGNED', 'Another reviewer already owns this submission.');
  end if;

  select * into image_row from public.images i
  where i.id = submission_row.image_id for update;
  if image_row.workflow_status <> 'submitted'::public.workflow_status then
    return public.review_error('REVIEW_STATE_CONFLICT', 'The image workflow no longer matches this submission.');
  end if;

  before_state_snapshot := jsonb_build_object(
    'submission_status', submission_row.status,
    'assigned_reviewer_id', submission_row.assigned_reviewer_id,
    'review_started_at', submission_row.review_started_at,
    'submission_lock_version', submission_row.lock_version,
    'workflow_status', image_row.workflow_status,
    'image_lock_version', image_row.version,
    'image_updated_at', image_row.updated_at
  );

  update public.review_submissions s set
    status = 'in_review'::public.submission_status,
    assigned_reviewer_id = actor_id,
    review_started_at = coalesce(s.review_started_at, now()),
    lock_version = s.lock_version + 1
  where s.id = submission_row.id returning * into submission_row;

  update public.images i set
    workflow_status = 'in_review'::public.workflow_status,
    version = i.version + 1,
    updated_at = now()
  where i.id = image_row.id returning * into image_row;

  after_state_snapshot := jsonb_build_object(
    'submission_status', submission_row.status,
    'assigned_reviewer_id', submission_row.assigned_reviewer_id,
    'review_started_at', submission_row.review_started_at,
    'submission_lock_version', submission_row.lock_version,
    'workflow_status', image_row.workflow_status,
    'image_lock_version', image_row.version,
    'image_updated_at', image_row.updated_at
  );

  insert into public.notifications (recipient_user_id, type, payload)
  values (submission_row.submitted_by_user_id, 'image_review_started', jsonb_build_object(
    'image_id', image_row.id,
    'submission_id', submission_row.id,
    'status', submission_row.status
  ));

  insert into public.audit_logs (
    actor_user_id, actor_role, action, target_type, target_id, request_id,
    reason_code, before_state, after_state, policy_version, result
  ) values (
    actor_id, actor_role, 'review.start', 'review_submission', submission_row.id::text,
    gen_random_uuid()::text, 'review_started',
    before_state_snapshot,
    after_state_snapshot,
    submission_row.policy_version, 'success'
  );

  return jsonb_build_object('submission', jsonb_build_object(
    'id', submission_row.id, 'status', submission_row.status,
    'assigned_reviewer_id', actor_id, 'lock_version', submission_row.lock_version,
    'review_started_at', submission_row.review_started_at
  ));
end;
$$;

create or replace function public.review_decide_submission(
  submission_id uuid,
  expected_lock_version integer,
  decision text,
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
  decision_code alias for $3;
  submitted_reason_codes alias for $4;
  submitted_user_message alias for $5;
  submitted_internal_note alias for $6;
  submitted_checklist alias for $7;
  request_key alias for $8;
  actor_id uuid;
  actor_role public.role_code;
  submission_row public.review_submissions%rowtype;
  image_row public.images%rowtype;
  version_row public.image_versions%rowtype;
  next_version_id uuid;
  existing_decision public.review_decisions%rowtype;
  decision_row public.review_decisions%rowtype;
  decision_id uuid;
  decision_created_at timestamptz;
  decision_completed_at timestamptz;
  decision_published_at timestamptz;
  decision_result_snapshot jsonb;
  next_status public.submission_status;
  next_workflow public.workflow_status;
  notification_type text;
  active_asset_count integer;
  active_asset_kind_count integer;
  all_active_assets_clean boolean;
  violated_constraint text;
  before_state_snapshot jsonb;
  after_state_snapshot jsonb;
  before_asset_visibility jsonb;
  after_asset_visibility jsonb;
  allowed_reason_codes text[];
  decision_policy constant text := 'mt-review-2026-07-v1';
  checklist_codes constant text[] := array[
    'file_integrity', 'rights', 'privacy', 'minors', 'sensitive_content',
    'hate_illegal', 'property_release', 'third_party_ip', 'ai_disclosure', 'public_metadata'
  ];
begin
  actor_id := public.review_require_actor();
  actor_role := public.review_actor_role(actor_id);
  submitted_user_message := btrim(coalesce(submitted_user_message, ''));
  submitted_internal_note := nullif(btrim(coalesce(submitted_internal_note, '')), '');

  if request_key is null then
    return public.review_error('REVIEW_IDEMPOTENCY_REQUIRED', 'Start a new review decision request.');
  end if;

  -- A completed request key is replayed before validating the current policy.
  -- Idempotency compares only caller-supplied request data, so a later policy
  -- revision cannot invalidate a previously committed response.
  select * into existing_decision from public.review_decisions d
  where d.idempotency_key = request_key::text;
  if existing_decision.id is not null then
    if existing_decision.submission_id is distinct from target_submission_id
       or existing_decision.reviewer_id is distinct from actor_id
       or existing_decision.decision::text is distinct from decision_code
       or existing_decision.reason_codes is distinct from submitted_reason_codes
       or existing_decision.user_message is distinct from submitted_user_message
       or existing_decision.internal_note is distinct from submitted_internal_note
       or existing_decision.checklist_result is distinct from submitted_checklist then
      return public.review_error('REVIEW_IDEMPOTENCY_CONFLICT', 'This decision key was already used with different review data.');
    end if;
    return public.review_decision_result(existing_decision.id);
  end if;

  if target_expected_lock_version is null or target_expected_lock_version < 1 then
    return public.review_error('REVIEW_VERSION_REQUIRED', 'Reload the submission before deciding it.');
  end if;
  if decision_code is null
     or decision_code not in ('request_changes', 'reject', 'approve', 'approve_and_publish') then
    return public.review_error('REVIEW_DECISION_INVALID', 'Choose a supported review decision.');
  end if;
  allowed_reason_codes := case decision_code
    when 'request_changes' then array[
      'missing_rights', 'missing_metadata', 'privacy_review', 'release_required'
    ]::text[]
    when 'reject' then array[
      'content_policy', 'rights_unverified', 'privacy_risk', 'misleading_metadata'
    ]::text[]
    else array['policy_complete']::text[]
  end;
  if submitted_reason_codes is null
     or jsonb_typeof(submitted_reason_codes) is distinct from 'array' then
    return public.review_error('REVIEW_DECISION_INVALID', 'Choose valid review reason codes.');
  end if;
  if jsonb_array_length(submitted_reason_codes) not between 1 and 8 then
    return public.review_error('REVIEW_DECISION_INVALID', 'Choose valid review reason codes.');
  end if;
  if exists (
       select 1 from jsonb_array_elements(submitted_reason_codes) entry
       where jsonb_typeof(entry) <> 'string'
         or length(btrim(entry #>> '{}')) not between 2 and 80
         or btrim(entry #>> '{}') !~ '^[a-z][a-z0-9_]*$'
         or entry #>> '{}' is distinct from btrim(entry #>> '{}')
         or btrim(entry #>> '{}') <> all(allowed_reason_codes)
     ) then
    return public.review_error('REVIEW_DECISION_INVALID', 'Choose valid review reason codes.');
  end if;
  if (
    select count(*) <> count(distinct btrim(entry #>> '{}'))
    from jsonb_array_elements(submitted_reason_codes) entry
  ) then
    return public.review_error('REVIEW_DECISION_INVALID', 'Choose distinct review reason codes.');
  end if;
  if length(submitted_user_message) not between 5 and 1000 or coalesce(length(submitted_internal_note), 0) > 2000 then
    return public.review_error('REVIEW_DECISION_INVALID', 'Provide a concise user message and optional internal note.');
  end if;
  if submitted_checklist is null
     or jsonb_typeof(submitted_checklist) is distinct from 'object' then
    return public.review_error('REVIEW_CHECKLIST_INCOMPLETE', 'Complete every policy checklist item before deciding.');
  end if;
  if not (submitted_checklist ?& checklist_codes)
     or (select count(*) from jsonb_object_keys(submitted_checklist)) <> cardinality(checklist_codes) then
    return public.review_error('REVIEW_CHECKLIST_INCOMPLETE', 'Complete every policy checklist item before deciding.');
  end if;
  if exists (
       select 1 from jsonb_each(submitted_checklist) item
       where item.key <> all(checklist_codes) or item.value <> 'true'::jsonb
     ) then
    return public.review_error('REVIEW_CHECKLIST_INCOMPLETE', 'Complete every policy checklist item before deciding.');
  end if;
  if decision_code = 'approve_and_publish'
     and actor_role not in ('admin'::public.role_code, 'super_admin'::public.role_code) then
    return public.review_error('REVIEW_PUBLISH_ADMIN_REQUIRED', 'Administrator approval is required to publish.');
  end if;

  select * into submission_row from public.review_submissions s
  where s.id = target_submission_id for update;
  if submission_row.id is null then
    return public.review_error('REVIEW_SUBMISSION_NOT_FOUND', 'The review submission is unavailable.');
  end if;

  -- A concurrent request with the same key can commit while this transaction
  -- waits for the submission lock. Recheck before applying the CAS.
  select * into existing_decision from public.review_decisions d
  where d.idempotency_key = request_key::text;
  if existing_decision.id is not null then
    if existing_decision.submission_id is distinct from target_submission_id
       or existing_decision.reviewer_id is distinct from actor_id
       or existing_decision.decision::text is distinct from decision_code
       or existing_decision.reason_codes is distinct from submitted_reason_codes
       or existing_decision.user_message is distinct from submitted_user_message
       or existing_decision.internal_note is distinct from submitted_internal_note
       or existing_decision.checklist_result is distinct from submitted_checklist then
      return public.review_error('REVIEW_IDEMPOTENCY_CONFLICT', 'This decision key was already used with different review data.');
    end if;
    return public.review_decision_result(existing_decision.id);
  end if;
  if submission_row.submitted_by_user_id = actor_id then
    return public.review_error('REVIEW_SELF_REVIEW_FORBIDDEN', 'A submission cannot be reviewed by its owner.');
  end if;
  if submission_row.lock_version <> target_expected_lock_version then
    return public.review_error('REVIEW_VERSION_CONFLICT', 'This submission changed. Reload before deciding it.');
  end if;

  if submission_row.status = 'approved'::public.submission_status
     and decision_code = 'approve_and_publish'
     and actor_role in ('admin'::public.role_code, 'super_admin'::public.role_code) then
    next_status := 'approved'::public.submission_status;
    next_workflow := 'approved'::public.workflow_status;
  elsif submission_row.status <> 'in_review'::public.submission_status then
    return public.review_error('REVIEW_STATE_CONFLICT', 'This submission is not open for a review decision.');
  elsif submission_row.assigned_reviewer_id is distinct from actor_id then
    return public.review_error('REVIEW_ASSIGNMENT_REQUIRED', 'Only the assigned reviewer can decide this submission.');
  else
    next_status := case decision_code
      when 'request_changes' then 'changes_requested'::public.submission_status
      when 'reject' then 'rejected'::public.submission_status
      else 'approved'::public.submission_status
    end;
    next_workflow := case decision_code
      when 'request_changes' then 'changes_requested'::public.workflow_status
      when 'reject' then 'rejected'::public.workflow_status
      else 'approved'::public.workflow_status
    end;
  end if;

  select * into image_row from public.images i
  where i.id = submission_row.image_id for update;
  select * into version_row from public.image_versions v
  where v.id = submission_row.image_version_id for share;
  if image_row.id is null or version_row.id is null then
    return public.review_error('REVIEW_STATE_CONFLICT', 'The submitted image version is unavailable.');
  end if;

  if image_row.deleted_at is not null
     or image_row.processing_status <> 'ready'::public.processing_status
     or image_row.current_version_id is distinct from submission_row.image_version_id
     or version_row.image_id is distinct from image_row.id
     or version_row.locked_at is null
     or submission_row.readiness_snapshot -> 'ready' is distinct from 'true'::jsonb then
    return public.review_error('REVIEW_STATE_CONFLICT', 'The submitted image is no longer ready for this decision.');
  end if;
  if submission_row.status = 'in_review'::public.submission_status
     and image_row.workflow_status <> 'in_review'::public.workflow_status then
    return public.review_error('REVIEW_STATE_CONFLICT', 'The image workflow no longer matches this review.');
  end if;
  if submission_row.status = 'approved'::public.submission_status
     and image_row.workflow_status <> 'approved'::public.workflow_status then
    return public.review_error('REVIEW_STATE_CONFLICT', 'The approved image workflow is inconsistent.');
  end if;
  if decision_code = 'approve_and_publish'
     and image_row.publication_status = 'published'::public.publication_status then
    return public.review_error('REVIEW_ALREADY_PUBLISHED', 'This work is already published.');
  end if;

  if decision_code in ('approve', 'approve_and_publish') then
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
      return public.review_error('REVIEW_ASSETS_NOT_READY', 'All three current image assets must pass security scanning.');
    end if;
  end if;

  select coalesce(
    jsonb_object_agg(a.kind, a.storage_visibility order by a.kind),
    '{}'::jsonb
  )
  into before_asset_visibility
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
    'asset_storage_visibility', before_asset_visibility
  );

  decision_id := gen_random_uuid();
  decision_created_at := now();
  decision_completed_at := coalesce(submission_row.completed_at, now());
  decision_published_at := case when decision_code = 'approve_and_publish'
    then coalesce(image_row.published_at, now()) else image_row.published_at end;
  if decision_code = 'request_changes' then
    next_version_id := gen_random_uuid();
  end if;
  decision_result_snapshot := jsonb_build_object(
    'decision', jsonb_build_object(
      'id', decision_id,
      'decision', decision_code,
      'created_at', decision_created_at
    ),
    'submission', jsonb_build_object(
      'id', submission_row.id,
      'status', next_status,
      'lock_version', submission_row.lock_version + 1,
      'completed_at', decision_completed_at
    ),
    'image', jsonb_build_object(
      'id', image_row.id,
      'workflow_status', next_workflow,
      'publication_status', case when decision_code = 'approve_and_publish'
        then 'published'::public.publication_status else image_row.publication_status end,
      'current_version_id', coalesce(next_version_id, image_row.current_version_id),
      'published_at', decision_published_at
    )
  );

  begin
    insert into public.review_decisions (
      id,
      submission_id, reviewer_id, decision, reason_codes, user_message,
      internal_note, checklist_result, policy_version, idempotency_key,
      expected_lock_version, result_snapshot, created_at
    ) values (
      decision_id,
      submission_row.id, actor_id, decision_code::public.review_decision, submitted_reason_codes,
      submitted_user_message, submitted_internal_note, submitted_checklist, decision_policy, request_key::text,
      target_expected_lock_version, decision_result_snapshot, decision_created_at
    ) returning * into decision_row;
  exception when unique_violation then
    get stacked diagnostics violated_constraint = constraint_name;
    if violated_constraint is distinct from 'review_decisions_idempotency_key_key' then
      raise;
    end if;
    select * into existing_decision from public.review_decisions d
    where d.idempotency_key = request_key::text;
    if existing_decision.id is not null
       and existing_decision.submission_id is not distinct from target_submission_id
       and existing_decision.reviewer_id is not distinct from actor_id
       and existing_decision.decision::text is not distinct from decision_code
       and existing_decision.reason_codes is not distinct from submitted_reason_codes
       and existing_decision.user_message is not distinct from submitted_user_message
       and existing_decision.internal_note is not distinct from submitted_internal_note
       and existing_decision.checklist_result is not distinct from submitted_checklist then
      return public.review_decision_result(existing_decision.id);
    end if;
    return public.review_error('REVIEW_IDEMPOTENCY_CONFLICT', 'This decision key conflicts with another action.');
  end;

  if decision_code = 'request_changes' then
    insert into public.image_versions (
      id,
      image_id, version_number, title, caption, description, alt_text, tags,
      content_category, captured_at, location_name, gps_visibility, public_exif,
      copyright_holder, copyright_year, contains_recognizable_people,
      model_release_status, property_release_status, rights_declared,
      ai_disclosure, sensitive_content_disclosure, created_by_user_id, locked_at
    ) values (
      next_version_id,
      image_row.id,
      (select coalesce(max(v.version_number), 0) + 1 from public.image_versions v where v.image_id = image_row.id),
      version_row.title, version_row.caption, version_row.description, version_row.alt_text, version_row.tags,
      version_row.content_category, version_row.captured_at, version_row.location_name,
      version_row.gps_visibility, version_row.public_exif, version_row.copyright_holder,
      version_row.copyright_year, version_row.contains_recognizable_people,
      version_row.model_release_status, version_row.property_release_status,
      version_row.rights_declared, version_row.ai_disclosure,
      version_row.sensitive_content_disclosure, image_row.owner_user_id, null
    );
  end if;

  update public.review_submissions s set
    status = next_status,
    completed_at = decision_completed_at,
    lock_version = s.lock_version + 1
  where s.id = submission_row.id returning * into submission_row;

  update public.images i set
    current_version_id = case when next_version_id is not null then next_version_id else i.current_version_id end,
    workflow_status = next_workflow,
    publication_status = case when decision_code = 'approve_and_publish'
      then 'published'::public.publication_status else i.publication_status end,
    published_at = decision_published_at,
    unpublished_at = case when decision_code = 'approve_and_publish' then null else i.unpublished_at end,
    version = i.version + 1,
    updated_at = now()
  where i.id = image_row.id returning * into image_row;

  if decision_code = 'approve_and_publish' then
    update public.image_assets a set storage_visibility = 'public'
    where a.image_id = image_row.id and a.kind in ('display', 'thumbnail') and a.deleted_at is null;
  end if;

  select coalesce(
    jsonb_object_agg(a.kind, a.storage_visibility order by a.kind),
    '{}'::jsonb
  )
  into after_asset_visibility
  from public.image_assets a
  where a.image_id = image_row.id
    and a.kind in ('display', 'thumbnail')
    and a.deleted_at is null;

  notification_type := case decision_code
    when 'request_changes' then 'image_changes_requested'
    when 'reject' then 'image_rejected'
    when 'approve' then 'image_approved'
    else 'image_published'
  end;
  insert into public.notifications (recipient_user_id, type, payload)
  values (submission_row.submitted_by_user_id, notification_type, jsonb_build_object(
    'image_id', image_row.id,
    'submission_id', submission_row.id,
    'decision_id', decision_row.id,
    'decision', decision_code,
    'reason_codes', submitted_reason_codes,
    'message', submitted_user_message,
    'publication_status', image_row.publication_status
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
    'decision_id', decision_row.id
  );

  insert into public.audit_logs (
    actor_user_id, actor_role, action, target_type, target_id, request_id,
    reason_code, before_state, after_state, policy_version, result
  ) values (
    actor_id, actor_role, 'review.' || decision_code, 'review_submission', submission_row.id::text,
    request_key::text, submitted_reason_codes ->> 0,
    before_state_snapshot,
    after_state_snapshot,
    decision_policy, 'success'
  );

  return public.review_decision_result(decision_row.id);
end;
$$;

revoke all on function public.review_list_submissions(text, text, integer, integer)
  from public, anon, authenticated, service_role;
revoke all on function public.review_get_submission(uuid)
  from public, anon, authenticated, service_role;
revoke all on function public.review_assign_submission(uuid, integer)
  from public, anon, authenticated, service_role;
revoke all on function public.review_start_submission(uuid, integer)
  from public, anon, authenticated, service_role;
revoke all on function public.review_decide_submission(uuid, integer, text, jsonb, text, text, jsonb, uuid)
  from public, anon, authenticated, service_role;
grant execute on function public.review_list_submissions(text, text, integer, integer) to authenticated;
grant execute on function public.review_get_submission(uuid) to authenticated;
grant execute on function public.review_assign_submission(uuid, integer) to authenticated;
grant execute on function public.review_start_submission(uuid, integer) to authenticated;
grant execute on function public.review_decide_submission(uuid, integer, text, jsonb, text, text, jsonb, uuid) to authenticated;

-- Direct table reads deliberately expose less than the SECURITY DEFINER queue
-- DTO. Reviewers can inspect only their own active, non-self assignments;
-- administrators require AAL2 and may inspect the full history.
drop policy if exists reviewer_submissions_select on public.review_submissions;
create policy reviewer_submissions_select on public.review_submissions
for select to authenticated
using (
  not (select public.is_recovery_auth_session())
  and (
    (
      (select public.has_any_role(array['reviewer']::public.role_code[]))
      and not (select public.has_any_role(array['admin','super_admin']::public.role_code[]))
      and submitted_by_user_id <> (select public.current_app_user_id())
      and assigned_reviewer_id = (select public.current_app_user_id())
      and status in (
        'submitted'::public.submission_status,
        'in_review'::public.submission_status,
        'escalated'::public.submission_status
      )
    )
    or (
      (select public.has_any_role(array['admin','super_admin']::public.role_code[]))
      and (select public.has_aal2())
    )
  )
);

drop policy if exists reviewer_decisions_select on public.review_decisions;
create policy reviewer_decisions_select on public.review_decisions
for select to authenticated
using (
  not (select public.is_recovery_auth_session())
  and (
    (
      reviewer_id = (select public.current_app_user_id())
      and (select public.has_any_role(array['reviewer']::public.role_code[]))
      and not (select public.has_any_role(array['admin','super_admin']::public.role_code[]))
    )
    or (
      (select public.has_any_role(array['admin','super_admin']::public.role_code[]))
      and (select public.has_aal2())
    )
  )
);

-- Reviewers need time-limited access to the three submitted private assets.
-- Admin/Super Admin access remains AAL2-gated even if the account also has the
-- reviewer role, preventing role stacking from bypassing MFA.
drop policy if exists review_assets_select on public.image_assets;
create policy review_assets_select on public.image_assets
for select to authenticated
using (
  not (select public.is_recovery_auth_session())
  and image_assets.deleted_at is null
  and image_assets.scan_status = 'clean'
  and image_assets.scan_policy_version = 'mt-asset-scan-2026-07-v1'
  and (
    (
      (select public.has_any_role(array['admin','super_admin']::public.role_code[]))
      and (select public.has_aal2())
      and exists (
        select 1 from public.review_submissions s
        where s.image_id = image_assets.image_id
      )
    )
    or (
      (select public.has_any_role(array['reviewer']::public.role_code[]))
      and not (select public.has_any_role(array['admin','super_admin']::public.role_code[]))
      and exists (
        select 1 from public.review_submissions s
        where s.image_id = image_assets.image_id
          and s.submitted_by_user_id <> (select public.current_app_user_id())
          and s.assigned_reviewer_id = (select public.current_app_user_id())
          and s.status in (
            'submitted'::public.submission_status,
            'in_review'::public.submission_status,
            'escalated'::public.submission_status
          )
      )
    )
  )
);

-- Storage evaluates this predicate without inheriting the deliberately narrow
-- raw-table RLS policy. It returns only a boolean and never exposes review row
-- data, while preserving unassigned clean thumbnail previews in the queue DTO.
create or replace function public.can_read_review_storage_object(
  target_bucket text,
  target_key text,
  target_owner text
)
returns boolean
language plpgsql
stable
security definer
set search_path = ''
as $$
declare
  actor_id uuid;
  has_reviewer boolean;
  has_privileged_role boolean;
begin
  if public.is_recovery_auth_session() then
    return false;
  end if;
  actor_id := public.current_app_user_id();
  if actor_id is null then
    return false;
  end if;

  has_reviewer := public.has_any_role(array['reviewer']::public.role_code[]);
  has_privileged_role := public.has_any_role(array['admin','super_admin']::public.role_code[]);

  if has_privileged_role then
    if not public.has_aal2() then
      return false;
    end if;
    return exists (
      select 1
      from public.image_assets a
      join public.images i on i.id = a.image_id
      join public.review_submissions s on s.image_id = a.image_id
      where a.storage_key = target_key
        and target_owner = i.owner_user_id::text
        and a.deleted_at is null
        and a.scan_status = 'clean'
        and a.scan_policy_version = 'mt-asset-scan-2026-07-v1'
        and (
          (a.kind = 'original' and target_bucket = 'image-originals')
          or (a.kind = 'display' and target_bucket = 'image-display')
          or (a.kind = 'thumbnail' and target_bucket = 'image-thumbnails')
        )
    );
  end if;

  if not has_reviewer then
    return false;
  end if;
  return exists (
    select 1
    from public.image_assets a
    join public.images i on i.id = a.image_id
    join public.review_submissions s on s.image_id = a.image_id
    where a.storage_key = target_key
      and target_owner = i.owner_user_id::text
      and a.deleted_at is null
      and a.scan_status = 'clean'
      and a.scan_policy_version = 'mt-asset-scan-2026-07-v1'
      and s.submitted_by_user_id <> actor_id
      and (
        (a.kind = 'original' and target_bucket = 'image-originals')
        or (a.kind = 'display' and target_bucket = 'image-display')
        or (a.kind = 'thumbnail' and target_bucket = 'image-thumbnails')
      )
      and (
        (
          a.kind = 'thumbnail'
          and s.status = 'submitted'::public.submission_status
          and s.assigned_reviewer_id is null
        )
        or (
          s.assigned_reviewer_id = actor_id
          and s.status in (
            'submitted'::public.submission_status,
            'in_review'::public.submission_status,
            'escalated'::public.submission_status
          )
        )
      )
  );
end;
$$;

revoke all on function public.can_read_review_storage_object(text, text, text)
  from public, anon, authenticated, service_role;
grant execute on function public.can_read_review_storage_object(text, text, text) to authenticated;

drop policy if exists review_storage_objects_select on storage.objects;
create policy review_storage_objects_select on storage.objects
for select to authenticated
using (
  (select public.can_read_review_storage_object(
    storage.objects.bucket_id,
    storage.objects.name,
    storage.objects.owner_id
  ))
);

commit;
