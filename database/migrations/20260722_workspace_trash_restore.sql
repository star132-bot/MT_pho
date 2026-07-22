-- Phase 2G: owner-scoped Trash listing for the existing reversible Draft restore boundary.
begin;

create or replace function public.workspace_list_trashed_drafts()
returns jsonb
language plpgsql
stable
security definer
set search_path = ''
as $$
declare
  app_user_id uuid;
  draft_rows jsonb;
begin
  if public.is_recovery_auth_session() then
    raise exception 'recovery session cannot access Workspace Trash' using errcode = '42501';
  end if;
  app_user_id := public.require_active_workspace_user();
  select coalesce(
    jsonb_agg(
      public.workspace_draft_json(i.id) || jsonb_build_object('deleted_at', i.deleted_at)
      order by i.deleted_at desc
    ),
    '[]'::jsonb
  )
  into draft_rows
  from public.images i
  where i.owner_user_id = app_user_id
    and i.workflow_status in ('draft'::public.workflow_status, 'changes_requested'::public.workflow_status)
    and i.deleted_at is not null;
  return jsonb_build_object('images', draft_rows);
end;
$$;

revoke all on function public.workspace_list_trashed_drafts()
  from public, anon, authenticated, service_role;
grant execute on function public.workspace_list_trashed_drafts() to authenticated;

commit;
