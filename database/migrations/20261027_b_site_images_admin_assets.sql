begin;

-- Admin redesign (2026-10-27): the Works table shows each work's series and
-- whether its display and thumbnail files exist, and the new "网站图片位"
-- page chooses which published works appear in the fixed image places of the
-- visitor site. Visitor delivery is unchanged: a site image is served only
-- while its work passes public_delivery_work_json (published, scanned clean).

-- ----- Works table: series and derivative facts -----------------------------

create or replace function public.admin_image_derivative_json(target_image_id uuid, target_kind text)
returns jsonb
language sql
stable
security definer
set search_path = ''
as $$
  select jsonb_build_object(
    'mime_type', a.mime_type,
    'byte_size', a.byte_size,
    'width', a.width,
    'height', a.height,
    'scan_status', a.scan_status
  )
  from public.image_assets a
  where a.image_id = $1
    and a.kind = $2
    and a.deleted_at is null
  order by a.created_at desc, a.id
  limit 1
$$;

-- Same as 20260723_admin_works_governance.sql, plus series and derivatives.
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
    'content_category', v.content_category,
    'derivatives', jsonb_build_object(
      'original', public.admin_image_derivative_json(i.id, 'original'),
      'display', public.admin_image_derivative_json(i.id, 'display'),
      'thumbnail', public.admin_image_derivative_json(i.id, 'thumbnail')
    ),
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

-- ----- Site image places ------------------------------------------------------

create table if not exists public.site_image_slots (
  slot_key text not null check (slot_key in (
    'home_hero', 'home_selected', 'home_about',
    'works_poster_colour', 'works_poster_grey', 'contact'
  )),
  position smallint not null check (position between 1 and 5),
  image_id uuid not null references public.images(id) on delete cascade,
  updated_by uuid not null references public.users(id) on delete restrict,
  updated_at timestamptz not null default now(),
  primary key (slot_key, position),
  check (slot_key = 'home_selected' or position = 1)
);

-- No direct table access for any API role.
alter table public.site_image_slots enable row level security;
revoke all on public.site_image_slots from public, anon, authenticated, service_role;

create or replace function public.site_image_slot_capacity(target_slot text)
returns integer
language sql
immutable
set search_path = ''
as $$
  select case $1
    when 'home_selected' then 5
    when 'home_hero' then 1
    when 'home_about' then 1
    when 'works_poster_colour' then 1
    when 'works_poster_grey' then 1
    when 'contact' then 1
    else 0
  end
$$;

create or replace function public.admin_site_images_json()
returns jsonb
language sql
stable
security definer
set search_path = ''
as $$
  select jsonb_build_object(
    'items', coalesce(jsonb_agg(jsonb_build_object(
      'slot_key', s.slot_key,
      'position', s.position,
      'image_id', s.image_id,
      'updated_at', s.updated_at,
      'live', public.public_delivery_work_json(s.image_id) is not null,
      'work', public.admin_image_summary_json(s.image_id)
    ) order by s.slot_key, s.position), '[]'::jsonb)
  )
  from public.site_image_slots s
$$;

create or replace function public.admin_list_site_images()
returns jsonb
language plpgsql
stable
security definer
set search_path = ''
as $$
begin
  perform public.admin_require_governance_actor();
  return public.admin_site_images_json();
end;
$$;

-- Replace every image of one place at once; an empty list restores the
-- site's built-in image. Each work must be live on the public site, and the
-- two Works posters only take works of their own series.
create or replace function public.admin_set_site_image_slot(
  target_slot text,
  target_image_ids uuid[]
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  actor_id uuid;
  actor_role public.role_code;
  capacity integer := public.site_image_slot_capacity(target_slot);
  submitted uuid[] := coalesce(target_image_ids, '{}'::uuid[]);
  before_ids jsonb;
  work jsonb;
  chosen_id uuid;
  slot_position integer := 0;
begin
  actor_id := public.admin_require_governance_actor();
  actor_role := public.admin_governance_actor_role(actor_id);
  if capacity = 0 then
    return public.admin_governance_error('ADMIN_SITE_IMAGE_SLOT_INVALID', 'This image place does not exist.');
  end if;
  if cardinality(submitted) > capacity
     or array_position(submitted, null) is not null
     or (select count(distinct value) from unnest(submitted) value) <> cardinality(submitted) then
    return public.admin_governance_error(
      'ADMIN_GOVERNANCE_VALIDATION_FAILED',
      'Choose up to ' || capacity || ' different works for this place.'
    );
  end if;
  foreach chosen_id in array submitted loop
    work := public.public_delivery_work_json(chosen_id);
    if work is null then
      return public.admin_governance_error(
        'ADMIN_SITE_IMAGE_NOT_LIVE',
        'Only works that are published on the website can be used here.'
      );
    end if;
    if (target_slot = 'works_poster_colour' and work ->> 'content_category' <> 'concrete')
       or (target_slot = 'works_poster_grey' and work ->> 'content_category' <> 'abstract') then
      return public.admin_governance_error(
        'ADMIN_SITE_IMAGE_SERIES_MISMATCH',
        'A series poster must use a work from that series.'
      );
    end if;
  end loop;

  select coalesce(jsonb_agg(s.image_id order by s.position), '[]'::jsonb)
  into before_ids
  from public.site_image_slots s
  where s.slot_key = target_slot;

  delete from public.site_image_slots s where s.slot_key = target_slot;
  foreach chosen_id in array submitted loop
    slot_position := slot_position + 1;
    insert into public.site_image_slots (slot_key, position, image_id, updated_by, updated_at)
    values (target_slot, slot_position, chosen_id, actor_id, now());
  end loop;

  insert into public.audit_logs (
    actor_user_id, actor_role, action, target_type, target_id, request_id,
    reason_code, before_state, after_state, policy_version, result
  ) values (
    actor_id, actor_role,
    case when cardinality(submitted) = 0 then 'site_image.reset' else 'site_image.updated' end,
    'site_image_slot', target_slot, gen_random_uuid()::text,
    null,
    jsonb_build_object('image_ids', before_ids),
    jsonb_build_object('image_ids', to_jsonb(submitted)),
    'mt-site-images-2026-10-v1', 'success'
  );

  return public.admin_site_images_json();
end;
$$;

-- Visitor read: only places whose work is live on the public site.
create or replace function public.get_public_site_images()
returns jsonb
language sql
stable
security definer
set search_path = ''
as $$
  select jsonb_build_object('items', coalesce(jsonb_agg(jsonb_build_object(
    'slot_key', live.slot_key,
    'position', live.position,
    'work', live.work
  ) order by live.slot_key, live.position), '[]'::jsonb))
  from (
    select s.slot_key, s.position, public.public_delivery_work_json(s.image_id) as work
    from public.site_image_slots s
  ) live
  where live.work is not null
$$;

revoke all on function public.admin_image_derivative_json(uuid, text)
  from public, anon, authenticated, service_role;
revoke all on function public.site_image_slot_capacity(text)
  from public, anon, authenticated, service_role;
revoke all on function public.admin_site_images_json()
  from public, anon, authenticated, service_role;
revoke all on function public.admin_list_site_images()
  from public, anon, authenticated, service_role;
revoke all on function public.admin_set_site_image_slot(text, uuid[])
  from public, anon, authenticated, service_role;
revoke all on function public.get_public_site_images()
  from public, anon, authenticated, service_role;

grant execute on function public.admin_list_site_images() to authenticated;
grant execute on function public.admin_set_site_image_slot(text, uuid[]) to authenticated;
grant execute on function public.get_public_site_images() to anon, authenticated;

commit;
