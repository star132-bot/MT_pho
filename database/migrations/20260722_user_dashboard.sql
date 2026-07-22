begin;

-- User Dashboard read model. Counts and operational summaries are aggregated
-- server-side so the browser never infers product state by walking Draft rows.

create or replace function public.dashboard_image_json(target_image_id uuid)
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
    'processing_status', i.processing_status,
    'workflow_status', i.workflow_status,
    'publication_status', i.publication_status,
    'updated_at', i.updated_at,
    'thumbnail_asset', (
      select jsonb_build_object(
        'id', a.id,
        'kind', a.kind,
        'storage_bucket', 'image-thumbnails',
        'storage_key', a.storage_key,
        'mime_type', a.mime_type,
        'byte_size', a.byte_size,
        'width', a.width,
        'height', a.height,
        'scan_status', a.scan_status,
        'scan_policy_version', a.scan_policy_version
      )
      from public.image_assets a
      where a.image_id = i.id
        and a.kind = 'thumbnail'
        and a.deleted_at is null
        and a.scan_status = 'clean'
        and a.scan_policy_version = 'mt-asset-scan-2026-07-v1'
      order by a.created_at desc, a.id
      limit 1
    )
  )
  from public.images i
  join public.image_versions v on v.id = i.current_version_id and v.image_id = i.id
  where i.id = target_image_id
$$;

revoke all on function public.dashboard_image_json(uuid)
  from public, anon, authenticated, service_role;

create or replace function public.get_my_dashboard()
returns jsonb
language plpgsql
stable
security definer
set search_path = ''
as $$
declare
  app_user_id uuid;
  status_counts jsonb;
  needs_attention jsonb;
  recent_images jsonb;
  draft_images jsonb;
  review_activity jsonb;
  storage_usage jsonb;
begin
  if public.is_recovery_auth_session() then
    raise exception 'recovery session cannot access the user dashboard' using errcode = '42501';
  end if;
  app_user_id := public.require_active_workspace_user();

  select jsonb_build_object(
    'drafts', count(*) filter (
      where i.workflow_status = 'draft'::public.workflow_status
        and i.deleted_at is null
    ),
    'submitted', count(*) filter (
      where i.workflow_status in (
        'submitted'::public.workflow_status,
        'in_review'::public.workflow_status
      )
        and i.deleted_at is null
    ),
    'changes_requested', count(*) filter (
      where i.workflow_status = 'changes_requested'::public.workflow_status
        and i.deleted_at is null
    ),
    'published', count(*) filter (
      where i.publication_status = 'published'::public.publication_status
        and i.deleted_at is null
    ),
    'unpublished', count(*) filter (
      where i.publication_status = 'unpublished'::public.publication_status
        and i.deleted_at is null
    )
  )
  into status_counts
  from public.images i
  where i.owner_user_id = app_user_id;

  select coalesce(jsonb_agg(entry order by priority, updated_at desc, image_id), '[]'::jsonb)
  into needs_attention
  from (
    select
      jsonb_build_object(
        'type', case
          when i.workflow_status = 'changes_requested'::public.workflow_status then 'changes_requested'
          else 'processing_failed'
        end,
        'image_id', i.id,
        'title', coalesce(nullif(v.title, ''), i.original_filename),
        'message', case
          when i.workflow_status = 'changes_requested'::public.workflow_status
            then 'A reviewer requested updates before this work can continue.'
          else 'Image processing failed. Open the Workspace to review or retry the upload.'
        end,
        'updated_at', i.updated_at,
        'workspace_path', '/workspace/images'
      ) as entry,
      case
        when i.workflow_status = 'changes_requested'::public.workflow_status then 1
        else 2
      end as priority,
      i.updated_at,
      i.id as image_id
    from public.images i
    join public.image_versions v on v.id = i.current_version_id
    where i.owner_user_id = app_user_id
      and i.deleted_at is null
      and (
        i.workflow_status = 'changes_requested'::public.workflow_status
        or i.processing_status = 'failed'::public.processing_status
      )
    order by priority, i.updated_at desc, i.id
    limit 8
  ) attention_rows;

  select coalesce(jsonb_agg(public.dashboard_image_json(image_row.id) order by image_row.updated_at desc, image_row.id), '[]'::jsonb)
  into recent_images
  from (
    select i.id, i.updated_at
    from public.images i
    where i.owner_user_id = app_user_id
      and i.deleted_at is null
    order by i.updated_at desc, i.id
    limit 8
  ) image_row;

  select coalesce(jsonb_agg(public.dashboard_image_json(image_row.id) order by image_row.updated_at desc, image_row.id), '[]'::jsonb)
  into draft_images
  from (
    select i.id, i.updated_at
    from public.images i
    where i.owner_user_id = app_user_id
      and i.deleted_at is null
      and i.workflow_status in (
        'draft'::public.workflow_status,
        'changes_requested'::public.workflow_status
      )
    order by i.updated_at desc, i.id
    limit 12
  ) image_row;

  select coalesce(jsonb_agg(entry order by occurred_at desc, submission_id), '[]'::jsonb)
  into review_activity
  from (
    select
      jsonb_build_object(
        'submission_id', s.id,
        'image_id', s.image_id,
        'title', coalesce(nullif(v.title, ''), i.original_filename),
        'status', s.status,
        'decision', decision.decision,
        'submitted_at', s.submitted_at,
        'review_started_at', s.review_started_at,
        'completed_at', s.completed_at,
        'occurred_at', coalesce(decision.created_at, s.completed_at, s.review_started_at, s.submitted_at)
      ) as entry,
      coalesce(decision.created_at, s.completed_at, s.review_started_at, s.submitted_at) as occurred_at,
      s.id as submission_id
    from public.review_submissions s
    join public.images i on i.id = s.image_id
    join public.image_versions v on v.id = s.image_version_id and v.image_id = i.id
    left join lateral (
      select d.decision, d.created_at
      from public.review_decisions d
      where d.submission_id = s.id
      order by d.created_at desc, d.id
      limit 1
    ) decision on true
    where s.submitted_by_user_id = app_user_id
      and i.owner_user_id = app_user_id
    order by occurred_at desc, s.id
    limit 10
  ) activity_rows;

  select jsonb_build_object(
    'used_bytes', coalesce(sum(a.byte_size), 0),
    'asset_count', count(a.id),
    'image_count', count(distinct a.image_id),
    'quota_bytes', null
  )
  into storage_usage
  from public.image_assets a
  where a.owner_user_id = app_user_id
    and a.deleted_at is null;

  return jsonb_build_object(
    'status_counts', status_counts,
    'needs_attention', needs_attention,
    'recent_images', recent_images,
    'drafts', draft_images,
    'review_activity', review_activity,
    'storage_usage', storage_usage,
    'capabilities', jsonb_build_object(
      'storage_quota', jsonb_build_object(
        'available', false,
        'reason', 'not_configured'
      ),
      'public_portfolio', jsonb_build_object(
        'available', false,
        'reason', 'public_delivery_not_connected'
      )
    ),
    'generated_at', now()
  );
end;
$$;

revoke all on function public.get_my_dashboard()
  from public, anon, service_role;
grant execute on function public.get_my_dashboard() to authenticated;

commit;
