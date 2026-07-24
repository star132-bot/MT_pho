begin;

-- Phase 4A: administrator all-images read model and publication governance.
-- Every browser caller keeps using its own authenticated token. The RPCs
-- enforce active Admin/Super Admin membership and AAL2 again inside PostgreSQL.

-- Preserve the first publication timestamp after unpublish/takedown. Public
-- delivery still requires published + published_at + no unpublished_at.
alter table public.images drop constraint if exists images_check;
alter table public.images drop constraint if exists images_publication_timestamps_consistent;
alter table public.images
  add constraint images_publication_timestamps_consistent check (
    (
      publication_status = 'published'::public.publication_status
      and published_at is not null
      and unpublished_at is null
    )
    or (
      publication_status = 'never_published'::public.publication_status
      and published_at is null
    )
    or publication_status in (
      'unpublished'::public.publication_status,
      'quarantined'::public.publication_status,
      'archived'::public.publication_status,
      'deleted'::public.publication_status
    )
  );

create table if not exists public.image_governance_actions (
  id uuid primary key default gen_random_uuid(),
  image_id uuid not null references public.images(id) on delete restrict,
  actor_user_id uuid not null references public.users(id) on delete restrict,
  actor_role public.role_code not null,
  action text not null check (action in ('unpublish', 'takedown', 'restore')),
  reason_code text not null check (
    reason_code in (
      'copyright', 'privacy', 'illegal_content', 'policy_violation',
      'security', 'user_request', 'appeal_upheld',
      'investigation_cleared', 'administrative_error', 'other'
    )
  ),
  user_message text not null check (length(user_message) between 5 and 1000),
  internal_note text check (internal_note is null or length(internal_note) <= 2000),
  expected_image_version integer not null check (expected_image_version > 0),
  idempotency_key uuid not null unique,
  takedown_case_id uuid references public.takedown_cases(id) on delete restrict,
  before_state jsonb not null check (jsonb_typeof(before_state) = 'object'),
  result_snapshot jsonb not null check (jsonb_typeof(result_snapshot) = 'object'),
  policy_version text not null,
  created_at timestamptz not null default now()
);

create index if not exists image_governance_actions_image_created_idx
  on public.image_governance_actions (image_id, created_at desc, id);
create index if not exists image_governance_actions_actor_created_idx
  on public.image_governance_actions (actor_user_id, created_at desc, id);

drop trigger if exists image_governance_actions_append_only
  on public.image_governance_actions;
create trigger image_governance_actions_append_only
before update or delete on public.image_governance_actions
for each row execute function public.reject_mutation();

alter table public.image_governance_actions enable row level security;
revoke all on public.image_governance_actions
  from public, anon, authenticated, service_role;
revoke insert, update, delete, truncate on public.takedown_cases
  from public, anon, authenticated, service_role;

create or replace function public.admin_governance_error(code text, message text)
returns jsonb
language sql
immutable
set search_path = ''
as $$
  select jsonb_build_object(
    'error', jsonb_build_object('code', $1, 'message', $2)
  )
$$;

create or replace function public.admin_governance_failure_result(
  failure_actor_id uuid,
  failure_actor_role public.role_code,
  failure_image_id uuid,
  submitted_action text,
  submitted_reason text,
  failure_expected_version integer,
  failure_request_key uuid,
  failure_error_code text,
  failure_error_message text
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  current_image_version integer;
  safe_action text;
  safe_reason text;
  safe_expected_version integer;
  policy constant text := 'mt-admin-governance-2026-07-v1';
begin
  if failure_error_code not in (
    'ADMIN_GOVERNANCE_VALIDATION_FAILED',
    'ADMIN_GOVERNANCE_IDEMPOTENCY_CONFLICT',
    'ADMIN_IMAGE_NOT_FOUND',
    'ADMIN_IMAGE_VERSION_CONFLICT',
    'ADMIN_GOVERNANCE_STATE_CONFLICT',
    'ADMIN_GOVERNANCE_RESTORE_BLOCKED'
  ) then
    raise exception 'unsupported governance failure code' using errcode = '22023';
  end if;

  -- A missing target stays indistinguishable from every other unavailable ID
  -- and does not create an attacker-controlled audit target.
  select image.version into current_image_version
  from public.images image
  where image.id = failure_image_id;
  if not found then
    return public.admin_governance_error(
      failure_error_code,
      failure_error_message
    );
  end if;

  -- This helper is private, but repeat the actor boundary before writing an
  -- append-only security record so re-use cannot weaken the calling RPC.
  if public.is_recovery_auth_session()
     or not public.has_aal2()
     or not exists (
       select 1
       from public.users actor
       join public.user_roles actor_role on actor_role.user_id = actor.id
       where actor.id = failure_actor_id
         and actor.id = public.current_app_user_id()
         and actor.account_status = 'active'::public.account_status
         and actor_role.role = failure_actor_role
         and actor_role.role in (
           'admin'::public.role_code,
           'super_admin'::public.role_code
         )
     ) then
    return public.admin_governance_error(
      failure_error_code,
      failure_error_message
    );
  end if;

  safe_action := case lower(btrim(coalesce(submitted_action, '')))
    when 'unpublish' then 'unpublish'
    when 'takedown' then 'takedown'
    when 'restore' then 'restore'
    else null
  end;
  safe_reason := case
    when safe_action = 'restore'
      and lower(btrim(coalesce(submitted_reason, ''))) in (
        'appeal_upheld', 'investigation_cleared',
        'administrative_error', 'other'
      ) then lower(btrim(submitted_reason))
    when safe_action in ('unpublish', 'takedown')
      and lower(btrim(coalesce(submitted_reason, ''))) in (
        'copyright', 'privacy', 'illegal_content', 'policy_violation',
        'security', 'user_request', 'other'
      ) then lower(btrim(submitted_reason))
    else null
  end;
  safe_expected_version := case
    when failure_expected_version > 0 then failure_expected_version
    else null
  end;

  insert into public.audit_logs (
    actor_user_id, actor_role, action, target_type, target_id, request_id,
    reason_code, before_state, after_state, policy_version, result
  ) values (
    failure_actor_id,
    failure_actor_role,
    'admin.image.governance_failed',
    'image',
    failure_image_id::text,
    coalesce(
      failure_request_key::text,
      'generated:' || gen_random_uuid()::text
    ),
    safe_reason,
    null,
    jsonb_build_object(
      'image_id', failure_image_id,
      'action', safe_action,
      'reason_code', safe_reason,
      'error_code', failure_error_code,
      'expected_version', safe_expected_version,
      'current_version', current_image_version,
      'policy_version', policy
    ),
    policy,
    'failure'
  );

  return public.admin_governance_error(
    failure_error_code,
    failure_error_message
  );
end;
$$;

create or replace function public.admin_require_governance_actor()
returns uuid
language plpgsql
stable
security definer
set search_path = ''
as $$
declare
  actor_id uuid;
begin
  if public.is_recovery_auth_session() then
    raise exception 'recovery session cannot access image governance'
      using errcode = '42501';
  end if;
  select public.current_app_user_id() into actor_id;
  if actor_id is null or not exists (
    select 1
    from public.users u
    where u.id = actor_id
      and u.account_status = 'active'::public.account_status
  ) then
    raise exception 'active administrator account required'
      using errcode = '42501';
  end if;
  if not exists (
    select 1
    from public.user_roles ur
    where ur.user_id = actor_id
      and ur.role in (
        'admin'::public.role_code,
        'super_admin'::public.role_code
      )
  ) then
    raise exception 'administrator role required' using errcode = '42501';
  end if;
  if not (select public.has_aal2()) then
    raise exception 'aal2 required for image governance' using errcode = '42501';
  end if;
  return actor_id;
end;
$$;

create or replace function public.admin_governance_actor_role(actor_id uuid)
returns public.role_code
language sql
stable
security definer
set search_path = ''
as $$
  select case
    when exists (
      select 1 from public.user_roles ur
      where ur.user_id = $1
        and ur.role = 'super_admin'::public.role_code
    ) then 'super_admin'::public.role_code
    else 'admin'::public.role_code
  end
$$;

-- Admin Works signs only derivative previews. Keep this Storage predicate
-- independent from review_submissions so governance can inspect any work,
-- while binding every allowed row back to its immutable clean scan verdict.
create or replace function public.can_read_admin_work_storage_object(
  target_object_id uuid,
  target_bucket text,
  target_key text,
  target_owner text
)
returns boolean
language sql
stable
security definer
set search_path = ''
as $$
  select
    not public.is_recovery_auth_session()
    and public.has_aal2()
    and exists (
      select 1
      from public.users actor
      join public.user_roles actor_role on actor_role.user_id = actor.id
      where actor.id = public.current_app_user_id()
        and actor.account_status = 'active'::public.account_status
        and actor_role.role in (
          'admin'::public.role_code,
          'super_admin'::public.role_code
        )
    )
    and exists (
      select 1
      from storage.objects storage_object
      join public.asset_scan_jobs scan_job
        on scan_job.expected_storage_object_id = storage_object.id
      join public.image_assets asset on asset.id = scan_job.asset_id
      join public.images image
        on image.id = asset.image_id
       and image.owner_user_id = asset.owner_user_id
      where storage_object.id = target_object_id
        and storage_object.bucket_id = target_bucket
        and storage_object.name = target_key
        and storage_object.owner_id = target_owner
        and asset.owner_user_id::text = target_owner
        and asset.storage_key = target_key
        and asset.deleted_at is null
        and asset.kind in ('display', 'thumbnail')
        and target_bucket = case asset.kind
          when 'display' then 'image-display'
          else 'image-thumbnails'
        end
        and asset.storage_key ~* (
          '^' || asset.owner_user_id::text || '/' || asset.image_id::text || '/'
          || asset.kind::text || '\.(jpg|jpeg|png|webp)$'
        )
        and asset.scan_status = 'clean'
        and asset.scan_result_code = 'clean'
        and asset.scan_completed_at is not null
        and asset.scan_policy_version = 'mt-asset-scan-2026-07-v1'
        and scan_job.status = 'clean'
        and scan_job.result_code = 'clean'
        and scan_job.completed_at is not null
        and scan_job.scan_policy_version = 'mt-asset-scan-2026-07-v1'
        and scan_job.storage_bucket = target_bucket
        and scan_job.storage_key = target_key
        and scan_job.mime_type = asset.mime_type
        and scan_job.byte_size = asset.byte_size
        and scan_job.width = asset.width
        and scan_job.height = asset.height
        and asset.checksum_sha256 is not null
        and scan_job.checksum_sha256 = asset.checksum_sha256
    )
$$;

drop policy if exists admin_work_storage_objects_select on storage.objects;
create policy admin_work_storage_objects_select on storage.objects
for select to authenticated
using (
  (select public.can_read_admin_work_storage_object(
    storage.objects.id,
    storage.objects.bucket_id,
    storage.objects.name,
    storage.objects.owner_id
  ))
);

-- Admin-only review access is derivative-only. An assigned Reviewer retains
-- the existing time-scoped original permission; role-stacked administrators
-- must still satisfy AAL2 before that assignment path can be evaluated.
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
  if actor_id is null or not exists (
    select 1
    from public.users actor
    where actor.id = actor_id
      and actor.account_status = 'active'::public.account_status
  ) then
    return false;
  end if;

  has_reviewer := public.has_any_role(array['reviewer']::public.role_code[]);
  has_privileged_role := public.has_any_role(
    array['admin','super_admin']::public.role_code[]
  );

  if has_privileged_role then
    if not public.has_aal2() then
      return false;
    end if;
    if exists (
      select 1
      from public.image_assets asset
      join public.images image
        on image.id = asset.image_id
       and image.owner_user_id = asset.owner_user_id
      join public.review_submissions submission
        on submission.image_id = asset.image_id
      where asset.storage_key = target_key
        and target_owner = image.owner_user_id::text
        and asset.deleted_at is null
        and asset.scan_status = 'clean'
        and asset.scan_result_code = 'clean'
        and asset.scan_completed_at is not null
        and asset.scan_policy_version = 'mt-asset-scan-2026-07-v1'
        and (
          (asset.kind = 'display' and target_bucket = 'image-display')
          or (
            asset.kind = 'thumbnail'
            and target_bucket = 'image-thumbnails'
          )
        )
    ) then
      return true;
    end if;
  end if;

  if not has_reviewer then
    return false;
  end if;
  return exists (
    select 1
    from public.image_assets asset
    join public.images image
      on image.id = asset.image_id
     and image.owner_user_id = asset.owner_user_id
    join public.review_submissions submission
      on submission.image_id = asset.image_id
    where asset.storage_key = target_key
      and target_owner = image.owner_user_id::text
      and asset.deleted_at is null
      and asset.scan_status = 'clean'
      and asset.scan_result_code = 'clean'
      and asset.scan_completed_at is not null
      and asset.scan_policy_version = 'mt-asset-scan-2026-07-v1'
      and submission.submitted_by_user_id <> actor_id
      and (
        (asset.kind = 'original' and target_bucket = 'image-originals')
        or (asset.kind = 'display' and target_bucket = 'image-display')
        or (
          asset.kind = 'thumbnail'
          and target_bucket = 'image-thumbnails'
        )
      )
      and (
        (
          asset.kind = 'thumbnail'
          and submission.status = 'submitted'::public.submission_status
          and submission.assigned_reviewer_id is null
        )
        or (
          submission.assigned_reviewer_id = actor_id
          and submission.status in (
            'submitted'::public.submission_status,
            'in_review'::public.submission_status,
            'escalated'::public.submission_status
          )
        )
      )
  );
end;
$$;

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

create or replace function public.admin_image_asset_json(target_asset_id uuid)
returns jsonb
language sql
stable
security definer
set search_path = ''
as $$
  select jsonb_build_object(
    'id', a.id,
    'image_id', a.image_id,
    'owner_user_id', a.owner_user_id,
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
    'scan_completed_at', a.scan_completed_at,
    'scan_policy_version', a.scan_policy_version,
    'storage_visibility', a.storage_visibility,
    'deleted_at', a.deleted_at,
    'created_at', a.created_at
  )
  from public.image_assets a
  where a.id = $1
  limit 1
$$;

create or replace function public.admin_image_summary_json(target_image_id uuid)
returns jsonb
language sql
stable
security definer
set search_path = ''
as $$
  select jsonb_build_object(
    'id', i.id,
    'title', coalesce(nullif(v.title, ''), i.original_filename),
    'original_filename', i.original_filename,
    'owner', jsonb_build_object(
      'id', owner_user.id,
      'email', owner_user.email,
      'display_name', coalesce(owner_profile.display_name, 'Member'),
      'account_status', owner_user.account_status
    ),
    'processing_status', i.processing_status,
    'workflow_status', i.workflow_status,
    'publication_status', i.publication_status,
    'version', i.version,
    'original_width', i.original_width,
    'original_height', i.original_height,
    'created_at', i.created_at,
    'updated_at', i.updated_at,
    'published_at', i.published_at,
    'unpublished_at', i.unpublished_at,
    'deleted_at', i.deleted_at,
    'thumbnail_asset', public.admin_image_asset_json(thumbnail.id),
    'asset_summary', jsonb_build_object(
      'count', asset_counts.asset_count,
      'clean_count', asset_counts.clean_count,
      'flagged_count', asset_counts.flagged_count,
      'failed_count', asset_counts.failed_count,
      'pending_count', asset_counts.pending_count
    ),
    'latest_review', case when latest_submission.id is null then null else jsonb_build_object(
      'image_id', latest_submission.image_id,
      'submission_id', latest_submission.id,
      'image_version_id', latest_submission.image_version_id,
      'status', latest_submission.status,
      'assigned_reviewer_id', latest_submission.assigned_reviewer_id,
      'submitted_at', latest_submission.submitted_at,
      'completed_at', latest_submission.completed_at,
      'decision', latest_decision.decision,
      'decision_at', latest_decision.created_at
    ) end,
    'latest_governance_action', case when latest_action.id is null then null else jsonb_build_object(
      'id', latest_action.id,
      'image_id', latest_action.image_id,
      'action', latest_action.action,
      'reason_code', latest_action.reason_code,
      'actor_user_id', latest_action.actor_user_id,
      'actor_role', latest_action.actor_role,
      'policy_version', latest_action.policy_version,
      'created_at', latest_action.created_at
    ) end
  )
  from public.images i
  join public.users owner_user on owner_user.id = i.owner_user_id
  left join public.user_profiles owner_profile on owner_profile.user_id = i.owner_user_id
  left join public.image_versions v
    on v.id = i.current_version_id and v.image_id = i.id
  left join lateral (
    select a.*
    from public.image_assets a
    where a.image_id = i.id
      and a.kind = 'thumbnail'
      and a.deleted_at is null
    order by a.created_at desc, a.id
    limit 1
  ) thumbnail on true
  cross join lateral (
    select
      count(*)::integer as asset_count,
      count(*) filter (where a.scan_status = 'clean')::integer as clean_count,
      count(*) filter (where a.scan_status = 'flagged')::integer as flagged_count,
      count(*) filter (where a.scan_status = 'failed')::integer as failed_count,
      count(*) filter (where a.scan_status = 'pending')::integer as pending_count
    from public.image_assets a
    where a.image_id = i.id and a.deleted_at is null
  ) asset_counts
  left join lateral (
    select s.*
    from public.review_submissions s
    where s.image_id = i.id
    order by s.submitted_at desc, s.id
    limit 1
  ) latest_submission on true
  left join lateral (
    select d.*
    from public.review_decisions d
    where d.submission_id = latest_submission.id
    order by d.created_at desc, d.id
    limit 1
  ) latest_decision on true
  left join lateral (
    select action_row.*
    from public.image_governance_actions action_row
    where action_row.image_id = i.id
    order by action_row.created_at desc, action_row.id
    limit 1
  ) latest_action on true
  where i.id = $1
  limit 1
$$;

create or replace function public.admin_list_images(
  status_filter text default 'all',
  search_query text default '',
  sort_code text default 'updated_desc',
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
  actor_roles jsonb;
  normalized_status text := lower(btrim(coalesce(status_filter, 'all')));
  normalized_search text := lower(btrim(coalesce(search_query, '')));
  normalized_sort text := lower(btrim(coalesce(sort_code, 'updated_desc')));
  total_count integer;
  image_items jsonb;
  status_counts jsonb;
begin
  actor_id := public.admin_require_governance_actor();
  if normalized_status not in (
       'all', 'never_published', 'published', 'unpublished',
       'quarantined', 'archived', 'deleted'
     )
     or length(normalized_search) > 200
     or normalized_sort not in (
       'updated_desc', 'uploaded_desc', 'published_desc', 'title_asc'
     )
     or page_size is null or page_size not between 1 and 50
     or page_offset is null or page_offset not between 0 and 10000 then
    return public.admin_governance_error(
      'ADMIN_FILTER_INVALID',
      'Choose supported image filters, sorting, and pagination values.'
    );
  end if;

  select coalesce(jsonb_agg(ur.role order by ur.role), '[]'::jsonb)
  into actor_roles
  from public.user_roles ur
  where ur.user_id = actor_id;

  select count(*)::integer
  into total_count
  from public.images i
  join public.users owner_user on owner_user.id = i.owner_user_id
  left join public.user_profiles owner_profile on owner_profile.user_id = i.owner_user_id
  left join public.image_versions v
    on v.id = i.current_version_id and v.image_id = i.id
  where (
      normalized_search = ''
      or position(normalized_search in lower(i.id::text)) > 0
      or position(normalized_search in lower(coalesce(v.title, ''))) > 0
      or position(normalized_search in lower(i.original_filename)) > 0
      or position(normalized_search in lower(owner_user.email)) > 0
      or position(normalized_search in lower(coalesce(owner_profile.display_name, ''))) > 0
      or position(normalized_search in lower(coalesce(i.checksum_sha256::text, ''))) > 0
    )
    and (normalized_status = 'all' or i.publication_status::text = normalized_status);

  select jsonb_build_object(
    'all', count(*),
    'never_published', count(*) filter (
      where i.publication_status = 'never_published'::public.publication_status
    ),
    'published', count(*) filter (
      where i.publication_status = 'published'::public.publication_status
    ),
    'unpublished', count(*) filter (
      where i.publication_status = 'unpublished'::public.publication_status
    ),
    'quarantined', count(*) filter (
      where i.publication_status = 'quarantined'::public.publication_status
    ),
    'archived', count(*) filter (
      where i.publication_status = 'archived'::public.publication_status
    ),
    'deleted', count(*) filter (
      where i.publication_status = 'deleted'::public.publication_status
    )
  )
  into status_counts
  from public.images i
  join public.users owner_user on owner_user.id = i.owner_user_id
  left join public.user_profiles owner_profile on owner_profile.user_id = i.owner_user_id
  left join public.image_versions v
    on v.id = i.current_version_id and v.image_id = i.id
  where normalized_search = ''
    or position(normalized_search in lower(i.id::text)) > 0
    or position(normalized_search in lower(coalesce(v.title, ''))) > 0
    or position(normalized_search in lower(i.original_filename)) > 0
    or position(normalized_search in lower(owner_user.email)) > 0
    or position(normalized_search in lower(coalesce(owner_profile.display_name, ''))) > 0
    or position(normalized_search in lower(coalesce(i.checksum_sha256::text, ''))) > 0;

  select coalesce(
    jsonb_agg(
      public.admin_image_summary_json(page.id)
      order by
        case when normalized_sort = 'updated_desc' then page.updated_at end desc nulls last,
        case when normalized_sort = 'uploaded_desc' then page.created_at end desc nulls last,
        case when normalized_sort = 'published_desc' then page.published_at end desc nulls last,
        case when normalized_sort = 'title_asc' then lower(page.title) end asc nulls last,
        page.id
    ),
    '[]'::jsonb
  )
  into image_items
  from (
    select
      i.id,
      i.updated_at,
      i.created_at,
      i.published_at,
      coalesce(v.title, i.original_filename) as title
    from public.images i
    join public.users owner_user on owner_user.id = i.owner_user_id
    left join public.user_profiles owner_profile on owner_profile.user_id = i.owner_user_id
    left join public.image_versions v
      on v.id = i.current_version_id and v.image_id = i.id
    where (
        normalized_search = ''
        or position(normalized_search in lower(i.id::text)) > 0
        or position(normalized_search in lower(coalesce(v.title, ''))) > 0
        or position(normalized_search in lower(i.original_filename)) > 0
        or position(normalized_search in lower(owner_user.email)) > 0
        or position(normalized_search in lower(coalesce(owner_profile.display_name, ''))) > 0
        or position(normalized_search in lower(coalesce(i.checksum_sha256::text, ''))) > 0
      )
      and (normalized_status = 'all' or i.publication_status::text = normalized_status)
    order by
      case when normalized_sort = 'updated_desc' then i.updated_at end desc nulls last,
      case when normalized_sort = 'uploaded_desc' then i.created_at end desc nulls last,
      case when normalized_sort = 'published_desc' then i.published_at end desc nulls last,
      case when normalized_sort = 'title_asc' then lower(coalesce(v.title, i.original_filename)) end asc nulls last,
      i.id
    limit page_size
    offset page_offset
  ) page;

  return jsonb_build_object(
    'actor', jsonb_build_object(
      'id', actor_id,
      'roles', actor_roles,
      'can_govern_images', true
    ),
    'items', image_items,
    'counts', status_counts,
    'pagination', jsonb_build_object(
      'offset', page_offset,
      'limit', page_size,
      'total', total_count,
      'has_more', page_offset + jsonb_array_length(image_items) < total_count
    )
  );
end;
$$;

create or replace function public.admin_get_image(target_image_id uuid)
returns jsonb
language plpgsql
stable
security definer
set search_path = ''
as $$
declare
  actor_id uuid;
  actor_roles jsonb;
  image_summary jsonb;
  image_detail jsonb;
begin
  actor_id := public.admin_require_governance_actor();
  image_summary := public.admin_image_summary_json(target_image_id);
  if image_summary is null then
    return public.admin_governance_error(
      'ADMIN_IMAGE_NOT_FOUND',
      'The image is unavailable.'
    );
  end if;

  select coalesce(jsonb_agg(ur.role order by ur.role), '[]'::jsonb)
  into actor_roles
  from public.user_roles ur
  where ur.user_id = actor_id;

  select image_summary || jsonb_build_object(
    'current_version', case when v.id is null then null else jsonb_build_object(
      'id', v.id,
      'image_id', v.image_id,
      'version_number', v.version_number,
      'title', v.title,
      'caption', v.caption,
      'description', v.description,
      'alt_text', v.alt_text,
      'tags', v.tags,
      'content_category', v.content_category,
      'captured_at', v.captured_at,
      'location_name', v.location_name,
      'gps_visibility', v.gps_visibility,
      'public_exif', v.public_exif,
      'copyright_holder', v.copyright_holder,
      'copyright_year', v.copyright_year,
      'contains_recognizable_people', v.contains_recognizable_people,
      'model_release_status', v.model_release_status,
      'property_release_status', v.property_release_status,
      'rights_declared', v.rights_declared,
      'ai_disclosure', v.ai_disclosure,
      'sensitive_content_disclosure', v.sensitive_content_disclosure,
      'locked_at', v.locked_at,
      'created_at', v.created_at
    ) end,
    'display_asset', public.admin_image_asset_json((
      select a.id from public.image_assets a
      where a.image_id = i.id and a.kind = 'display' and a.deleted_at is null
      order by a.created_at desc, a.id limit 1
    )),
    'thumbnail_asset', public.admin_image_asset_json((
      select a.id from public.image_assets a
      where a.image_id = i.id and a.kind = 'thumbnail' and a.deleted_at is null
      order by a.created_at desc, a.id limit 1
    )),
    'versions', coalesce((
      select jsonb_agg(jsonb_build_object(
        'id', history.id,
        'image_id', history.image_id,
        'version_number', history.version_number,
        'title', history.title,
        'created_by_user_id', history.created_by_user_id,
        'created_at', history.created_at,
        'locked_at', history.locked_at
      ) order by history.version_number desc, history.id)
      from (
        select version_row.*
        from public.image_versions version_row
        where version_row.image_id = i.id
        order by version_row.version_number desc, version_row.id
        limit 50
      ) history
    ), '[]'::jsonb),
    'review_submissions', coalesce((
      select jsonb_agg(jsonb_build_object(
        'id', s.id,
        'image_id', s.image_id,
        'image_version_id', s.image_version_id,
        'image_version_image_id', s.image_version_image_id,
        'status', s.status,
        'assigned_reviewer_id', s.assigned_reviewer_id,
        'policy_version', s.policy_version,
        'lock_version', s.lock_version,
        'submitted_at', s.submitted_at,
        'review_started_at', s.review_started_at,
        'completed_at', s.completed_at,
        'decisions', coalesce((
          select jsonb_agg(jsonb_build_object(
            'id', d.id,
            'submission_id', d.submission_id,
            'reviewer_id', d.reviewer_id,
            'decision', d.decision,
            'reason_codes', d.reason_codes,
            'user_message', d.user_message,
            'policy_version', d.policy_version,
            'created_at', d.created_at
          ) order by d.created_at, d.id)
          from (
            select decision_row.*
            from public.review_decisions decision_row
            where decision_row.submission_id = s.id
            order by decision_row.created_at desc, decision_row.id
            limit 20
          ) d
        ), '[]'::jsonb)
      ) order by s.submitted_at desc, s.id)
      from (
        select
          submission_row.*,
          submitted_version.image_id as image_version_image_id
        from public.review_submissions submission_row
        left join public.image_versions submitted_version
          on submitted_version.id = submission_row.image_version_id
        where submission_row.image_id = i.id
        order by submission_row.submitted_at desc, submission_row.id
        limit 50
      ) s
    ), '[]'::jsonb),
    'governance_actions', coalesce((
      select jsonb_agg(jsonb_build_object(
        'id', action_row.id,
        'image_id', action_row.image_id,
        'actor_user_id', action_row.actor_user_id,
        'actor_role', action_row.actor_role,
        'action', action_row.action,
        'reason_code', action_row.reason_code,
        'user_message', action_row.user_message,
        'expected_image_version', action_row.expected_image_version,
        'takedown_case_id', action_row.takedown_case_id,
        'policy_version', action_row.policy_version,
        'created_at', action_row.created_at
      ) order by action_row.created_at desc, action_row.id)
      from (
        select governance_row.*
        from public.image_governance_actions governance_row
        where governance_row.image_id = i.id
        order by governance_row.created_at desc, governance_row.id
        limit 100
      ) action_row
    ), '[]'::jsonb),
    'takedowns', coalesce((
      select jsonb_agg(jsonb_build_object(
        'id', case_row.id,
        'image_id', case_row.image_id,
        'requester_user_id', case_row.requester_user_id,
        'reason_code', case_row.reason_code,
        'evidence_reference', case_row.evidence_reference,
        'status', case_row.status,
        'assigned_admin_id', case_row.assigned_admin_id,
        'legal_hold', case_row.legal_hold,
        'created_at', case_row.created_at,
        'resolved_at', case_row.resolved_at
      ) order by case_row.created_at desc, case_row.id)
      from (
        select takedown_row.*
        from public.takedown_cases takedown_row
        where takedown_row.image_id = i.id
        order by takedown_row.created_at desc, takedown_row.id
        limit 100
      ) case_row
    ), '[]'::jsonb),
    'audit_timeline', coalesce((
      select jsonb_agg(jsonb_build_object(
        'id', log_row.id,
        'target_type', log_row.target_type,
        'target_id', log_row.target_id,
        'actor_user_id', log_row.actor_user_id,
        'actor_role', log_row.actor_role,
        'action', log_row.action,
        'request_id', log_row.request_id,
        'reason_code', log_row.reason_code,
        'policy_version', log_row.policy_version,
        'result', log_row.result,
        'created_at', log_row.created_at
      ) order by log_row.created_at desc, log_row.id)
      from (
        select audit_row.*
        from public.audit_logs audit_row
        where audit_row.target_type = 'image'
          and audit_row.target_id = i.id::text
          and audit_row.actor_role in (
            'admin'::public.role_code,
            'super_admin'::public.role_code
          )
        order by audit_row.created_at desc, audit_row.id
        limit 100
      ) log_row
    ), '[]'::jsonb)
  )
  into image_detail
  from public.images i
  left join public.image_versions v
    on v.id = i.current_version_id and v.image_id = i.id
  where i.id = target_image_id;

  return jsonb_build_object(
    'actor', jsonb_build_object(
      'id', actor_id,
      'roles', actor_roles,
      'can_govern_images', true
    ),
    'work', image_detail
  );
end;
$$;

create or replace function public.admin_governance_action_result(
  target_action_id uuid,
  replayed boolean
)
returns jsonb
language sql
stable
security definer
set search_path = ''
as $$
  select action_row.result_snapshot || jsonb_build_object('replayed', $2)
  from public.image_governance_actions action_row
  where action_row.id = $1
$$;

create or replace function public.admin_govern_image(
  target_image_id uuid,
  target_expected_version integer,
  action_code text,
  submitted_reason_code text,
  submitted_user_message text,
  submitted_internal_note text,
  idempotency_key uuid
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  actor_id uuid;
  actor_role public.role_code;
  normalized_action text := lower(btrim(coalesce(action_code, '')));
  normalized_reason text := lower(btrim(coalesce(submitted_reason_code, '')));
  normalized_user_message text := btrim(coalesce(submitted_user_message, ''));
  normalized_internal_note text := nullif(btrim(coalesce(submitted_internal_note, '')), '');
  request_key alias for $7;
  image_row public.images%rowtype;
  owner_status public.account_status;
  current_version_locked_at timestamptz;
  existing_action public.image_governance_actions%rowtype;
  action_id uuid := gen_random_uuid();
  action_created_at timestamptz := now();
  case_id uuid;
  next_publication_status public.publication_status;
  asset_count integer;
  asset_kind_count integer;
  assets_restorable boolean;
  before_asset_visibility jsonb;
  after_asset_visibility jsonb;
  before_state_snapshot jsonb;
  after_state_snapshot jsonb;
  actor_snapshot jsonb;
  work_snapshot jsonb;
  takedown_snapshot jsonb;
  result_snapshot jsonb;
  allowed_reasons text[];
  notification_type text;
  policy constant text := 'mt-admin-governance-2026-07-v1';
begin
  actor_id := public.admin_require_governance_actor();
  actor_role := public.admin_governance_actor_role(actor_id);

  if request_key is null then
    return public.admin_governance_failure_result(
      actor_id, actor_role, target_image_id, normalized_action,
      normalized_reason, target_expected_version, request_key,
      'ADMIN_GOVERNANCE_VALIDATION_FAILED',
      'Start a new image governance request.'
    );
  end if;

  -- A request UUID serializes retries even when two requests target different
  -- images. Replays return the immutable first result before current-state CAS.
  perform pg_catalog.pg_advisory_xact_lock(
    pg_catalog.hashtextextended(request_key::text, 0)
  );
  select * into existing_action
  from public.image_governance_actions action_row
  where action_row.idempotency_key = request_key;
  if existing_action.id is not null then
    if existing_action.image_id is distinct from target_image_id
       or existing_action.actor_user_id is distinct from actor_id
       or existing_action.action is distinct from normalized_action
       or existing_action.reason_code is distinct from normalized_reason
       or existing_action.user_message is distinct from normalized_user_message
       or existing_action.internal_note is distinct from normalized_internal_note
       or existing_action.expected_image_version is distinct from target_expected_version then
      return public.admin_governance_failure_result(
        actor_id, actor_role, target_image_id, normalized_action,
        normalized_reason, target_expected_version, request_key,
        'ADMIN_GOVERNANCE_IDEMPOTENCY_CONFLICT',
        'This request key was already used with different governance data.'
      );
    end if;
    return public.admin_governance_action_result(existing_action.id, true);
  end if;

  if target_expected_version is null or target_expected_version < 1
     or normalized_action not in ('unpublish', 'takedown', 'restore')
     or length(normalized_user_message) not between 5 and 1000
     or coalesce(length(normalized_internal_note), 0) > 2000 then
    return public.admin_governance_failure_result(
      actor_id, actor_role, target_image_id, normalized_action,
      normalized_reason, target_expected_version, request_key,
      'ADMIN_GOVERNANCE_VALIDATION_FAILED',
      'Provide a current version, supported action, reason, and user-safe message.'
    );
  end if;
  allowed_reasons := case normalized_action
    when 'restore' then array[
      'appeal_upheld', 'investigation_cleared', 'administrative_error', 'other'
    ]::text[]
    else array[
      'copyright', 'privacy', 'illegal_content', 'policy_violation',
      'security', 'user_request', 'other'
    ]::text[]
  end;
  if normalized_reason <> all(allowed_reasons) then
    return public.admin_governance_failure_result(
      actor_id, actor_role, target_image_id, normalized_action,
      normalized_reason, target_expected_version, request_key,
      'ADMIN_GOVERNANCE_VALIDATION_FAILED',
      'Choose a supported reason for this governance action.'
    );
  end if;

  select * into image_row
  from public.images i
  where i.id = target_image_id
  for update;
  if image_row.id is null then
    return public.admin_governance_failure_result(
      actor_id, actor_role, target_image_id, normalized_action,
      normalized_reason, target_expected_version, request_key,
      'ADMIN_IMAGE_NOT_FOUND',
      'The image is unavailable.'
    );
  end if;
  if image_row.version <> target_expected_version then
    return public.admin_governance_failure_result(
      actor_id, actor_role, target_image_id, normalized_action,
      normalized_reason, target_expected_version, request_key,
      'ADMIN_IMAGE_VERSION_CONFLICT',
      'This image changed. Reload before applying governance.'
    );
  end if;

  select u.account_status into owner_status
  from public.users u
  where u.id = image_row.owner_user_id;
  select v.locked_at into current_version_locked_at
  from public.image_versions v
  where v.id = image_row.current_version_id and v.image_id = image_row.id;

  if normalized_action = 'unpublish' then
    if image_row.publication_status <> 'published'::public.publication_status then
      return public.admin_governance_failure_result(
        actor_id, actor_role, target_image_id, normalized_action,
        normalized_reason, target_expected_version, request_key,
        'ADMIN_GOVERNANCE_STATE_CONFLICT',
        'Only a published image can be unpublished.'
      );
    end if;
    next_publication_status := 'unpublished'::public.publication_status;
  elsif normalized_action = 'takedown' then
    if image_row.publication_status not in (
      'published'::public.publication_status,
      'unpublished'::public.publication_status
    ) then
      return public.admin_governance_failure_result(
        actor_id, actor_role, target_image_id, normalized_action,
        normalized_reason, target_expected_version, request_key,
        'ADMIN_GOVERNANCE_STATE_CONFLICT',
        'Only a published or unpublished image can be taken down.'
      );
    end if;
    next_publication_status := 'quarantined'::public.publication_status;
  else
    if image_row.publication_status not in (
      'unpublished'::public.publication_status,
      'quarantined'::public.publication_status
    ) then
      return public.admin_governance_failure_result(
        actor_id, actor_role, target_image_id, normalized_action,
        normalized_reason, target_expected_version, request_key,
        'ADMIN_GOVERNANCE_STATE_CONFLICT',
        'Only an unpublished or quarantined image can be restored.'
      );
    end if;
    if exists (
      select 1
      from public.takedown_cases case_row
      where case_row.image_id = image_row.id
        and case_row.legal_hold
        and case_row.status in ('open', 'investigating', 'unpublished')
    ) then
      return public.admin_governance_failure_result(
        actor_id, actor_role, target_image_id, normalized_action,
        normalized_reason, target_expected_version, request_key,
        'ADMIN_GOVERNANCE_RESTORE_BLOCKED',
        'This image is under legal hold and cannot be restored.'
      );
    end if;
    if image_row.deleted_at is not null
       or image_row.processing_status <> 'ready'::public.processing_status
       or image_row.workflow_status <> 'approved'::public.workflow_status
       or image_row.current_version_id is null
       or current_version_locked_at is null
       or owner_status <> 'active'::public.account_status then
      return public.admin_governance_failure_result(
        actor_id, actor_role, target_image_id, normalized_action,
        normalized_reason, target_expected_version, request_key,
        'ADMIN_GOVERNANCE_RESTORE_BLOCKED',
        'The image, current version, or owner is not eligible for restoration.'
      );
    end if;

    select
      count(*)::integer,
      count(distinct a.kind)::integer,
      coalesce(bool_and(
        scan_job.id is not null
        and storage_object.id is not null
        and a.scan_status = 'clean'
        and a.scan_result_code = 'clean'
        and a.scan_completed_at is not null
        and a.scan_policy_version = 'mt-asset-scan-2026-07-v1'
        and scan_job.status = 'clean'
        and scan_job.result_code = 'clean'
        and scan_job.completed_at is not null
        and scan_job.scan_policy_version = 'mt-asset-scan-2026-07-v1'
        and scan_job.storage_bucket = case a.kind
          when 'original' then 'image-originals'
          when 'display' then 'image-display'
          else 'image-thumbnails'
        end
        and scan_job.storage_key = a.storage_key
        and scan_job.mime_type = a.mime_type
        and scan_job.byte_size = a.byte_size
        and scan_job.width = a.width
        and scan_job.height = a.height
        and a.checksum_sha256 is not null
        and scan_job.checksum_sha256 = a.checksum_sha256
        and storage_object.id = scan_job.expected_storage_object_id
        and storage_object.bucket_id = scan_job.storage_bucket
        and storage_object.name = scan_job.storage_key
        and storage_object.owner_id = image_row.owner_user_id::text
      ), false)
    into asset_count, asset_kind_count, assets_restorable
    from public.image_assets a
    left join public.asset_scan_jobs scan_job on scan_job.asset_id = a.id
    left join storage.objects storage_object
      on storage_object.id = scan_job.expected_storage_object_id
    where a.image_id = image_row.id
      and a.deleted_at is null
      and a.kind in ('original', 'display', 'thumbnail');
    if asset_count <> 3 or asset_kind_count <> 3 or not assets_restorable then
      return public.admin_governance_failure_result(
        actor_id, actor_role, target_image_id, normalized_action,
        normalized_reason, target_expected_version, request_key,
        'ADMIN_GOVERNANCE_RESTORE_BLOCKED',
        'All current image assets must pass the active security policy before restoration.'
      );
    end if;
    next_publication_status := 'published'::public.publication_status;
  end if;

  select coalesce(
    jsonb_object_agg(a.kind, a.storage_visibility order by a.kind),
    '{}'::jsonb
  )
  into before_asset_visibility
  from public.image_assets a
  where a.image_id = image_row.id
    and a.deleted_at is null;

  before_state_snapshot := jsonb_build_object(
    'image_id', image_row.id,
    'owner_user_id', image_row.owner_user_id,
    'workflow_status', image_row.workflow_status,
    'processing_status', image_row.processing_status,
    'publication_status', image_row.publication_status,
    'published_at', image_row.published_at,
    'unpublished_at', image_row.unpublished_at,
    'image_version', image_row.version,
    'current_version_id', image_row.current_version_id,
    'asset_storage_visibility', before_asset_visibility
  );

  if normalized_action in ('unpublish', 'takedown') then
    insert into public.takedown_cases (
      image_id, requester_user_id, reason_code, evidence_reference, status,
      assigned_admin_id, legal_hold, resolved_at
    ) values (
      image_row.id,
      actor_id,
      normalized_reason,
      case when normalized_internal_note is null then null
        else 'internal-note:' || action_id::text end,
      case when normalized_action = 'unpublish' then 'unpublished' else 'open' end,
      actor_id,
      false,
      case when normalized_action = 'unpublish' then action_created_at else null end
    ) returning id into case_id;
  else
    select case_row.id into case_id
    from public.takedown_cases case_row
    where case_row.image_id = image_row.id
      and case_row.status in ('open', 'investigating', 'unpublished')
    order by case_row.created_at desc, case_row.id
    limit 1;
    update public.takedown_cases case_row set
      status = 'restored',
      assigned_admin_id = actor_id,
      resolved_at = action_created_at
    where case_row.image_id = image_row.id
      and case_row.status in ('open', 'investigating', 'unpublished')
      and not case_row.legal_hold;
  end if;

  update public.images i set
    publication_status = next_publication_status,
    published_at = case when normalized_action = 'restore'
      then coalesce(i.published_at, action_created_at)
      else i.published_at
    end,
    unpublished_at = case when normalized_action = 'restore'
      then null
      else action_created_at
    end,
    version = i.version + 1,
    updated_at = action_created_at
  where i.id = image_row.id
  returning * into image_row;

  -- Original is never public. Only a restored work's clean display derivatives
  -- are eligible for the existing published-only Storage policy.
  update public.image_assets a set
    storage_visibility = case
      when normalized_action = 'restore' and a.kind in ('display', 'thumbnail')
        then 'public'
      else 'private'
    end
  where a.image_id = image_row.id
    and a.deleted_at is null;

  select coalesce(
    jsonb_object_agg(a.kind, a.storage_visibility order by a.kind),
    '{}'::jsonb
  )
  into after_asset_visibility
  from public.image_assets a
  where a.image_id = image_row.id
    and a.deleted_at is null;

  after_state_snapshot := jsonb_build_object(
    'image_id', image_row.id,
    'owner_user_id', image_row.owner_user_id,
    'workflow_status', image_row.workflow_status,
    'processing_status', image_row.processing_status,
    'publication_status', image_row.publication_status,
    'published_at', image_row.published_at,
    'unpublished_at', image_row.unpublished_at,
    'image_version', image_row.version,
    'current_version_id', image_row.current_version_id,
    'asset_storage_visibility', after_asset_visibility
  );

  actor_snapshot := jsonb_build_object(
    'id', actor_id,
    'roles', coalesce((
      select jsonb_agg(ur.role order by ur.role)
      from public.user_roles ur
      where ur.user_id = actor_id
    ), '[]'::jsonb),
    'can_govern_images', true
  );
  work_snapshot := public.admin_image_summary_json(image_row.id)
    || jsonb_build_object('latest_governance_action', jsonb_build_object(
      'id', action_id,
      'image_id', image_row.id,
      'action', normalized_action,
      'reason_code', normalized_reason,
      'actor_user_id', actor_id,
      'actor_role', actor_role,
      'policy_version', policy,
      'created_at', action_created_at
    ));
  select jsonb_build_object(
    'id', case_row.id,
    'image_id', case_row.image_id,
    'reason_code', case_row.reason_code,
    'status', case_row.status,
    'assigned_admin_id', case_row.assigned_admin_id,
    'legal_hold', case_row.legal_hold,
    'created_at', case_row.created_at,
    'resolved_at', case_row.resolved_at
  )
  into takedown_snapshot
  from public.takedown_cases case_row
  where case_row.id = case_id;
  result_snapshot := jsonb_build_object(
    'actor', actor_snapshot,
    'action', jsonb_build_object(
      'id', action_id,
      'image_id', image_row.id,
      'action', normalized_action,
      'reason_code', normalized_reason,
      'user_message', normalized_user_message,
      'actor_user_id', actor_id,
      'actor_role', actor_role,
      'expected_image_version', target_expected_version,
      'policy_version', policy,
      'created_at', action_created_at,
      'takedown_case_id', case_id
    ),
    'work', work_snapshot,
    'takedown', takedown_snapshot
  );

  insert into public.image_governance_actions (
    id, image_id, actor_user_id, actor_role, action, reason_code,
    user_message, internal_note, expected_image_version, idempotency_key,
    takedown_case_id, before_state, result_snapshot, policy_version, created_at
  ) values (
    action_id, image_row.id, actor_id, actor_role, normalized_action,
    normalized_reason, normalized_user_message, normalized_internal_note,
    target_expected_version, request_key, case_id, before_state_snapshot,
    result_snapshot, policy, action_created_at
  );

  notification_type := case normalized_action
    when 'unpublish' then 'image_unpublished_by_admin'
    when 'takedown' then 'image_taken_down'
    else 'image_restored_by_admin'
  end;
  insert into public.notifications (recipient_user_id, type, payload)
  values (image_row.owner_user_id, notification_type, jsonb_build_object(
    'image_id', image_row.id,
    'governance_action_id', action_id,
    'takedown_case_id', case_id,
    'action', normalized_action,
    'reason_code', normalized_reason,
    'message', normalized_user_message,
    'publication_status', image_row.publication_status
  ));

  insert into public.audit_logs (
    actor_user_id, actor_role, action, target_type, target_id, request_id,
    reason_code, before_state, after_state, policy_version, result
  ) values (
    actor_id,
    actor_role,
    'admin.image_' || normalized_action,
    'image',
    image_row.id::text,
    request_key::text,
    normalized_reason,
    before_state_snapshot,
    after_state_snapshot || jsonb_build_object(
      'governance_action_id', action_id,
      'takedown_case_id', case_id
    ),
    policy,
    'success'
  );

  return public.admin_governance_action_result(action_id, false);
end;
$$;

revoke all on function public.admin_governance_error(text, text)
  from public, anon, authenticated, service_role;
revoke all on function public.admin_governance_failure_result(uuid,
  public.role_code, uuid, text, text, integer, uuid, text, text)
  from public, anon, authenticated, service_role;
revoke all on function public.admin_require_governance_actor()
  from public, anon, authenticated, service_role;
revoke all on function public.admin_governance_actor_role(uuid)
  from public, anon, authenticated, service_role;
revoke all on function public.can_read_admin_work_storage_object(uuid, text, text, text)
  from public, anon, authenticated, service_role;
revoke all on function public.can_read_review_storage_object(text, text, text)
  from public, anon, authenticated, service_role;
revoke all on function public.admin_image_asset_json(uuid)
  from public, anon, authenticated, service_role;
revoke all on function public.admin_image_summary_json(uuid)
  from public, anon, authenticated, service_role;
revoke all on function public.admin_governance_action_result(uuid, boolean)
  from public, anon, authenticated, service_role;
revoke all on function public.admin_list_images(text, text, text, integer, integer)
  from public, anon, authenticated, service_role;
revoke all on function public.admin_get_image(uuid)
  from public, anon, authenticated, service_role;
revoke all on function public.admin_govern_image(uuid, integer, text, text, text, text, uuid)
  from public, anon, authenticated, service_role;

grant execute on function public.admin_list_images(text, text, text, integer, integer)
  to authenticated;
grant execute on function public.admin_get_image(uuid)
  to authenticated;
grant execute on function public.admin_govern_image(uuid, integer, text, text, text, text, uuid)
  to authenticated;
grant execute on function public.can_read_admin_work_storage_object(uuid, text, text, text)
  to authenticated;
grant execute on function public.can_read_review_storage_object(text, text, text)
  to authenticated;

commit;
