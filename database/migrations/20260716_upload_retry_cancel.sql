-- Phase 2B: idempotent upload cancellation and tracked Storage cleanup.
begin;

alter table public.upload_intents
  add column if not exists canceled_at timestamptz,
  add column if not exists cleanup_status text not null default 'not_required';

alter table public.upload_intents
  drop constraint if exists upload_intents_cleanup_status_check;
alter table public.upload_intents
  add constraint upload_intents_cleanup_status_check
  check (cleanup_status in ('not_required', 'pending', 'complete', 'failed'));

create or replace function public.workspace_cancel_upload_intent(upload_id uuid)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  app_user_id uuid;
  upload_row public.upload_intents%rowtype;
begin
  app_user_id := public.require_active_workspace_user();
  select * into upload_row
  from public.upload_intents u
  where u.id = upload_id and u.owner_user_id = app_user_id
  for update;

  if upload_row.id is null then
    return jsonb_build_object('error', jsonb_build_object(
      'code', 'UPLOAD_INTENT_NOT_FOUND',
      'message', 'The upload intent is unavailable.'
    ));
  end if;
  if upload_row.status = 'completed' then
    return jsonb_build_object('error', jsonb_build_object(
      'code', 'UPLOAD_INTENT_NOT_CANCELABLE',
      'message', 'A completed upload cannot be canceled.'
    ));
  end if;

  if upload_row.status <> 'canceled' then
    update public.upload_intents set
      status = 'canceled',
      canceled_at = now(),
      cleanup_status = 'pending',
      updated_at = now()
    where id = upload_row.id
    returning * into upload_row;
  elsif upload_row.cleanup_status <> 'complete' then
    update public.upload_intents set cleanup_status = 'pending', updated_at = now()
    where id = upload_row.id
    returning * into upload_row;
  end if;

  return jsonb_build_object(
    'canceled', true,
    'upload_id', upload_row.id,
    'cleanup_status', upload_row.cleanup_status,
    'assets', upload_row.expected_assets
  );
end;
$$;

create or replace function public.workspace_finish_upload_cleanup(upload_id uuid, cleanup_succeeded boolean)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  app_user_id uuid;
  changed_id uuid;
  next_status text := case when cleanup_succeeded then 'complete' else 'failed' end;
begin
  app_user_id := public.require_active_workspace_user();
  update public.upload_intents u set
    cleanup_status = next_status,
    updated_at = now()
  where u.id = upload_id
    and u.owner_user_id = app_user_id
    and u.status = 'canceled'
  returning u.id into changed_id;

  if changed_id is null then
    return jsonb_build_object('error', jsonb_build_object(
      'code', 'UPLOAD_INTENT_NOT_FOUND',
      'message', 'The canceled upload intent is unavailable.'
    ));
  end if;
  return jsonb_build_object(
    'upload_id', changed_id,
    'cleanup_status', next_status
  );
end;
$$;

grant execute on function public.workspace_cancel_upload_intent(uuid) to authenticated;
grant execute on function public.workspace_finish_upload_cleanup(uuid, boolean) to authenticated;
revoke all on function public.workspace_cancel_upload_intent(uuid) from anon, public;
revoke all on function public.workspace_finish_upload_cleanup(uuid, boolean) from anon, public;

commit;
