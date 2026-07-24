#!/usr/bin/env python3
"""Development-only, rollback-only Admin Users governance acceptance."""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess


ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT / ".env"

USER_IDS = tuple(
    f"00000000-0000-4000-8000-00000000f8{suffix}"
    for suffix in ("01", "02", "03", "04", "05", "06", "07", "08")
)
FOLDER_IDS = ("00000000-0000-4000-8000-00000000f811",)
IMAGE_IDS = ("00000000-0000-4000-8000-00000000f821",)

EXPECTED_MARKERS = (
    "admin_users_database_pg_proc_security=yes",
    "admin_users_database_acl_rls=yes",
    "admin_users_database_role_aal_boundary=yes",
    "admin_users_database_list_detail=yes",
    "admin_users_database_account_state_cas=yes",
    "admin_users_database_role_governance=yes",
    "admin_users_database_idempotency=yes",
    "admin_users_database_identity_super_guard=yes",
    "admin_users_database_session_intent=yes",
    "admin_users_database_failure_audit=yes",
    "admin_users_database_append_only=yes",
    "admin_users_database_fixtures_rolled_back=yes",
)


SQL = r"""
\set ON_ERROR_STOP on

begin;
select pg_advisory_xact_lock(hashtextextended('mt-admin-users-database-test', 0));

do $$
declare
  proc_row record;
  authenticated_role oid := (select oid from pg_roles where rolname = 'authenticated');
begin
  if authenticated_role is null
     or not exists (select 1 from pg_roles where rolname = 'anon')
     or not exists (select 1 from pg_roles where rolname = 'service_role') then
    raise exception 'Supabase database roles are unavailable';
  end if;

  for proc_row in
    select
      p.oid,
      p.oid::regprocedure::text as identity,
      p.proowner,
      p.prosecdef,
      p.proconfig,
      p.oid in (
        'public.admin_list_users(text,text,text,text,integer,integer)'::regprocedure,
        'public.admin_get_user(uuid)'::regprocedure,
        'public.admin_govern_user(uuid,integer,text,text,text,uuid)'::regprocedure
      ) as allow_authenticated,
      p.oid in (
        'public.bump_user_version()'::regprocedure,
        'public.admin_user_error(text,text)'::regprocedure
      ) as invoker_helper
    from pg_proc p
    where p.oid in (
      'public.bump_user_version()'::regprocedure,
      'public.admin_user_error(text,text)'::regprocedure,
      'public.admin_require_user_governance_actor()'::regprocedure,
      'public.admin_user_actor_json(uuid)'::regprocedure,
      'public.admin_user_summary_json(uuid)'::regprocedure,
      'public.admin_list_users(text,text,text,text,integer,integer)'::regprocedure,
      'public.admin_get_user(uuid)'::regprocedure,
      'public.admin_user_action_result(uuid,boolean)'::regprocedure,
      'public.admin_user_failure_result(uuid,public.role_code,uuid,text,text,text,integer,uuid,text,text)'::regprocedure,
      'public.admin_govern_user(uuid,integer,text,text,text,uuid)'::regprocedure
    )
  loop
    if proc_row.prosecdef = proc_row.invoker_helper then
      raise exception '% has an invalid SECURITY DEFINER setting', proc_row.identity;
    end if;
    if not coalesce(proc_row.proconfig, '{}'::text[])
      @> array['search_path=""']::text[] then
      raise exception '% does not pin an empty search_path', proc_row.identity;
    end if;
    if has_function_privilege('authenticated', proc_row.oid, 'EXECUTE')
       <> proc_row.allow_authenticated then
      raise exception '% has an invalid authenticated EXECUTE grant', proc_row.identity;
    end if;
    if has_function_privilege('anon', proc_row.oid, 'EXECUTE')
       or has_function_privilege('service_role', proc_row.oid, 'EXECUTE') then
      raise exception '% is executable by anon or service_role', proc_row.identity;
    end if;
    if exists (
      select 1
      from aclexplode(coalesce(
        (select p2.proacl from pg_proc p2 where p2.oid = proc_row.oid),
        acldefault('f', proc_row.proowner)
      )) privilege
      where privilege.privilege_type = 'EXECUTE'
        and privilege.grantee not in (
          proc_row.proowner,
          case when proc_row.allow_authenticated
            then authenticated_role else proc_row.proowner end
        )
    ) then
      raise exception '% grants EXECUTE outside its exact allowlist', proc_row.identity;
    end if;
  end loop;

  if (select count(*) from pg_proc p where p.oid in (
    'public.bump_user_version()'::regprocedure,
    'public.admin_user_error(text,text)'::regprocedure,
    'public.admin_require_user_governance_actor()'::regprocedure,
    'public.admin_user_actor_json(uuid)'::regprocedure,
    'public.admin_user_summary_json(uuid)'::regprocedure,
    'public.admin_list_users(text,text,text,text,integer,integer)'::regprocedure,
    'public.admin_get_user(uuid)'::regprocedure,
    'public.admin_user_action_result(uuid,boolean)'::regprocedure,
    'public.admin_user_failure_result(uuid,public.role_code,uuid,text,text,text,integer,uuid,text,text)'::regprocedure,
    'public.admin_govern_user(uuid,integer,text,text,text,uuid)'::regprocedure
  )) <> 10 then
    raise exception 'Admin Users function metadata is incomplete';
  end if;

  if position(
    'pg_advisory_xact_lock' in pg_get_functiondef(
      'public.admin_govern_user(uuid,integer,text,text,text,uuid)'::regprocedure
    )
  ) = 0 or position(
    'ADMIN_USER_LAST_SUPER_ADMIN' in pg_get_functiondef(
      'public.admin_govern_user(uuid,integer,text,text,text,uuid)'::regprocedure
    )
  ) = 0 then
    raise exception 'concurrent last-Super-Admin guard is incomplete';
  end if;
end
$$;

select 'admin_users_database_pg_proc_security=yes';

do $$
begin
  if has_table_privilege('anon', 'public.user_governance_actions', 'SELECT')
     or has_table_privilege('authenticated', 'public.user_governance_actions', 'SELECT')
     or has_table_privilege('authenticated', 'public.user_governance_actions', 'INSERT')
     or has_table_privilege('authenticated', 'public.user_governance_actions', 'UPDATE')
     or has_table_privilege('authenticated', 'public.user_governance_actions', 'DELETE')
     or has_table_privilege('service_role', 'public.user_governance_actions', 'SELECT')
     or has_table_privilege('authenticated', 'public.users', 'UPDATE')
     or has_table_privilege('authenticated', 'public.user_roles', 'INSERT')
     or has_table_privilege('authenticated', 'public.user_roles', 'UPDATE')
     or has_table_privilege('authenticated', 'public.user_roles', 'DELETE') then
    raise exception 'Admin Users tables expose direct governance access';
  end if;
  if not (select relrowsecurity from pg_class where oid = 'public.user_governance_actions'::regclass) then
    raise exception 'user_governance_actions RLS is disabled';
  end if;
  if exists (
    select 1 from pg_policies policy
    where policy.schemaname = 'public'
      and policy.tablename = 'user_governance_actions'
  ) then
    raise exception 'user_governance_actions unexpectedly has a direct row policy';
  end if;
  if not exists (
    select 1 from pg_trigger
    where tgrelid = 'public.user_governance_actions'::regclass
      and tgname = 'user_governance_actions_append_only'
      and not tgisinternal
  ) or not exists (
    select 1 from pg_trigger
    where tgrelid = 'public.users'::regclass
      and tgname = 'users_version_bump'
      and not tgisinternal
  ) then
    raise exception 'Admin Users integrity trigger is missing';
  end if;
end
$$;

set local role anon;
do $$
begin
  begin
    perform public.admin_list_users('all', 'all', '', 'updated_desc', 30, 0);
    raise exception 'anon executed admin_list_users';
  exception when insufficient_privilege then null;
  end;
  begin
    perform public.admin_get_user('00000000-0000-4000-8000-00000000f801');
    raise exception 'anon executed admin_get_user';
  exception when insufficient_privilege then null;
  end;
end
$$;
reset role;

set local role service_role;
do $$
begin
  begin
    perform public.admin_list_users('all', 'all', '', 'updated_desc', 30, 0);
    raise exception 'service_role executed admin_list_users';
  exception when insufficient_privilege then null;
  end;
  begin
    perform public.admin_govern_user(
      '00000000-0000-4000-8000-00000000f801', 1, 'suspend', null,
      'security_review', '00000000-0000-4000-8000-00000000f861'
    );
    raise exception 'service_role executed admin_govern_user';
  exception when insufficient_privilege then null;
  end;
end
$$;
reset role;

select 'admin_users_database_acl_rls=yes';

do $$
begin
  if exists (
    select 1 from public.users
    where id between '00000000-0000-4000-8000-00000000f801'::uuid
      and '00000000-0000-4000-8000-00000000f808'::uuid
  ) or exists (
    select 1 from public.folders
    where id = '00000000-0000-4000-8000-00000000f811'
  ) or exists (
    select 1 from public.images
    where id = '00000000-0000-4000-8000-00000000f821'
  ) then
    raise exception 'fixed Admin Users fixtures already exist';
  end if;
end
$$;

create function pg_temp.set_admin_users_claims(
  actor_id uuid,
  actor_aal text default 'aal1',
  recovery boolean default false
)
returns void
language plpgsql
as $$
begin
  perform set_config(
    'request.jwt.claims',
    jsonb_build_object(
      'sub', actor_id,
      'role', 'authenticated',
      'aal', actor_aal,
      'amr', case when recovery
        then jsonb_build_array(jsonb_build_object('method', 'recovery'))
        when actor_aal = 'aal2'
          then jsonb_build_array(
            jsonb_build_object('method', 'password'),
            jsonb_build_object('method', 'totp')
          )
        else jsonb_build_array(jsonb_build_object('method', 'password'))
      end
    )::text,
    true
  );
end
$$;

insert into public.users (
  id, auth_subject, email, email_verified_at, account_status,
  is_system_identity, created_at, updated_at, last_active_at
) values
  ('00000000-0000-4000-8000-00000000f801', '00000000-0000-4000-8000-00000000f801', 'users-target@example.test', now(), 'active', false, now() - interval '30 days', now() - interval '1 day', now() - interval '2 hours'),
  ('00000000-0000-4000-8000-00000000f802', '00000000-0000-4000-8000-00000000f802', 'users-admin@example.test', now(), 'active', false, now() - interval '60 days', now(), now()),
  ('00000000-0000-4000-8000-00000000f803', '00000000-0000-4000-8000-00000000f803', 'users-super@example.test', now(), 'active', false, now() - interval '90 days', now(), now()),
  ('00000000-0000-4000-8000-00000000f804', '00000000-0000-4000-8000-00000000f804', 'users-peer-super@example.test', now(), 'active', false, now() - interval '80 days', now(), now()),
  ('00000000-0000-4000-8000-00000000f805', '00000000-0000-4000-8000-00000000f805', 'users-suspended@example.test', now(), 'suspended', false, now() - interval '20 days', now(), now() - interval '10 days'),
  ('00000000-0000-4000-8000-00000000f806', '00000000-0000-4000-8000-00000000f806', 'users-system@example.test', now(), 'active', true, now() - interval '100 days', now(), now()),
  ('00000000-0000-4000-8000-00000000f807', '00000000-0000-4000-8000-00000000f807', 'users-inactive-admin@example.test', now(), 'suspended', false, now() - interval '70 days', now(), now()),
  ('00000000-0000-4000-8000-00000000f808', '00000000-0000-4000-8000-00000000f808', 'users-member@example.test', now(), 'active', false, now() - interval '10 days', now(), now());

insert into public.user_profiles (
  user_id, display_name, professional_headline, company, city, country_code
) values
  ('00000000-0000-4000-8000-00000000f801', 'Governance Target', 'Photographer', 'MT Test', 'Shanghai', 'CN'),
  ('00000000-0000-4000-8000-00000000f802', 'Governance Admin', 'Administrator', 'MT Test', 'Shanghai', 'CN'),
  ('00000000-0000-4000-8000-00000000f803', 'Governance Super', 'Super Admin', 'MT Test', 'Shanghai', 'CN'),
  ('00000000-0000-4000-8000-00000000f804', 'Peer Super', 'Super Admin', 'MT Test', 'Shanghai', 'CN'),
  ('00000000-0000-4000-8000-00000000f805', 'Suspended Member', null, null, null, null),
  ('00000000-0000-4000-8000-00000000f806', 'System Identity', null, null, null, null),
  ('00000000-0000-4000-8000-00000000f807', 'Inactive Admin', null, null, null, null);

insert into public.user_roles (user_id, role, assigned_by, reason)
select id, 'user'::public.role_code, null, 'Admin Users acceptance baseline'
from public.users
where id between '00000000-0000-4000-8000-00000000f801'::uuid
  and '00000000-0000-4000-8000-00000000f808'::uuid;
insert into public.user_roles (user_id, role, assigned_by, reason) values
  ('00000000-0000-4000-8000-00000000f802', 'admin', '00000000-0000-4000-8000-00000000f803', 'Admin Users acceptance'),
  ('00000000-0000-4000-8000-00000000f803', 'super_admin', null, 'Admin Users acceptance'),
  ('00000000-0000-4000-8000-00000000f804', 'super_admin', '00000000-0000-4000-8000-00000000f803', 'Admin Users acceptance'),
  ('00000000-0000-4000-8000-00000000f806', 'super_admin', null, 'System identity boundary'),
  ('00000000-0000-4000-8000-00000000f807', 'admin', '00000000-0000-4000-8000-00000000f803', 'Inactive actor boundary');

insert into public.folders (id, owner_user_id, name, sort_order, is_system)
values (
  '00000000-0000-4000-8000-00000000f811',
  '00000000-0000-4000-8000-00000000f801', 'Inbox', 0, true
);
insert into public.images (
  id, owner_user_id, folder_id, processing_status, workflow_status,
  publication_status, original_filename
) values (
  '00000000-0000-4000-8000-00000000f821',
  '00000000-0000-4000-8000-00000000f801',
  '00000000-0000-4000-8000-00000000f811',
  'ready', 'draft', 'never_published', 'admin-users-fixture.jpg'
);

set local role authenticated;
do $$
declare
  payload jsonb;
begin
  perform pg_temp.set_admin_users_claims('00000000-0000-4000-8000-00000000f808', 'aal2');
  begin
    perform public.admin_list_users('all', 'all', '', 'updated_desc', 30, 0);
    raise exception 'ordinary user accessed Admin Users';
  exception when insufficient_privilege then null;
  end;

  perform pg_temp.set_admin_users_claims('00000000-0000-4000-8000-00000000f802', 'aal1');
  begin
    perform public.admin_list_users('all', 'all', '', 'updated_desc', 30, 0);
    raise exception 'Admin AAL1 accessed Admin Users';
  exception when insufficient_privilege then null;
  end;

  perform pg_temp.set_admin_users_claims('00000000-0000-4000-8000-00000000f802', 'aal2', true);
  begin
    perform public.admin_list_users('all', 'all', '', 'updated_desc', 30, 0);
    raise exception 'recovery session accessed Admin Users';
  exception when insufficient_privilege then null;
  end;

  perform pg_temp.set_admin_users_claims('00000000-0000-4000-8000-00000000f807', 'aal2');
  begin
    perform public.admin_list_users('all', 'all', '', 'updated_desc', 30, 0);
    raise exception 'inactive Admin accessed Admin Users';
  exception when insufficient_privilege then null;
  end;

  perform pg_temp.set_admin_users_claims('00000000-0000-4000-8000-00000000f806', 'aal2');
  begin
    perform public.admin_list_users('all', 'all', '', 'updated_desc', 30, 0);
    raise exception 'system actor accessed Admin Users';
  exception when insufficient_privilege then null;
  end;

  perform pg_temp.set_admin_users_claims('00000000-0000-4000-8000-00000000f802', 'aal2');
  payload := public.admin_list_users('all', 'all', '00000000-0000-4000-8000-00000000f8', 'last_login_desc', 5, 0);
  if payload ? 'error'
     or jsonb_array_length(payload -> 'items') <> 5
     or (payload #>> '{pagination,total}')::integer <> 8
     or payload #>> '{actor,can_manage_roles}' <> 'false'
     or (payload #>> '{counts,statuses,active}')::integer < 6
     or (payload #>> '{counts,roles,super_admin}')::integer < 3 then
    raise exception 'Admin Users list envelope is invalid: %', payload;
  end if;

  payload := public.admin_list_users('active', 'user', 'Governance Target', 'email_asc', 30, 0);
  if jsonb_array_length(payload -> 'items') <> 1
     or payload #>> '{items,0,id}' <> '00000000-0000-4000-8000-00000000f801'
     or payload #>> '{items,0,profile,user_id}' <> '00000000-0000-4000-8000-00000000f801'
     or payload #>> '{items,0,mfa_status}' <> 'unavailable'
     or payload #>> '{items,0,sessions,provider_action_required}' <> 'true'
     or payload #>> '{items,0,storage,quota_status}' <> 'unavailable'
     or payload #>> '{items,0,image_counts,total}' <> '1'
     or payload #>> '{items,0,image_counts,draft}' <> '1'
     or (payload -> 'items' -> 0) ? 'auth_subject' then
    raise exception 'Admin Users list DTO is invalid: %', payload;
  end if;

  payload := public.admin_list_users('active', 'user', 'users-member@example.test', 'email_asc', 30, 0);
  if jsonb_array_length(payload -> 'items') <> 1
     or payload #>> '{items,0,id}' <> '00000000-0000-4000-8000-00000000f808'
     or payload #>> '{items,0,profile,user_id}' <> '00000000-0000-4000-8000-00000000f808'
     or payload #>> '{items,0,profile,display_name}' <> 'users-member'
     or payload #>> '{items,0,profile,availability_status}' <> 'unavailable' then
    raise exception 'profile-less Admin Users summary is invalid: %', payload;
  end if;

  payload := public.admin_get_user('00000000-0000-4000-8000-00000000f801');
  if payload ? 'error'
     or payload #>> '{user,id}' <> '00000000-0000-4000-8000-00000000f801'
     or payload #>> '{user,profile,user_id}' <> '00000000-0000-4000-8000-00000000f801'
     or payload #>> '{user,recent_images,0,owner_user_id}' <> '00000000-0000-4000-8000-00000000f801'
     or payload #>> '{user,recent_images,0,id}' <> '00000000-0000-4000-8000-00000000f821'
     or jsonb_array_length(payload #> '{user,governance_actions}') <> 0
     or jsonb_array_length(payload #> '{user,audit_timeline}') <> 0 then
    raise exception 'Admin Users detail DTO is invalid: %', payload;
  end if;
end
$$;
reset role;

select 'admin_users_database_role_aal_boundary=yes';
select 'admin_users_database_list_detail=yes';

set local role authenticated;
do $$
declare
  payload jsonb;
  replay jsonb;
begin
  perform pg_temp.set_admin_users_claims('00000000-0000-4000-8000-00000000f802', 'aal2');
  payload := public.admin_govern_user(
    '00000000-0000-4000-8000-00000000f801', 1, 'grant_role', 'reviewer',
    'operational_need', '00000000-0000-4000-8000-00000000f861'
  );
  if payload #>> '{error,code}' <> 'ADMIN_USER_ROLE_FORBIDDEN' then
    raise exception 'Admin granted a role: %', payload;
  end if;

  payload := public.admin_govern_user(
    '00000000-0000-4000-8000-00000000f804', 1, 'suspend', null,
    'security_review', '00000000-0000-4000-8000-00000000f862'
  );
  if payload #>> '{error,code}' <> 'ADMIN_USER_TARGET_FORBIDDEN' then
    raise exception 'Admin governed a privileged target: %', payload;
  end if;

  payload := public.admin_govern_user(
    '00000000-0000-4000-8000-00000000f801', 1, 'suspend', null,
    'security_review', '00000000-0000-4000-8000-00000000f863'
  );
  if payload ? 'error'
     or payload #>> '{action,target_user_id}' <> '00000000-0000-4000-8000-00000000f801'
     or payload #>> '{user,id}' <> '00000000-0000-4000-8000-00000000f801'
     or payload #>> '{user,account_status}' <> 'suspended'
     or payload #>> '{user,version}' <> '2'
     or payload ->> 'replayed' <> 'false' then
    raise exception 'Suspend result is invalid: %', payload;
  end if;
  replay := public.admin_govern_user(
    '00000000-0000-4000-8000-00000000f801', 1, 'suspend', null,
    'security_review', '00000000-0000-4000-8000-00000000f863'
  );
  if replay ->> 'replayed' <> 'true'
     or replay #>> '{action,id}' <> payload #>> '{action,id}'
     or replay #>> '{user,version}' <> '2' then
    raise exception 'Suspend idempotency replay is unstable: %', replay;
  end if;

  payload := public.admin_govern_user(
    '00000000-0000-4000-8000-00000000f801', 1, 'reactivate', null,
    'investigation_cleared', '00000000-0000-4000-8000-00000000f864'
  );
  if payload #>> '{error,code}' <> 'ADMIN_USER_VERSION_CONFLICT' then
    raise exception 'stale user CAS was accepted: %', payload;
  end if;
  payload := public.admin_govern_user(
    '00000000-0000-4000-8000-00000000f801', 2, 'reactivate', null,
    'investigation_cleared', '00000000-0000-4000-8000-00000000f865'
  );
  if payload #>> '{user,account_status}' <> 'active'
     or payload #>> '{user,version}' <> '3' then
    raise exception 'Reactivate result is invalid: %', payload;
  end if;

  payload := public.admin_govern_user(
    '00000000-0000-4000-8000-00000000f801', 3, 'revoke_sessions', null,
    'suspected_compromise', '00000000-0000-4000-8000-00000000f866'
  );
  if payload ? 'error'
     or payload #>> '{action,provider_action_required}' <> 'true'
     or payload #>> '{user,version}' <> '4'
     or payload #>> '{user,account_status}' <> 'active' then
    raise exception 'session intent result is invalid: %', payload;
  end if;

  replay := public.admin_govern_user(
    '00000000-0000-4000-8000-00000000f805', 1, 'revoke_sessions', null,
    'suspected_compromise', '00000000-0000-4000-8000-00000000f866'
  );
  if replay #>> '{error,code}' <> 'ADMIN_USER_IDEMPOTENCY_CONFLICT' then
    raise exception 'cross-target idempotency reuse was accepted: %', replay;
  end if;
end
$$;
reset role;

select 'admin_users_database_account_state_cas=yes';
select 'admin_users_database_idempotency=yes';
select 'admin_users_database_session_intent=yes';

set local role authenticated;
do $$
declare
  payload jsonb;
begin
  perform pg_temp.set_admin_users_claims('00000000-0000-4000-8000-00000000f803', 'aal2');
  payload := public.admin_govern_user(
    '00000000-0000-4000-8000-00000000f801', 4, 'grant_role', 'reviewer',
    'operational_need', '00000000-0000-4000-8000-00000000f867'
  );
  if payload ? 'error'
     or payload #>> '{user,version}' <> '5'
     or not (payload #> '{user,roles}') @> '["reviewer"]'::jsonb then
    raise exception 'Super Admin role grant failed: %', payload;
  end if;
  payload := public.admin_govern_user(
    '00000000-0000-4000-8000-00000000f801', 5, 'revoke_role', 'reviewer',
    'access_review', '00000000-0000-4000-8000-00000000f868'
  );
  if payload ? 'error'
     or payload #>> '{user,version}' <> '6'
     or (payload #> '{user,roles}') @> '["reviewer"]'::jsonb then
    raise exception 'Super Admin role revoke failed: %', payload;
  end if;
  payload := public.admin_govern_user(
    '00000000-0000-4000-8000-00000000f801', 6, 'revoke_role', 'user',
    'access_review', '00000000-0000-4000-8000-00000000f869'
  );
  if payload #>> '{error,code}' <> 'ADMIN_USER_ROLE_FORBIDDEN' then
    raise exception 'baseline user role was revoked: %', payload;
  end if;
  payload := public.admin_govern_user(
    '00000000-0000-4000-8000-00000000f805', 1, 'grant_role', 'admin',
    'operational_need', '00000000-0000-4000-8000-00000000f86a'
  );
  if payload #>> '{error,code}' <> 'ADMIN_USER_STATE_CONFLICT' then
    raise exception 'privileged role was granted to inactive account: %', payload;
  end if;
  payload := public.admin_govern_user(
    '00000000-0000-4000-8000-00000000f803', 1, 'suspend', null,
    'security_review', '00000000-0000-4000-8000-00000000f86b'
  );
  if payload #>> '{error,code}' <> 'ADMIN_USER_SELF_ACTION_FORBIDDEN' then
    raise exception 'self governance was accepted: %', payload;
  end if;
  payload := public.admin_govern_user(
    '00000000-0000-4000-8000-00000000f806', 1, 'suspend', null,
    'security_review', '00000000-0000-4000-8000-00000000f86c'
  );
  if payload #>> '{error,code}' <> 'ADMIN_USER_SYSTEM_IDENTITY' then
    raise exception 'system target governance was accepted: %', payload;
  end if;

  payload := public.admin_govern_user(
    '00000000-0000-4000-8000-00000000f804', 1, 'revoke_role', 'super_admin',
    'access_review', '00000000-0000-4000-8000-00000000f86d'
  );
  if payload ? 'error'
     or (payload #> '{user,roles}') @> '["super_admin"]'::jsonb
     or payload #>> '{user,version}' <> '2' then
    raise exception 'peer Super Admin role governance failed: %', payload;
  end if;
end
$$;
reset role;

do $$
begin
  if (select count(distinct u.id)
      from public.users u
      join public.user_roles role_row on role_row.user_id = u.id
      where u.account_status = 'active'::public.account_status
        and not u.is_system_identity
        and role_row.role = 'super_admin'::public.role_code) < 1 then
    raise exception 'no active non-system Super Admin remains';
  end if;
  if not exists (
    select 1 from public.user_roles
    where user_id = '00000000-0000-4000-8000-00000000f801'
      and role = 'user'::public.role_code
  ) then
    raise exception 'baseline user role was not preserved';
  end if;
end
$$;

select 'admin_users_database_role_governance=yes';
select 'admin_users_database_identity_super_guard=yes';

do $$
declare
  session_notification jsonb;
  failure_audit public.audit_logs%rowtype;
  detail jsonb;
begin
  select notification.payload into session_notification
  from public.notifications notification
  where notification.recipient_user_id = '00000000-0000-4000-8000-00000000f801'
    and notification.type = 'admin_session_revocation_requested'
  order by notification.created_at desc, notification.id
  limit 1;
  if session_notification is null
     or session_notification ->> 'status' <> 'requested'
     or session_notification ->> 'provider_action_required' <> 'true'
     or session_notification ? 'signed_out'
     or session_notification ? 'revoked' then
    raise exception 'session notification overstates provider completion: %', session_notification;
  end if;

  select audit.* into failure_audit
  from public.audit_logs audit
  where audit.target_type = 'user'
    and audit.target_id = '00000000-0000-4000-8000-00000000f801'
    and audit.action = 'admin.user.grant_role_failed'
    and audit.result = 'failure'
  order by audit.created_at desc, audit.id
  limit 1;
  if failure_audit.id is null
     or failure_audit.after_state ->> 'error_code' <> 'ADMIN_USER_ROLE_FORBIDDEN'
     or failure_audit.after_state ? 'email'
     or failure_audit.after_state ? 'auth_subject'
     or failure_audit.after_state ? 'message'
     or failure_audit.after_state ? 'internal_note'
     or failure_audit.after_state ? 'token' then
    raise exception 'controlled failure audit is invalid: %', row_to_json(failure_audit);
  end if;

  perform pg_temp.set_admin_users_claims('00000000-0000-4000-8000-00000000f803', 'aal2');
  detail := public.admin_get_user('00000000-0000-4000-8000-00000000f801');
  if exists (
    select 1 from jsonb_array_elements(detail #> '{user,governance_actions}') action_row
    where action_row ->> 'target_user_id' <> detail #>> '{user,id}'
  ) or exists (
    select 1 from jsonb_array_elements(detail #> '{user,audit_timeline}') audit_row
    where audit_row ->> 'target_type' <> 'user'
       or audit_row ->> 'target_id' <> detail #>> '{user,id}'
       or audit_row ->> 'target_user_id' <> detail #>> '{user,id}'
  ) then
    raise exception 'Admin Users detail contains cross-record history: %', detail;
  end if;
end
$$;

select 'admin_users_database_failure_audit=yes';

do $$
declare
  action_id uuid;
  audit_id uuid;
begin
  select id into action_id from public.user_governance_actions
  where target_user_id = '00000000-0000-4000-8000-00000000f801'
  order by created_at, id limit 1;
  begin
    update public.user_governance_actions set reason_code = 'other'
    where id = action_id;
    raise exception 'user governance action update was accepted';
  exception when others then
    if sqlerrm = 'user governance action update was accepted' then raise; end if;
  end;
  begin
    delete from public.user_governance_actions where id = action_id;
    raise exception 'user governance action delete was accepted';
  exception when others then
    if sqlerrm = 'user governance action delete was accepted' then raise; end if;
  end;

  select id into audit_id from public.audit_logs
  where target_type = 'user'
    and target_id = '00000000-0000-4000-8000-00000000f801'
  order by created_at, id limit 1;
  begin
    delete from public.audit_logs where id = audit_id;
    raise exception 'user audit delete was accepted';
  exception when others then
    if sqlerrm = 'user audit delete was accepted' then raise; end if;
  end;
end
$$;

select 'admin_users_database_append_only=yes';

rollback;
select 'admin_users_database_fixtures_rolled_back=yes';
"""


def load_dotenv() -> None:
    if not ENV_PATH.exists():
        return
    for raw_line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        os.environ.setdefault(name.strip(), value)


def require_development_environment() -> None:
    if os.environ.get("MT_TEST_ENVIRONMENT") != "development":
        raise RuntimeError(
            "Refusing Admin Users database fixtures without "
            "MT_TEST_ENVIRONMENT=development"
        )
    if os.environ.get("MT_ALLOW_PRODUCTION") == "yes":
        raise RuntimeError(
            "Refusing Admin Users database fixtures while production approval is enabled"
        )
    missing = [
        name
        for name in ("PGHOST", "PGDATABASE", "PGUSER", "PGPASSWORD")
        if not os.environ.get(name)
    ]
    if missing:
        raise RuntimeError(
            f"Missing required database environment variables: {', '.join(missing)}"
        )


def psql_binary() -> str:
    found = shutil.which("psql")
    fallback = Path("/opt/homebrew/opt/libpq/bin/psql")
    if found:
        return found
    if fallback.exists():
        return str(fallback)
    raise RuntimeError("psql is required for the Admin Users database acceptance")


def psql_command() -> list[str]:
    return [
        psql_binary(),
        "--no-psqlrc",
        "--quiet",
        "--no-align",
        "--tuples-only",
        "--set",
        "ON_ERROR_STOP=1",
    ]


def redact_diagnostics(value: str) -> str:
    cleaned = value
    for name in (
        "PGPASSWORD",
        "SUPABASE_SECRET_KEY",
        "SUPABASE_SERVICE_ROLE_KEY",
        "SUPABASE_PUBLISHABLE_KEY",
    ):
        secret = os.environ.get(name, "")
        if secret:
            cleaned = cleaned.replace(secret, "[redacted]")
    return cleaned.strip()[-3000:]


def run_psql(sql: str) -> str:
    completed = subprocess.run(
        psql_command(),
        input=sql,
        cwd=ROOT,
        env=os.environ.copy(),
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )
    if completed.returncode:
        detail = redact_diagnostics(completed.stderr)
        raise RuntimeError(
            "Admin Users database acceptance failed"
            + (f":\n{detail}" if detail else "")
        )
    return completed.stdout


def sql_values(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{value}'" for value in values)


def assert_fixtures_absent() -> None:
    fixture_count = run_psql(
        f"""
        select (
          (select count(*) from public.users where id in ({sql_values(USER_IDS)}))
          + (select count(*) from public.folders where id in ({sql_values(FOLDER_IDS)}))
          + (select count(*) from public.images where id in ({sql_values(IMAGE_IDS)}))
          + (select count(*) from public.user_governance_actions
             where target_user_id in ({sql_values(USER_IDS)}))
          + (select count(*) from public.notifications
             where recipient_user_id in ({sql_values(USER_IDS)})
               and type like 'admin_%')
          + (select count(*) from public.audit_logs
             where target_type = 'user' and target_id in ({sql_values(USER_IDS)}))
        );
        """
    ).strip()
    if fixture_count != "0":
        raise RuntimeError("Admin Users database fixture UUIDs remain after rollback")


def main() -> None:
    load_dotenv()
    require_development_environment()
    output = run_psql(SQL)
    lines = {line.strip() for line in output.splitlines() if line.strip()}
    missing = [marker for marker in EXPECTED_MARKERS if marker not in lines]
    if missing:
        raise RuntimeError(
            f"Admin Users database markers are missing: {', '.join(missing)}"
        )
    assert_fixtures_absent()
    for marker in EXPECTED_MARKERS:
        print(marker)
    print("admin_users_database_fixtures_absent=yes")


if __name__ == "__main__":
    main()
