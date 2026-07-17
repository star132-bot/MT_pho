-- Existing-environment patch: inactive privileged users must lose role scope.
-- Fresh environments receive the same definition from supabase_phase1_auth_rls.sql.
begin;

create or replace function public.has_any_role(required_roles public.role_code[])
returns boolean
language sql
stable
security definer
set search_path = ''
as $$
  select exists (
    select 1
    from public.user_roles ur
    join public.users u on u.id = ur.user_id
    where ur.user_id = (select public.current_app_user_id())
      and ur.role = any(required_roles)
      and u.account_status = 'active'::public.account_status
  )
$$;

grant execute on function public.has_any_role(public.role_code[]) to authenticated;
revoke all on function public.has_any_role(public.role_code[]) from anon;

commit;
