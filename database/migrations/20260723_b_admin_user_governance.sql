begin;

-- Phase 4B: administrator user read model and account/role governance.
-- Supabase Auth remains authoritative for sessions and MFA. These RPCs expose
-- an explicit unavailable/provider-action-required capability instead of
-- inferring provider state from application roles.

alter table public.users
  add column if not exists version integer not null default 1,
  add column if not exists is_system_identity boolean not null default false;

insert into public.user_roles (user_id, role, assigned_by, reason)
select target.id, 'user'::public.role_code, null,
       'Baseline user role backfilled by Phase 4B migration'
from public.users target
where not exists (
  select 1 from public.user_roles role_row
  where role_row.user_id = target.id
    and role_row.role = 'user'::public.role_code
)
on conflict (user_id, role) do nothing;

do $$
begin
  if not exists (
    select 1 from pg_constraint
    where conrelid = 'public.users'::regclass
      and conname = 'users_version_positive'
  ) then
    alter table public.users
      add constraint users_version_positive check (version > 0);
  end if;
end
$$;

create or replace function public.bump_user_version()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
  new.version := old.version + 1;
  return new;
end;
$$;

drop trigger if exists users_version_bump on public.users;
create trigger users_version_bump
before update on public.users
for each row execute function public.bump_user_version();

create index if not exists users_admin_status_updated_idx
  on public.users (account_status, updated_at desc, id);

create table if not exists public.user_governance_actions (
  id uuid primary key default gen_random_uuid(),
  target_user_id uuid not null references public.users(id) on delete restrict,
  actor_user_id uuid not null references public.users(id) on delete restrict,
  actor_role public.role_code not null,
  action text not null check (
    action in ('suspend', 'reactivate', 'grant_role', 'revoke_role', 'revoke_sessions')
  ),
  target_role public.role_code,
  reason_code text not null check (
    reason_code in (
      'security_review', 'policy_violation', 'suspected_compromise',
      'user_request', 'investigation_cleared', 'appeal_upheld',
      'administrative_error', 'operational_need', 'access_review',
      'staffing_change', 'other'
    )
  ),
  expected_user_version integer not null check (expected_user_version > 0),
  idempotency_key uuid not null unique,
  provider_action_required boolean not null default false,
  before_state jsonb not null check (jsonb_typeof(before_state) = 'object'),
  result_snapshot jsonb not null check (jsonb_typeof(result_snapshot) = 'object'),
  policy_version text not null,
  created_at timestamptz not null default now(),
  check (
    (action in ('grant_role', 'revoke_role') and target_role is not null)
    or (action not in ('grant_role', 'revoke_role') and target_role is null)
  ),
  check (provider_action_required = (action = 'revoke_sessions'))
);

create index if not exists user_governance_actions_target_created_idx
  on public.user_governance_actions (target_user_id, created_at desc, id);
create index if not exists user_governance_actions_actor_created_idx
  on public.user_governance_actions (actor_user_id, created_at desc, id);

drop trigger if exists user_governance_actions_append_only
  on public.user_governance_actions;
create trigger user_governance_actions_append_only
before update or delete on public.user_governance_actions
for each row execute function public.reject_mutation();

alter table public.user_governance_actions enable row level security;
revoke all on public.user_governance_actions
  from public, anon, authenticated, service_role;

-- Browser identities never mutate account or role rows through PostgREST.
-- The provider/bootstrap service_role path remains available for controlled
-- provisioning, while application mutations are restricted to the RPC below.
revoke insert, update, delete, truncate on public.users
  from public, anon, authenticated;
revoke insert, update, delete, truncate on public.user_roles
  from public, anon, authenticated;

create or replace function public.admin_user_error(code text, message text)
returns jsonb
language sql
immutable
set search_path = ''
as $$
  select jsonb_build_object(
    'error', jsonb_build_object('code', $1, 'message', $2)
  )
$$;

create or replace function public.admin_require_user_governance_actor()
returns uuid
language plpgsql
stable
security definer
set search_path = ''
as $$
declare
  actor_id uuid;
begin
  actor_id := public.admin_require_governance_actor();
  if exists (
    select 1 from public.users actor
    where actor.id = actor_id and actor.is_system_identity
  ) then
    raise exception 'system identity cannot access user governance'
      using errcode = '42501';
  end if;
  return actor_id;
end;
$$;

create or replace function public.admin_user_actor_json(actor_id uuid)
returns jsonb
language sql
stable
security definer
set search_path = ''
as $$
  select jsonb_build_object(
    'id', $1,
    'roles', coalesce((
      select jsonb_agg(role_row.role order by role_row.role)
      from public.user_roles role_row
      where role_row.user_id = $1
    ), '[]'::jsonb),
    'can_manage_users', true,
    'can_manage_roles', exists (
      select 1 from public.user_roles role_row
      where role_row.user_id = $1
        and role_row.role = 'super_admin'::public.role_code
    )
  )
$$;

create or replace function public.admin_user_summary_json(target_user_id uuid)
returns jsonb
language sql
stable
security definer
set search_path = ''
as $$
  select jsonb_build_object(
    'id', target.id,
    'email', target.email,
    'email_verified_at', target.email_verified_at,
    'account_status', target.account_status,
    'version', target.version,
    'is_system_identity', target.is_system_identity,
    'created_at', target.created_at,
    'updated_at', target.updated_at,
    'last_active_at', target.last_active_at,
    'roles', coalesce((
      select jsonb_agg(role_row.role order by role_row.role)
      from public.user_roles role_row
      where role_row.user_id = target.id
    ), '[]'::jsonb),
    'profile', jsonb_build_object(
      'user_id', target.id,
      'display_name', coalesce(
        profile.display_name, nullif(split_part(target.email, '@', 1), ''), 'Member'
      ),
      'avatar_url', profile.avatar_url,
      'professional_headline', profile.professional_headline,
      'company', profile.company,
      'country_code', profile.country_code,
      'city', profile.city,
      'availability_status', coalesce(
        profile.availability_status,
        'unavailable'::public.creator_availability_status
      )
    ),
    'mfa_status', 'unavailable',
    'sessions', jsonb_build_object(
      'status', 'provider_managed',
      'active_count', null,
      'provider_action_required', true
    ),
    'image_counts', jsonb_build_object(
      'total', coalesce(image_totals.total, 0),
      'draft', coalesce(image_totals.draft, 0),
      'submitted', coalesce(image_totals.submitted, 0),
      'in_review', coalesce(image_totals.in_review, 0),
      'changes_requested', coalesce(image_totals.changes_requested, 0),
      'rejected', coalesce(image_totals.rejected, 0),
      'approved', coalesce(image_totals.approved, 0),
      'published', coalesce(image_totals.published, 0),
      'unpublished', coalesce(image_totals.unpublished, 0),
      'quarantined', coalesce(image_totals.quarantined, 0),
      'processing_failed', coalesce(image_totals.processing_failed, 0)
    ),
    'storage', jsonb_build_object(
      'used_bytes', coalesce(storage_totals.used_bytes, 0),
      'quota_bytes', null,
      'quota_status', 'unavailable'
    ),
    'takedown_case_count', coalesce(case_totals.case_count, 0)
  )
  from public.users target
  left join public.user_profiles profile on profile.user_id = target.id
  left join lateral (
    select
      count(*)::integer as total,
      count(*) filter (
        where image.workflow_status = 'draft'::public.workflow_status
      )::integer as draft,
      count(*) filter (
        where image.workflow_status = 'submitted'::public.workflow_status
      )::integer as submitted,
      count(*) filter (
        where image.workflow_status = 'in_review'::public.workflow_status
      )::integer as in_review,
      count(*) filter (
        where image.workflow_status = 'changes_requested'::public.workflow_status
      )::integer as changes_requested,
      count(*) filter (
        where image.workflow_status = 'rejected'::public.workflow_status
      )::integer as rejected,
      count(*) filter (
        where image.workflow_status = 'approved'::public.workflow_status
      )::integer as approved,
      count(*) filter (
        where image.publication_status = 'published'::public.publication_status
      )::integer as published,
      count(*) filter (
        where image.publication_status = 'unpublished'::public.publication_status
      )::integer as unpublished,
      count(*) filter (
        where image.publication_status = 'quarantined'::public.publication_status
      )::integer as quarantined,
      count(*) filter (
        where image.processing_status = 'failed'::public.processing_status
      )::integer as processing_failed
    from public.images image
    where image.owner_user_id = target.id
      and image.deleted_at is null
  ) image_totals on true
  left join lateral (
    select coalesce(sum(asset.byte_size), 0)::bigint as used_bytes
    from public.image_assets asset
    where asset.owner_user_id = target.id
      and asset.deleted_at is null
  ) storage_totals on true
  left join lateral (
    select count(*)::integer as case_count
    from public.takedown_cases case_row
    join public.images image on image.id = case_row.image_id
    where image.owner_user_id = target.id
  ) case_totals on true
  where target.id = $1
$$;

create or replace function public.admin_list_users(
  status_filter text default 'all',
  role_filter text default 'all',
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
  normalized_status text := lower(btrim(coalesce(status_filter, 'all')));
  normalized_role text := lower(btrim(coalesce(role_filter, 'all')));
  normalized_search text := lower(btrim(coalesce(search_query, '')));
  normalized_sort text := lower(btrim(coalesce(sort_code, 'updated_desc')));
  item_rows jsonb;
  total_count integer;
  status_counts jsonb;
  role_counts jsonb;
begin
  actor_id := public.admin_require_user_governance_actor();

  if normalized_status not in (
    'all', 'pending_verification', 'active', 'suspended', 'banned',
    'deletion_requested', 'deleted'
  ) then
    return public.admin_user_error(
      'ADMIN_USER_FILTER_INVALID', 'Choose a supported account status filter.'
    );
  end if;
  if normalized_role not in ('all', 'user', 'reviewer', 'admin', 'super_admin') then
    return public.admin_user_error(
      'ADMIN_USER_FILTER_INVALID', 'Choose a supported role filter.'
    );
  end if;
  if normalized_sort not in (
    'updated_desc', 'created_desc', 'last_login_desc',
    'email_asc', 'display_name_asc'
  ) then
    return public.admin_user_error(
      'ADMIN_USER_SORT_INVALID', 'Choose a supported user sort.'
    );
  end if;
  if length(normalized_search) > 160 then
    return public.admin_user_error(
      'ADMIN_USER_SEARCH_INVALID', 'Search is limited to 160 characters.'
    );
  end if;
  if page_size is null or page_size not between 1 and 100
     or page_offset is null or page_offset not between 0 and 10000 then
    return public.admin_user_error(
      'ADMIN_USER_PAGE_INVALID', 'Use a page size from 1 to 100 and an offset up to 10000.'
    );
  end if;

  with filtered as (
    select target.id, profile.display_name
    from public.users target
    left join public.user_profiles profile on profile.user_id = target.id
    where (
      normalized_status = 'all'
      or target.account_status::text = normalized_status
    )
      and (
        normalized_role = 'all'
        or exists (
          select 1 from public.user_roles role_row
          where role_row.user_id = target.id
            and role_row.role::text = normalized_role
        )
      )
      and (
        normalized_search = ''
        or position(normalized_search in lower(target.id::text)) > 0
        or position(normalized_search in lower(target.email)) > 0
        or position(normalized_search in lower(coalesce(profile.display_name, ''))) > 0
      )
  ), ranked as (
    select filtered.id, row_number() over (order by
      case when normalized_sort = 'updated_desc' then target.updated_at end desc nulls last,
      case when normalized_sort = 'created_desc' then target.created_at end desc nulls last,
      case when normalized_sort = 'last_login_desc' then target.last_active_at end desc nulls last,
      case when normalized_sort = 'email_asc' then lower(target.email) end asc nulls last,
      case when normalized_sort = 'display_name_asc' then lower(filtered.display_name) end asc nulls last,
      target.id
    ) as sort_position
    from filtered
    join public.users target on target.id = filtered.id
  ), paged as (
    select ranked.id, ranked.sort_position
    from ranked
    order by ranked.sort_position
    limit page_size offset page_offset
  )
  select coalesce(jsonb_agg(
    public.admin_user_summary_json(paged.id) order by paged.sort_position
  ), '[]'::jsonb)
  into item_rows
  from paged;

  select count(*)::integer into total_count
  from public.users target
  left join public.user_profiles profile on profile.user_id = target.id
  where (
    normalized_status = 'all'
    or target.account_status::text = normalized_status
  )
    and (
      normalized_role = 'all'
      or exists (
        select 1 from public.user_roles role_row
        where role_row.user_id = target.id
          and role_row.role::text = normalized_role
      )
    )
    and (
      normalized_search = ''
      or position(normalized_search in lower(target.id::text)) > 0
      or position(normalized_search in lower(target.email)) > 0
      or position(normalized_search in lower(coalesce(profile.display_name, ''))) > 0
    );

  select jsonb_build_object(
    'all', count(*)::integer,
    'pending_verification', count(*) filter (
      where account_status = 'pending_verification'::public.account_status
    )::integer,
    'active', count(*) filter (
      where account_status = 'active'::public.account_status
    )::integer,
    'suspended', count(*) filter (
      where account_status = 'suspended'::public.account_status
    )::integer,
    'banned', count(*) filter (
      where account_status = 'banned'::public.account_status
    )::integer,
    'deletion_requested', count(*) filter (
      where account_status = 'deletion_requested'::public.account_status
    )::integer,
    'deleted', count(*) filter (
      where account_status = 'deleted'::public.account_status
    )::integer
  ) into status_counts
  from public.users;

  select jsonb_build_object(
    'user', count(distinct user_id) filter (
      where role = 'user'::public.role_code
    )::integer,
    'reviewer', count(distinct user_id) filter (
      where role = 'reviewer'::public.role_code
    )::integer,
    'admin', count(distinct user_id) filter (
      where role = 'admin'::public.role_code
    )::integer,
    'super_admin', count(distinct user_id) filter (
      where role = 'super_admin'::public.role_code
    )::integer
  ) into role_counts
  from public.user_roles;

  return jsonb_build_object(
    'actor', public.admin_user_actor_json(actor_id),
    'items', item_rows,
    'counts', jsonb_build_object(
      'statuses', status_counts,
      'roles', role_counts
    ),
    'pagination', jsonb_build_object(
      'limit', page_size,
      'offset', page_offset,
      'total', total_count,
      'has_more', page_offset + page_size < total_count
    )
  );
end;
$$;

create or replace function public.admin_get_user(target_user_id uuid)
returns jsonb
language plpgsql
stable
security definer
set search_path = ''
as $$
declare
  actor_id uuid;
  user_summary jsonb;
  profile_detail jsonb;
  recent_images jsonb;
  governance_actions jsonb;
  audit_timeline jsonb;
begin
  actor_id := public.admin_require_user_governance_actor();
  user_summary := public.admin_user_summary_json(target_user_id);
  if user_summary is null then
    return public.admin_user_error(
      'ADMIN_USER_NOT_FOUND', 'The user is unavailable.'
    );
  end if;

  select jsonb_build_object(
    'user_id', target.id,
    'display_name', coalesce(
      profile.display_name, nullif(split_part(target.email, '@', 1), ''), 'Member'
    ),
    'avatar_url', profile.avatar_url,
    'professional_headline', profile.professional_headline,
    'company', profile.company,
    'availability_status', coalesce(
      profile.availability_status,
      'unavailable'::public.creator_availability_status
    ),
    'bio', profile.bio,
    'website_url', profile.website_url,
    'instagram_url', profile.instagram_url,
    'linkedin_url', profile.linkedin_url,
    'country_code', profile.country_code,
    'city', profile.city,
    'preferred_locale', profile.preferred_locale,
    'timezone', profile.timezone,
    'copyright_name', profile.copyright_name,
    'default_license_preference', profile.default_license_preference
  ) into profile_detail
  from public.users target
  left join public.user_profiles profile on profile.user_id = target.id
  where target.id = target_user_id;

  select coalesce(jsonb_agg(jsonb_build_object(
    'id', image.id,
    'owner_user_id', image.owner_user_id,
    'original_filename', image.original_filename,
    'processing_status', image.processing_status,
    'workflow_status', image.workflow_status,
    'publication_status', image.publication_status,
    'version', image.version,
    'created_at', image.created_at,
    'updated_at', image.updated_at,
    'published_at', image.published_at
  ) order by image.updated_at desc, image.id), '[]'::jsonb)
  into recent_images
  from (
    select image.*
    from public.images image
    where image.owner_user_id = target_user_id
      and image.deleted_at is null
    order by image.updated_at desc, image.id
    limit 12
  ) image;

  select coalesce(jsonb_agg(jsonb_build_object(
    'id', action_row.id,
    'target_user_id', action_row.target_user_id,
    'actor_user_id', action_row.actor_user_id,
    'actor_role', action_row.actor_role,
    'action', action_row.action,
    'target_role', action_row.target_role,
    'reason_code', action_row.reason_code,
    'expected_user_version', action_row.expected_user_version,
    'provider_action_required', action_row.provider_action_required,
    'policy_version', action_row.policy_version,
    'created_at', action_row.created_at
  ) order by action_row.created_at desc, action_row.id), '[]'::jsonb)
  into governance_actions
  from (
    select action_row.*
    from public.user_governance_actions action_row
    where action_row.target_user_id = $1
    order by action_row.created_at desc, action_row.id
    limit 100
  ) action_row;

  select coalesce(jsonb_agg(jsonb_build_object(
    'id', audit.id,
    'target_type', audit.target_type,
    'target_id', audit.target_id,
    'target_user_id', target_user_id,
    'actor_user_id', audit.actor_user_id,
    'actor_role', audit.actor_role,
    'action', audit.action,
    'reason_code', audit.reason_code,
    'result', audit.result,
    'policy_version', audit.policy_version,
    'created_at', audit.created_at
  ) order by audit.created_at desc, audit.id), '[]'::jsonb)
  into audit_timeline
  from (
    select audit.*
    from public.audit_logs audit
    where audit.target_type = 'user'
      and audit.target_id = target_user_id::text
      and audit.action like 'admin.user.%'
    order by audit.created_at desc, audit.id
    limit 100
  ) audit;

  return jsonb_build_object(
    'actor', public.admin_user_actor_json(actor_id),
    'user', user_summary || jsonb_build_object(
      'profile', coalesce(profile_detail, '{}'::jsonb),
      'recent_images', recent_images,
      'governance_actions', governance_actions,
      'audit_timeline', audit_timeline
    )
  );
end;
$$;

create or replace function public.admin_user_action_result(
  action_id uuid,
  replayed boolean default false
)
returns jsonb
language sql
stable
security definer
set search_path = ''
as $$
  select action_row.result_snapshot || jsonb_build_object('replayed', $2)
  from public.user_governance_actions action_row
  where action_row.id = $1
$$;

create or replace function public.admin_user_failure_result(
  failure_actor_id uuid,
  failure_actor_role public.role_code,
  failure_target_user_id uuid,
  submitted_action text,
  submitted_target_role text,
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
  current_user_version integer;
  safe_action text;
  safe_target_role text;
  safe_reason text;
  safe_expected_version integer;
  audit_action text;
  policy constant text := 'mt-admin-user-governance-2026-07-v1';
begin
  if failure_error_code not in (
    'ADMIN_USER_VALIDATION_FAILED', 'ADMIN_USER_IDEMPOTENCY_CONFLICT',
    'ADMIN_USER_NOT_FOUND', 'ADMIN_USER_VERSION_CONFLICT',
    'ADMIN_USER_STATE_CONFLICT', 'ADMIN_USER_SELF_ACTION_FORBIDDEN',
    'ADMIN_USER_SYSTEM_IDENTITY', 'ADMIN_USER_TARGET_FORBIDDEN',
    'ADMIN_USER_ROLE_FORBIDDEN', 'ADMIN_USER_LAST_SUPER_ADMIN'
  ) then
    raise exception 'unsupported user governance failure code' using errcode = '22023';
  end if;

  select target.version into current_user_version
  from public.users target
  where target.id = failure_target_user_id;
  if not found then
    return public.admin_user_error(failure_error_code, failure_error_message);
  end if;

  if public.is_recovery_auth_session()
     or not public.has_aal2()
     or not exists (
       select 1
       from public.users actor
       join public.user_roles actor_role on actor_role.user_id = actor.id
       where actor.id = failure_actor_id
         and actor.id = public.current_app_user_id()
         and actor.account_status = 'active'::public.account_status
         and not actor.is_system_identity
         and actor_role.role = failure_actor_role
         and actor_role.role in (
           'admin'::public.role_code, 'super_admin'::public.role_code
         )
     ) then
    return public.admin_user_error(failure_error_code, failure_error_message);
  end if;

  safe_action := case lower(btrim(coalesce(submitted_action, '')))
    when 'suspend' then 'suspend'
    when 'reactivate' then 'reactivate'
    when 'grant_role' then 'grant_role'
    when 'revoke_role' then 'revoke_role'
    when 'revoke_sessions' then 'revoke_sessions'
    else null
  end;
  safe_target_role := case
    when lower(btrim(coalesce(submitted_target_role, ''))) in (
      'user', 'reviewer', 'admin', 'super_admin'
    ) then lower(btrim(submitted_target_role))
    else null
  end;
  safe_reason := case
    when lower(btrim(coalesce(submitted_reason, ''))) in (
      'security_review', 'policy_violation', 'suspected_compromise',
      'user_request', 'investigation_cleared', 'appeal_upheld',
      'administrative_error', 'operational_need', 'access_review',
      'staffing_change', 'other'
    ) then lower(btrim(submitted_reason))
    else null
  end;
  safe_expected_version := case
    when failure_expected_version > 0 then failure_expected_version
    else null
  end;
  audit_action := case safe_action
    when 'suspend' then 'admin.user.suspend_failed'
    when 'reactivate' then 'admin.user.reactivate_failed'
    when 'grant_role' then 'admin.user.grant_role_failed'
    when 'revoke_role' then 'admin.user.revoke_role_failed'
    when 'revoke_sessions' then 'admin.user.revoke_sessions_request_failed'
    else 'admin.user.governance_failed'
  end;

  insert into public.audit_logs (
    actor_user_id, actor_role, action, target_type, target_id, request_id,
    reason_code, before_state, after_state, policy_version, result
  ) values (
    failure_actor_id,
    failure_actor_role,
    audit_action,
    'user',
    failure_target_user_id::text,
    coalesce(failure_request_key::text, 'generated:' || gen_random_uuid()::text),
    safe_reason,
    null,
    jsonb_build_object(
      'target_user_id', failure_target_user_id,
      'action', safe_action,
      'target_role', safe_target_role,
      'reason_code', safe_reason,
      'error_code', failure_error_code,
      'expected_version', safe_expected_version,
      'current_version', current_user_version,
      'policy_version', policy
    ),
    policy,
    'failure'
  );

  return public.admin_user_error(failure_error_code, failure_error_message);
end;
$$;

create or replace function public.admin_govern_user(
  target_user_id uuid,
  expected_version integer,
  action text,
  target_role text,
  reason_code text,
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
  target public.users%rowtype;
  normalized_action text := lower(btrim(coalesce(action, '')));
  normalized_target_role text := nullif(lower(btrim(coalesce(target_role, ''))), '');
  normalized_reason text := lower(btrim(coalesce(reason_code, '')));
  request_key uuid := idempotency_key;
  existing_action public.user_governance_actions%rowtype;
  action_id uuid := gen_random_uuid();
  action_created_at timestamptz := now();
  policy constant text := 'mt-admin-user-governance-2026-07-v1';
  before_state_snapshot jsonb;
  after_state_snapshot jsonb;
  result_snapshot jsonb;
  provider_action_required boolean := false;
  audit_action text;
  notification_type text;
  active_super_admin_count integer;
begin
  actor_id := public.admin_require_user_governance_actor();
  actor_role := public.admin_governance_actor_role(actor_id);

  -- Serialize user governance globally. This closes both same-key races and
  -- concurrent last-active-Super-Admin removal/suspension races.
  perform pg_advisory_xact_lock(
    hashtextextended('mt-admin-user-governance', 0)
  );

  if request_key is not null then
    select * into existing_action
    from public.user_governance_actions action_row
    where action_row.idempotency_key = request_key;
    if existing_action.id is not null then
      if existing_action.actor_user_id = actor_id
         and existing_action.target_user_id = target_user_id
         and existing_action.expected_user_version = expected_version
         and existing_action.action = normalized_action
         and existing_action.target_role::text is not distinct from normalized_target_role
         and existing_action.reason_code = normalized_reason then
        return public.admin_user_action_result(existing_action.id, true);
      end if;
      return public.admin_user_failure_result(
        actor_id, actor_role, target_user_id, normalized_action,
        normalized_target_role, normalized_reason, expected_version,
        request_key, 'ADMIN_USER_IDEMPOTENCY_CONFLICT',
        'This idempotency key is already bound to another user action.'
      );
    end if;
  end if;

  if request_key is null
     or expected_version is null or expected_version <= 0
     or normalized_action not in (
       'suspend', 'reactivate', 'grant_role', 'revoke_role', 'revoke_sessions'
     ) then
    return public.admin_user_failure_result(
      actor_id, actor_role, target_user_id, normalized_action,
      normalized_target_role, normalized_reason, expected_version,
      request_key, 'ADMIN_USER_VALIDATION_FAILED',
      'A supported action, current version, and UUID idempotency key are required.'
    );
  end if;
  if (
    normalized_action in ('grant_role', 'revoke_role')
    and normalized_target_role not in ('user', 'reviewer', 'admin', 'super_admin')
  ) or (
    normalized_action not in ('grant_role', 'revoke_role')
    and normalized_target_role is not null
  ) then
    return public.admin_user_failure_result(
      actor_id, actor_role, target_user_id, normalized_action,
      normalized_target_role, normalized_reason, expected_version,
      request_key, 'ADMIN_USER_VALIDATION_FAILED',
      'Role actions require one supported role; other actions do not accept a role.'
    );
  end if;
  if not (
    (normalized_action = 'suspend' and normalized_reason in (
      'security_review', 'policy_violation', 'suspected_compromise', 'other'
    ))
    or (normalized_action = 'reactivate' and normalized_reason in (
      'investigation_cleared', 'appeal_upheld', 'administrative_error', 'other'
    ))
    or (normalized_action = 'grant_role' and normalized_reason in (
      'operational_need', 'access_review', 'staffing_change',
      'security_review', 'other'
    ))
    or (normalized_action = 'revoke_role' and normalized_reason in (
      'operational_need', 'access_review', 'staffing_change',
      'security_review', 'other'
    ))
    or (normalized_action = 'revoke_sessions' and normalized_reason in (
      'suspected_compromise', 'access_review', 'user_request', 'other'
    ))
  ) then
    return public.admin_user_failure_result(
      actor_id, actor_role, target_user_id, normalized_action,
      normalized_target_role, normalized_reason, expected_version,
      request_key, 'ADMIN_USER_VALIDATION_FAILED',
      'Choose a supported reason for this user action.'
    );
  end if;

  select * into target
  from public.users target_row
  where target_row.id = target_user_id
  for update;
  if target.id is null then
    return public.admin_user_failure_result(
      actor_id, actor_role, target_user_id, normalized_action,
      normalized_target_role, normalized_reason, expected_version,
      request_key, 'ADMIN_USER_NOT_FOUND', 'The user is unavailable.'
    );
  end if;
  if target.version <> expected_version then
    return public.admin_user_failure_result(
      actor_id, actor_role, target_user_id, normalized_action,
      normalized_target_role, normalized_reason, expected_version,
      request_key, 'ADMIN_USER_VERSION_CONFLICT',
      'This user changed. Reload before applying governance.'
    );
  end if;
  if target.id = actor_id then
    return public.admin_user_failure_result(
      actor_id, actor_role, target_user_id, normalized_action,
      normalized_target_role, normalized_reason, expected_version,
      request_key, 'ADMIN_USER_SELF_ACTION_FORBIDDEN',
      'Use Account Settings for your own account and session actions.'
    );
  end if;
  if target.is_system_identity then
    return public.admin_user_failure_result(
      actor_id, actor_role, target_user_id, normalized_action,
      normalized_target_role, normalized_reason, expected_version,
      request_key, 'ADMIN_USER_SYSTEM_IDENTITY',
      'System and service identities cannot be governed here.'
    );
  end if;
  if actor_role = 'admin'::public.role_code and exists (
    select 1 from public.user_roles target_role_row
    where target_role_row.user_id = target.id
      and target_role_row.role in (
        'admin'::public.role_code, 'super_admin'::public.role_code
      )
  ) then
    return public.admin_user_failure_result(
      actor_id, actor_role, target_user_id, normalized_action,
      normalized_target_role, normalized_reason, expected_version,
      request_key, 'ADMIN_USER_TARGET_FORBIDDEN',
      'Only a Super Admin can govern an administrator account.'
    );
  end if;
  if normalized_action in ('grant_role', 'revoke_role')
     and actor_role <> 'super_admin'::public.role_code then
    return public.admin_user_failure_result(
      actor_id, actor_role, target_user_id, normalized_action,
      normalized_target_role, normalized_reason, expected_version,
      request_key, 'ADMIN_USER_ROLE_FORBIDDEN',
      'Only a Super Admin can manage roles.'
    );
  end if;
  if normalized_action = 'revoke_role' and normalized_target_role = 'user' then
    return public.admin_user_failure_result(
      actor_id, actor_role, target_user_id, normalized_action,
      normalized_target_role, normalized_reason, expected_version,
      request_key, 'ADMIN_USER_ROLE_FORBIDDEN',
      'The baseline user role cannot be revoked.'
    );
  end if;
  if normalized_action = 'revoke_sessions'
     and target.account_status = 'deleted'::public.account_status then
    return public.admin_user_failure_result(
      actor_id, actor_role, target_user_id, normalized_action,
      normalized_target_role, normalized_reason, expected_version,
      request_key, 'ADMIN_USER_STATE_CONFLICT',
      'A deleted account has no revocable application sessions.'
    );
  end if;
  if normalized_action = 'grant_role'
     and normalized_target_role in ('reviewer', 'admin', 'super_admin')
     and target.account_status <> 'active'::public.account_status then
    return public.admin_user_failure_result(
      actor_id, actor_role, target_user_id, normalized_action,
      normalized_target_role, normalized_reason, expected_version,
      request_key, 'ADMIN_USER_STATE_CONFLICT',
      'Privileged roles can only be granted to active accounts.'
    );
  end if;

  if normalized_action = 'suspend'
     and target.account_status <> 'active'::public.account_status then
    return public.admin_user_failure_result(
      actor_id, actor_role, target_user_id, normalized_action,
      normalized_target_role, normalized_reason, expected_version,
      request_key, 'ADMIN_USER_STATE_CONFLICT',
      'Only an active account can be suspended.'
    );
  elsif normalized_action = 'reactivate'
     and target.account_status <> 'suspended'::public.account_status then
    return public.admin_user_failure_result(
      actor_id, actor_role, target_user_id, normalized_action,
      normalized_target_role, normalized_reason, expected_version,
      request_key, 'ADMIN_USER_STATE_CONFLICT',
      'Only a suspended account can be reactivated.'
    );
  elsif normalized_action = 'grant_role' and exists (
    select 1 from public.user_roles role_row
    where role_row.user_id = target.id
      and role_row.role::text = normalized_target_role
  ) then
    return public.admin_user_failure_result(
      actor_id, actor_role, target_user_id, normalized_action,
      normalized_target_role, normalized_reason, expected_version,
      request_key, 'ADMIN_USER_STATE_CONFLICT',
      'The user already has this role.'
    );
  elsif normalized_action = 'revoke_role' and not exists (
    select 1 from public.user_roles role_row
    where role_row.user_id = target.id
      and role_row.role::text = normalized_target_role
  ) then
    return public.admin_user_failure_result(
      actor_id, actor_role, target_user_id, normalized_action,
      normalized_target_role, normalized_reason, expected_version,
      request_key, 'ADMIN_USER_STATE_CONFLICT',
      'The user does not have this role.'
    );
  end if;

  if (
    normalized_action = 'suspend'
    or (
      normalized_action = 'revoke_role'
      and normalized_target_role = 'super_admin'
    )
  ) and target.account_status = 'active'::public.account_status and exists (
    select 1 from public.user_roles role_row
    where role_row.user_id = target.id
      and role_row.role = 'super_admin'::public.role_code
  ) then
    select count(distinct target_super.id)::integer
    into active_super_admin_count
    from public.users target_super
    join public.user_roles target_super_role
      on target_super_role.user_id = target_super.id
    where target_super.account_status = 'active'::public.account_status
      and not target_super.is_system_identity
      and target_super_role.role = 'super_admin'::public.role_code;
    if active_super_admin_count <= 1 then
      return public.admin_user_failure_result(
        actor_id, actor_role, target_user_id, normalized_action,
        normalized_target_role, normalized_reason, expected_version,
        request_key, 'ADMIN_USER_LAST_SUPER_ADMIN',
        'At least one active Super Admin must remain.'
      );
    end if;
  end if;

  before_state_snapshot := jsonb_build_object(
    'target_user_id', target.id,
    'account_status', target.account_status,
    'version', target.version,
    'roles', coalesce((
      select jsonb_agg(role_row.role order by role_row.role)
      from public.user_roles role_row
      where role_row.user_id = target.id
    ), '[]'::jsonb),
    'is_system_identity', target.is_system_identity
  );

  if normalized_action = 'suspend' then
    update public.users target_row set
      account_status = 'suspended'::public.account_status,
      updated_at = action_created_at
    where target_row.id = target.id
    returning * into target;
    audit_action := 'admin.user.suspend';
    notification_type := 'account_suspended_by_admin';
  elsif normalized_action = 'reactivate' then
    update public.users target_row set
      account_status = 'active'::public.account_status,
      updated_at = action_created_at
    where target_row.id = target.id
    returning * into target;
    audit_action := 'admin.user.reactivate';
    notification_type := 'account_reactivated_by_admin';
  elsif normalized_action = 'grant_role' then
    insert into public.user_roles (user_id, role, assigned_by, reason)
    values (
      target.id, normalized_target_role::public.role_code,
      actor_id, normalized_reason
    );
    update public.users target_row set updated_at = action_created_at
    where target_row.id = target.id returning * into target;
    audit_action := 'admin.user.grant_role';
    notification_type := 'role_granted_by_admin';
  elsif normalized_action = 'revoke_role' then
    delete from public.user_roles role_row
    where role_row.user_id = target.id
      and role_row.role = normalized_target_role::public.role_code;
    update public.users target_row set updated_at = action_created_at
    where target_row.id = target.id returning * into target;
    audit_action := 'admin.user.revoke_role';
    notification_type := 'role_revoked_by_admin';
  else
    update public.users target_row set updated_at = action_created_at
    where target_row.id = target.id returning * into target;
    audit_action := 'admin.user.revoke_sessions_requested';
    notification_type := 'admin_session_revocation_requested';
    provider_action_required := true;
  end if;

  after_state_snapshot := jsonb_build_object(
    'target_user_id', target.id,
    'account_status', target.account_status,
    'version', target.version,
    'roles', coalesce((
      select jsonb_agg(role_row.role order by role_row.role)
      from public.user_roles role_row
      where role_row.user_id = target.id
    ), '[]'::jsonb),
    'is_system_identity', target.is_system_identity,
    'provider_action_required', provider_action_required
  );

  result_snapshot := jsonb_build_object(
    'actor', public.admin_user_actor_json(actor_id),
    'action', jsonb_build_object(
      'id', action_id,
      'target_user_id', target.id,
      'action', normalized_action,
      'target_role', normalized_target_role,
      'reason_code', normalized_reason,
      'actor_user_id', actor_id,
      'actor_role', actor_role,
      'expected_user_version', expected_version,
      'provider_action_required', provider_action_required,
      'policy_version', policy,
      'created_at', action_created_at
    ),
    'user', public.admin_user_summary_json(target.id)
  );

  insert into public.user_governance_actions (
    id, target_user_id, actor_user_id, actor_role, action, target_role,
    reason_code, expected_user_version, idempotency_key,
    provider_action_required, before_state, result_snapshot,
    policy_version, created_at
  ) values (
    action_id, target.id, actor_id, actor_role, normalized_action,
    normalized_target_role::public.role_code, normalized_reason,
    expected_version, request_key, provider_action_required,
    before_state_snapshot, result_snapshot, policy, action_created_at
  );

  insert into public.notifications (recipient_user_id, type, payload)
  values (target.id, notification_type, jsonb_build_object(
    'user_governance_action_id', action_id,
    'action', normalized_action,
    'target_role', normalized_target_role,
    'reason_code', normalized_reason,
    'account_status', target.account_status,
    'provider_action_required', provider_action_required,
    'status', case when provider_action_required then 'requested' else 'completed' end
  ));

  insert into public.audit_logs (
    actor_user_id, actor_role, action, target_type, target_id, request_id,
    reason_code, before_state, after_state, policy_version, result
  ) values (
    actor_id, actor_role, audit_action, 'user', target.id::text,
    request_key::text, normalized_reason, before_state_snapshot,
    after_state_snapshot || jsonb_build_object(
      'user_governance_action_id', action_id
    ), policy, 'success'
  );

  return public.admin_user_action_result(action_id, false);
end;
$$;

revoke all on function public.bump_user_version()
  from public, anon, authenticated, service_role;
revoke all on function public.admin_user_error(text, text)
  from public, anon, authenticated, service_role;
revoke all on function public.admin_require_user_governance_actor()
  from public, anon, authenticated, service_role;
revoke all on function public.admin_user_actor_json(uuid)
  from public, anon, authenticated, service_role;
revoke all on function public.admin_user_summary_json(uuid)
  from public, anon, authenticated, service_role;
revoke all on function public.admin_user_action_result(uuid, boolean)
  from public, anon, authenticated, service_role;
revoke all on function public.admin_user_failure_result(
  uuid, public.role_code, uuid, text, text, text, integer, uuid, text, text
) from public, anon, authenticated, service_role;
revoke all on function public.admin_list_users(
  text, text, text, text, integer, integer
) from public, anon, authenticated, service_role;
revoke all on function public.admin_get_user(uuid)
  from public, anon, authenticated, service_role;
revoke all on function public.admin_govern_user(
  uuid, integer, text, text, text, uuid
) from public, anon, authenticated, service_role;

grant execute on function public.admin_list_users(
  text, text, text, text, integer, integer
) to authenticated;
grant execute on function public.admin_get_user(uuid) to authenticated;
grant execute on function public.admin_govern_user(
  uuid, integer, text, text, text, uuid
) to authenticated;

commit;
