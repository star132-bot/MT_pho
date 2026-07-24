#!/usr/bin/env python3
"""Development-only, rollback-only profile avatar database acceptance."""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess


ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT / ".env"

USER_IDS = (
    "00000000-0000-4000-8000-00000000fa01",
    "00000000-0000-4000-8000-00000000fa02",
    "00000000-0000-4000-8000-00000000fa03",
    "00000000-0000-4000-8000-00000000fa04",
    "00000000-0000-4000-8000-00000000fa05",
)
OBJECT_IDS = (
    "00000000-0000-4000-8000-00000000fb01",
    "00000000-0000-4000-8000-00000000fb02",
)

EXPECTED_MARKERS = (
    "profile_avatar_database_function_acl=yes",
    "profile_avatar_database_table_acl=yes",
    "profile_avatar_database_storage_contract=yes",
    "profile_avatar_database_create_validation=yes",
    "profile_avatar_database_cross_owner=yes",
    "profile_avatar_database_incomplete_gate=yes",
    "profile_avatar_database_complete_stable_metadata=yes",
    "profile_avatar_database_public_boundary=yes",
    "profile_avatar_database_cancel_remove=yes",
    "profile_avatar_database_identity_guards=yes",
    "profile_avatar_database_fixtures_rolled_back=yes",
)


SQL = r"""
\set ON_ERROR_STOP on

begin;
select pg_advisory_xact_lock(hashtextextended('mt-profile-avatar-database-test', 0));
set local lock_timeout = '10s';
set local statement_timeout = '90s';

do $$
declare
  proc_row record;
  anon_role oid := (select oid from pg_roles where rolname = 'anon');
  authenticated_role oid := (select oid from pg_roles where rolname = 'authenticated');
  service_role_id oid := (select oid from pg_roles where rolname = 'service_role');
begin
  if anon_role is null or authenticated_role is null or service_role_id is null then
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
        'public.is_public_profile_avatar_object(text,text,text)'::regprocedure,
        'public.get_public_creator_avatar(text)'::regprocedure
      ) as allow_anon
    from pg_proc p
    where p.oid in (
      'public.is_profile_avatar_upload_target(text,text)'::regprocedure,
      'public.is_public_profile_avatar_object(text,text,text)'::regprocedure,
      'public.create_my_profile_avatar_upload(text,bigint,integer,integer)'::regprocedure,
      'public.complete_my_profile_avatar_upload(uuid)'::regprocedure,
      'public.cancel_my_profile_avatar_upload(uuid)'::regprocedure,
      'public.remove_my_profile_avatar()'::regprocedure,
      'public.get_public_creator_avatar(text)'::regprocedure
    )
  loop
    if not proc_row.prosecdef then
      raise exception '% is not SECURITY DEFINER', proc_row.identity;
    end if;
    if not coalesce(proc_row.proconfig, '{}'::text[]) @> array['search_path=""']::text[] then
      raise exception '% does not pin an empty search_path', proc_row.identity;
    end if;
    if not has_function_privilege('authenticated', proc_row.oid, 'EXECUTE') then
      raise exception '% is not executable by authenticated', proc_row.identity;
    end if;
    if has_function_privilege('anon', proc_row.oid, 'EXECUTE') <> proc_row.allow_anon then
      raise exception '% has an invalid anon EXECUTE grant', proc_row.identity;
    end if;
    if has_function_privilege('service_role', proc_row.oid, 'EXECUTE') then
      raise exception '% is executable by service_role', proc_row.identity;
    end if;
    if exists (
      select 1
      from aclexplode(coalesce(
        (select function_row.proacl from pg_proc function_row where function_row.oid = proc_row.oid),
        acldefault('f', proc_row.proowner)
      )) privilege
      where privilege.privilege_type = 'EXECUTE'
        and not (
          privilege.grantee = proc_row.proowner
          or privilege.grantee = authenticated_role
          or (proc_row.allow_anon and privilege.grantee = anon_role)
        )
    ) then
      raise exception '% grants EXECUTE outside its exact allowlist', proc_row.identity;
    end if;
  end loop;

  if (select count(*) from pg_proc p where p.oid in (
    'public.is_profile_avatar_upload_target(text,text)'::regprocedure,
    'public.is_public_profile_avatar_object(text,text,text)'::regprocedure,
    'public.create_my_profile_avatar_upload(text,bigint,integer,integer)'::regprocedure,
    'public.complete_my_profile_avatar_upload(uuid)'::regprocedure,
    'public.cancel_my_profile_avatar_upload(uuid)'::regprocedure,
    'public.remove_my_profile_avatar()'::regprocedure,
    'public.get_public_creator_avatar(text)'::regprocedure
  )) <> 7 then
    raise exception 'Profile avatar function metadata is incomplete';
  end if;
  if has_function_privilege(
       'authenticated',
       'public.require_creator_profile_user()',
       'EXECUTE'
     ) then
    raise exception 'authenticated can execute the private creator identity helper';
  end if;
end
$$;

select 'profile_avatar_database_function_acl=yes';

do $$
declare
  table_owner oid;
  authenticated_role oid := (select oid from pg_roles where rolname = 'authenticated');
begin
  select relation.relowner
  into table_owner
  from pg_class relation
  where relation.oid = 'public.profile_avatar_upload_intents'::regclass;

  if table_owner is null
     or not (select relation.relrowsecurity from pg_class relation
             where relation.oid = 'public.profile_avatar_upload_intents'::regclass)
     or not has_table_privilege(
       'authenticated', 'public.profile_avatar_upload_intents', 'SELECT'
     )
     or has_table_privilege(
       'authenticated', 'public.profile_avatar_upload_intents', 'INSERT'
     )
     or has_table_privilege(
       'authenticated', 'public.profile_avatar_upload_intents', 'UPDATE'
     )
     or has_table_privilege(
       'authenticated', 'public.profile_avatar_upload_intents', 'DELETE'
     )
     or has_table_privilege('anon', 'public.profile_avatar_upload_intents', 'SELECT')
     or has_table_privilege('service_role', 'public.profile_avatar_upload_intents', 'SELECT')
     or has_table_privilege('authenticated', 'public.user_profiles', 'UPDATE') then
    raise exception 'Profile avatar table privileges are broader than the owner-read contract';
  end if;

  if exists (
    select 1
    from pg_class relation
    cross join lateral aclexplode(coalesce(
      relation.relacl,
      acldefault('r', relation.relowner)
    )) privilege
    where relation.oid = 'public.profile_avatar_upload_intents'::regclass
      and not (
        privilege.grantee = table_owner
        or (
          privilege.grantee = authenticated_role
          and privilege.privilege_type = 'SELECT'
        )
      )
  ) then
    raise exception 'profile_avatar_upload_intents ACL contains an unexpected grantee or privilege';
  end if;

  if not exists (
    select 1
    from pg_policies policy
    where policy.schemaname = 'public'
      and policy.tablename = 'profile_avatar_upload_intents'
      and policy.policyname = 'profile_avatar_upload_intents_owner_select'
      and policy.cmd = 'SELECT'
      and policy.roles = array['authenticated'::name]
      and position('current_app_user_id' in policy.qual) > 0
  ) then
    raise exception 'Profile avatar owner SELECT policy is missing or over-broad';
  end if;
end
$$;

select 'profile_avatar_database_table_acl=yes';

do $$
declare
  bucket_row storage.buckets%rowtype;
begin
  select bucket.* into bucket_row
  from storage.buckets bucket
  where bucket.id = 'profile-avatars';
  if bucket_row.id is null
     or bucket_row.public
     or bucket_row.file_size_limit <> 1048576
     or bucket_row.allowed_mime_types is distinct from array['image/jpeg']::text[] then
    raise exception 'profile-avatars bucket is not private or has unsafe upload limits';
  end if;

  if not exists (
       select 1 from pg_policies policy
       where policy.schemaname = 'storage'
         and policy.tablename = 'objects'
         and policy.policyname = 'profile_avatar_owner_insert'
         and policy.cmd = 'INSERT'
         and policy.roles = array['authenticated'::name]
         and position('is_profile_avatar_upload_target' in policy.with_check) > 0
     )
     or not exists (
       select 1 from pg_policies policy
       where policy.schemaname = 'storage'
         and policy.tablename = 'objects'
         and policy.policyname = 'profile_avatar_owner_select'
         and policy.cmd = 'SELECT'
         and policy.roles = array['authenticated'::name]
         and position('auth.uid' in policy.qual) > 0
     )
     or not exists (
       select 1 from pg_policies policy
       where policy.schemaname = 'storage'
         and policy.tablename = 'objects'
         and policy.policyname = 'profile_avatar_owner_delete'
         and policy.cmd = 'DELETE'
         and policy.roles = array['authenticated'::name]
         and position('auth.uid' in policy.qual) > 0
     )
     or not exists (
       select 1 from pg_policies policy
       where policy.schemaname = 'storage'
         and policy.tablename = 'objects'
         and policy.policyname = 'profile_avatar_public_current_select'
         and policy.cmd = 'SELECT'
         and policy.roles @> array['anon'::name, 'authenticated'::name]
         and cardinality(policy.roles) = 2
         and position('is_public_profile_avatar_object' in policy.qual) > 0
     ) then
    raise exception 'Profile avatar Storage policies are missing or over-broad';
  end if;
end
$$;

select 'profile_avatar_database_storage_contract=yes';

do $$
begin
  if exists (
       select 1 from public.users
       where id in (
         '00000000-0000-4000-8000-00000000fa01',
         '00000000-0000-4000-8000-00000000fa02',
         '00000000-0000-4000-8000-00000000fa03',
         '00000000-0000-4000-8000-00000000fa04',
         '00000000-0000-4000-8000-00000000fa05'
       )
     )
     or exists (
       select 1 from public.profile_avatar_upload_intents
       where owner_user_id in (
         '00000000-0000-4000-8000-00000000fa01',
         '00000000-0000-4000-8000-00000000fa02',
         '00000000-0000-4000-8000-00000000fa03',
         '00000000-0000-4000-8000-00000000fa04',
         '00000000-0000-4000-8000-00000000fa05'
       )
     )
     or exists (
       select 1 from storage.objects
       where id in (
         '00000000-0000-4000-8000-00000000fb01',
         '00000000-0000-4000-8000-00000000fb02'
       )
     ) then
    raise exception 'Fixed profile avatar database fixtures already exist';
  end if;
end
$$;

create function pg_temp.set_profile_avatar_claims(
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

create function pg_temp.assert_profile_avatar_mutations_rejected(context_label text)
returns void
language plpgsql
as $$
begin
  begin
    perform public.create_my_profile_avatar_upload('image/jpeg', 734, 512, 512);
    raise exception '% created a profile avatar upload', context_label;
  exception when sqlstate '42501' then
    null;
  end;
  begin
    perform public.complete_my_profile_avatar_upload(
      '00000000-0000-4000-8000-00000000faff'
    );
    raise exception '% completed a profile avatar upload', context_label;
  exception when sqlstate '42501' then
    null;
  end;
  begin
    perform public.cancel_my_profile_avatar_upload(
      '00000000-0000-4000-8000-00000000faff'
    );
    raise exception '% canceled a profile avatar upload', context_label;
  exception when sqlstate '42501' then
    null;
  end;
  begin
    perform public.remove_my_profile_avatar();
    raise exception '% removed a profile avatar', context_label;
  exception when sqlstate '42501' then
    null;
  end;
end
$$;
grant execute on function pg_temp.assert_profile_avatar_mutations_rejected(text)
  to authenticated;

insert into public.users (
  id, auth_subject, email, email_verified_at, account_status
) values
  ('00000000-0000-4000-8000-00000000fa01', '00000000-0000-4000-8000-00000000fa01', 'avatar-owner-a@example.test', now(), 'active'),
  ('00000000-0000-4000-8000-00000000fa02', '00000000-0000-4000-8000-00000000fa02', 'avatar-owner-b@example.test', now(), 'active'),
  ('00000000-0000-4000-8000-00000000fa03', '00000000-0000-4000-8000-00000000fa03', 'avatar-inactive@example.test', now(), 'suspended'),
  ('00000000-0000-4000-8000-00000000fa04', '00000000-0000-4000-8000-00000000fa04', 'avatar-recovery@example.test', now(), 'active'),
  ('00000000-0000-4000-8000-00000000fa05', '00000000-0000-4000-8000-00000000fa05', 'avatar-admin@example.test', now(), 'active');

insert into public.user_profiles (
  user_id, display_name, public_slug, public_fields
) values
  ('00000000-0000-4000-8000-00000000fa01', 'Avatar Owner A', 'avatar-owner-a', '{"avatar_url":false}'),
  ('00000000-0000-4000-8000-00000000fa02', 'Avatar Owner B', 'avatar-owner-b', '{"avatar_url":false}'),
  ('00000000-0000-4000-8000-00000000fa03', 'Avatar Inactive', 'avatar-inactive', '{"avatar_url":false}'),
  ('00000000-0000-4000-8000-00000000fa04', 'Avatar Recovery', 'avatar-recovery', '{"avatar_url":false}'),
  ('00000000-0000-4000-8000-00000000fa05', 'Avatar Admin', 'avatar-admin', '{"avatar_url":false}');

insert into public.user_roles (user_id, role, reason) values
  ('00000000-0000-4000-8000-00000000fa01', 'user', 'Profile avatar database acceptance'),
  ('00000000-0000-4000-8000-00000000fa02', 'user', 'Profile avatar database acceptance'),
  ('00000000-0000-4000-8000-00000000fa03', 'user', 'Profile avatar database acceptance'),
  ('00000000-0000-4000-8000-00000000fa04', 'user', 'Profile avatar database acceptance'),
  ('00000000-0000-4000-8000-00000000fa05', 'user', 'Profile avatar database acceptance'),
  ('00000000-0000-4000-8000-00000000fa05', 'admin', 'Profile avatar AAL2 acceptance');

select pg_temp.set_profile_avatar_claims('00000000-0000-4000-8000-00000000fa01');
set local role authenticated;
do $$
declare
  created jsonb;
  invalid_mime jsonb;
  invalid_size jsonb;
  intent_row public.profile_avatar_upload_intents%rowtype;
begin
  created := public.create_my_profile_avatar_upload(' image/jpeg ', 734, 512, 512);
  select intent.* into intent_row
  from public.profile_avatar_upload_intents intent
  where intent.id = (created ->> 'upload_id')::uuid;

  if (select count(*) from jsonb_object_keys(created)) <> 9
     or created ->> 'storage_bucket' <> 'profile-avatars'
     or created ->> 'storage_key' <> (
       '00000000-0000-4000-8000-00000000fa01/' ||
       (created ->> 'upload_id') || '/avatar.jpg'
     )
     or created ->> 'mime_type' <> 'image/jpeg'
     or created ->> 'byte_size' <> '734'
     or created ->> 'width' <> '512'
     or created ->> 'height' <> '512'
     or jsonb_array_length(created -> 'superseded_uploads') <> 0
     or intent_row.id is null
     or intent_row.owner_user_id <> '00000000-0000-4000-8000-00000000fa01'
     or intent_row.status <> 'issued'
     or intent_row.storage_key <> created ->> 'storage_key'
     or intent_row.expires_at <= now()
     or not public.is_profile_avatar_upload_target(
       created ->> 'storage_bucket', created ->> 'storage_key'
     )
     or public.is_profile_avatar_upload_target(
       created ->> 'storage_bucket', created ->> 'storage_key' || '.other'
     ) then
    raise exception 'Active owner did not receive one strict owner-bound upload intent: %', created;
  end if;

  invalid_mime := public.create_my_profile_avatar_upload('image/png', 734, 512, 512);
  invalid_size := public.create_my_profile_avatar_upload('image/jpeg', 1048577, 512, 512);
  if invalid_mime #>> '{error,code}' <> 'PROFILE_AVATAR_UPLOAD_INVALID'
     or invalid_size #>> '{error,code}' <> 'PROFILE_AVATAR_UPLOAD_INVALID'
     or (select count(*) from public.profile_avatar_upload_intents
         where status = 'issued') <> 1 then
    raise exception 'Invalid profile avatar MIME or size changed upload state';
  end if;
end
$$;
reset role;

select set_config(
  'mt.test.profile_avatar_intent_id',
  (select intent.id::text from public.profile_avatar_upload_intents intent
   where intent.owner_user_id = '00000000-0000-4000-8000-00000000fa01'
     and intent.status = 'issued'),
  true
);
select set_config(
  'mt.test.profile_avatar_storage_key',
  (select intent.storage_key from public.profile_avatar_upload_intents intent
   where intent.owner_user_id = '00000000-0000-4000-8000-00000000fa01'
     and intent.status = 'issued'),
  true
);

select 'profile_avatar_database_create_validation=yes';

select pg_temp.set_profile_avatar_claims('00000000-0000-4000-8000-00000000fa02');
set local role authenticated;
do $$
declare
  completed jsonb;
  canceled jsonb;
  removed jsonb;
  cross_owner_insert_blocked boolean := false;
begin
  if (select count(*) from public.profile_avatar_upload_intents) <> 0
     or public.is_profile_avatar_upload_target(
       'profile-avatars', current_setting('mt.test.profile_avatar_storage_key')
     ) then
    raise exception 'Owner B can see or authorize Owner A upload intent';
  end if;

  completed := public.complete_my_profile_avatar_upload(
    current_setting('mt.test.profile_avatar_intent_id')::uuid
  );
  canceled := public.cancel_my_profile_avatar_upload(
    current_setting('mt.test.profile_avatar_intent_id')::uuid
  );
  removed := public.remove_my_profile_avatar();
  if completed #>> '{error,code}' <> 'PROFILE_AVATAR_UPLOAD_NOT_FOUND'
     or canceled #>> '{error,code}' <> 'PROFILE_AVATAR_UPLOAD_NOT_FOUND'
     or removed ->> 'removed' <> 'false'
     or jsonb_array_length(removed -> 'canceled_uploads') <> 0 then
    raise exception 'Owner B crossed an Owner A profile avatar RPC boundary';
  end if;

  begin
    insert into storage.objects (id, bucket_id, name, owner_id, metadata) values (
      '00000000-0000-4000-8000-00000000fb02',
      'profile-avatars',
      current_setting('mt.test.profile_avatar_storage_key'),
      '00000000-0000-4000-8000-00000000fa02',
      '{"mimetype":"image/jpeg","size":734}'
    );
  exception when sqlstate '42501' then
    cross_owner_insert_blocked := true;
  end;
  if not cross_owner_insert_blocked then
    raise exception 'Owner B inserted a Storage object into Owner A avatar path';
  end if;
end
$$;
reset role;

do $$
begin
  if (select status from public.profile_avatar_upload_intents
      where id = current_setting('mt.test.profile_avatar_intent_id')::uuid) <> 'issued'
     or (select avatar_storage_key from public.user_profiles
         where user_id = '00000000-0000-4000-8000-00000000fa01') is not null
     or exists (
       select 1 from storage.objects
       where id = '00000000-0000-4000-8000-00000000fb02'
     ) then
    raise exception 'Cross-owner attempts changed Owner A profile avatar state';
  end if;
end
$$;

select 'profile_avatar_database_cross_owner=yes';

select pg_temp.set_profile_avatar_claims('00000000-0000-4000-8000-00000000fa01');
set local role authenticated;
do $$
declare
  completed jsonb;
begin
  completed := public.complete_my_profile_avatar_upload(
    current_setting('mt.test.profile_avatar_intent_id')::uuid
  );
  if completed #>> '{error,code}' <> 'PROFILE_AVATAR_UPLOAD_INCOMPLETE'
     or (select status from public.profile_avatar_upload_intents
         where id = current_setting('mt.test.profile_avatar_intent_id')::uuid) <> 'issued' then
    raise exception 'Profile avatar completed before its Storage object existed';
  end if;
end
$$;
reset role;

select 'profile_avatar_database_incomplete_gate=yes';

select pg_temp.set_profile_avatar_claims('00000000-0000-4000-8000-00000000fa01');
set local role authenticated;
insert into storage.objects (id, bucket_id, name, owner_id, metadata) values (
  '00000000-0000-4000-8000-00000000fb01',
  'profile-avatars',
  current_setting('mt.test.profile_avatar_storage_key'),
  '00000000-0000-4000-8000-00000000fa01',
  '{"mimetype":"image/jpeg","size":734}'
);
do $$
declare
  completed jsonb;
  replayed jsonb;
begin
  if (select count(*) from storage.objects
      where id = '00000000-0000-4000-8000-00000000fb01') <> 1 then
    raise exception 'Authenticated owner could not read its uploaded avatar object';
  end if;

  completed := public.complete_my_profile_avatar_upload(
    current_setting('mt.test.profile_avatar_intent_id')::uuid
  );
  replayed := public.complete_my_profile_avatar_upload(
    current_setting('mt.test.profile_avatar_intent_id')::uuid
  );
  if completed ->> 'replayed' <> 'false'
     or replayed ->> 'replayed' <> 'true'
     or completed #>> '{avatar,storage_bucket}' <> 'profile-avatars'
     or completed #>> '{avatar,storage_key}' <>
        current_setting('mt.test.profile_avatar_storage_key')
     or completed #>> '{avatar,mime_type}' <> 'image/jpeg'
     or completed #>> '{avatar,byte_size}' <> '734'
     or completed #>> '{avatar,width}' <> '512'
     or completed #>> '{avatar,height}' <> '512'
     or completed -> 'previous_avatar' <> 'null'::jsonb
     or public.is_profile_avatar_upload_target(
       'profile-avatars', current_setting('mt.test.profile_avatar_storage_key')
     ) then
    raise exception 'Completed profile avatar response or replay contract is invalid: %', completed;
  end if;
end
$$;
reset role;

do $$
declare
  profile_row public.user_profiles%rowtype;
  intent_row public.profile_avatar_upload_intents%rowtype;
begin
  select profile.* into profile_row
  from public.user_profiles profile
  where profile.user_id = '00000000-0000-4000-8000-00000000fa01';
  select intent.* into intent_row
  from public.profile_avatar_upload_intents intent
  where intent.id = current_setting('mt.test.profile_avatar_intent_id')::uuid;

  if profile_row.avatar_url is not null
     or profile_row.avatar_storage_bucket <> 'profile-avatars'
     or profile_row.avatar_storage_key <> current_setting('mt.test.profile_avatar_storage_key')
     or profile_row.avatar_mime_type <> 'image/jpeg'
     or profile_row.avatar_byte_size <> 734
     or profile_row.avatar_width <> 512
     or profile_row.avatar_height <> 512
     or profile_row.avatar_updated_at is null
     or intent_row.status <> 'completed'
     or intent_row.completed_at is null
     or intent_row.previous_storage_key is not null then
    raise exception 'Completed avatar did not persist stable metadata with avatar_url cleared';
  end if;
end
$$;

select 'profile_avatar_database_complete_stable_metadata=yes';

set local role anon;
do $$
begin
  if public.get_public_creator_avatar('avatar-owner-a') <> '{}'::jsonb
     or public.is_public_profile_avatar_object(
       'profile-avatars',
       current_setting('mt.test.profile_avatar_storage_key'),
       '00000000-0000-4000-8000-00000000fa01'
     )
     or (select count(*) from storage.objects
         where id = '00000000-0000-4000-8000-00000000fb01') <> 0 then
    raise exception 'Private profile avatar entered anonymous delivery';
  end if;
end
$$;
reset role;

update public.user_profiles
set public_fields = jsonb_set(public_fields, '{avatar_url}', 'true'::jsonb, true)
where user_id = '00000000-0000-4000-8000-00000000fa01';

set local role anon;
do $$
declare
  avatar jsonb := public.get_public_creator_avatar('avatar-owner-a');
begin
  if (select count(*) from jsonb_object_keys(avatar)) <> 8
     or avatar ->> 'owner_user_id' <> '00000000-0000-4000-8000-00000000fa01'
     or avatar ->> 'storage_bucket' <> 'profile-avatars'
     or avatar ->> 'storage_key' <> current_setting('mt.test.profile_avatar_storage_key')
     or avatar ->> 'mime_type' <> 'image/jpeg'
     or avatar ->> 'byte_size' <> '734'
     or avatar ->> 'width' <> '512'
     or avatar ->> 'height' <> '512'
     or avatar ->> 'updated_at' is null
     or public.get_public_creator_avatar('avatar-owner-b') <> '{}'::jsonb
     or not public.is_public_profile_avatar_object(
       'profile-avatars',
       current_setting('mt.test.profile_avatar_storage_key'),
       '00000000-0000-4000-8000-00000000fa01'
     )
     or public.is_public_profile_avatar_object(
       'profile-avatars',
       current_setting('mt.test.profile_avatar_storage_key') || '.other',
       '00000000-0000-4000-8000-00000000fa01'
     )
     or public.is_public_profile_avatar_object(
       'profile-avatars',
       current_setting('mt.test.profile_avatar_storage_key'),
       '00000000-0000-4000-8000-00000000fa02'
     )
     or (select count(*) from storage.objects
         where id = '00000000-0000-4000-8000-00000000fb01') <> 1 then
    raise exception 'Anonymous avatar delivery is not limited to the exact active public object: %', avatar;
  end if;
end
$$;
reset role;

update public.users
set account_status = 'suspended'
where id = '00000000-0000-4000-8000-00000000fa01';
set local role anon;
do $$
begin
  if public.get_public_creator_avatar('avatar-owner-a') <> '{}'::jsonb
     or (select count(*) from storage.objects
         where id = '00000000-0000-4000-8000-00000000fb01') <> 0 then
    raise exception 'Inactive account retained public avatar delivery';
  end if;
end
$$;
reset role;
update public.users
set account_status = 'active'
where id = '00000000-0000-4000-8000-00000000fa01';

select 'profile_avatar_database_public_boundary=yes';

select pg_temp.set_profile_avatar_claims('00000000-0000-4000-8000-00000000fa02');
set local role authenticated;
do $$
begin
  if (select count(*) from storage.objects
      where id = '00000000-0000-4000-8000-00000000fb01') <> 0 then
    raise exception 'Owner B read Owner A private avatar object';
  end if;
end
$$;
reset role;

select pg_temp.set_profile_avatar_claims('00000000-0000-4000-8000-00000000fa01');
set local role authenticated;
do $$
declare
  cancel_created jsonb;
  canceled jsonb;
  pending_created jsonb;
  removed jsonb;
begin
  cancel_created := public.create_my_profile_avatar_upload('image/jpeg', 735, 512, 512);
  canceled := public.cancel_my_profile_avatar_upload(
    (cancel_created ->> 'upload_id')::uuid
  );
  if canceled ->> 'canceled' <> 'true'
     or canceled ->> 'status' <> 'canceled'
     or canceled #>> '{upload,upload_id}' <> cancel_created ->> 'upload_id'
     or canceled #>> '{upload,storage_key}' <> cancel_created ->> 'storage_key'
     or (select status from public.profile_avatar_upload_intents
         where id = (cancel_created ->> 'upload_id')::uuid) <> 'canceled' then
    raise exception 'Owner could not cancel its pending profile avatar upload';
  end if;

  pending_created := public.create_my_profile_avatar_upload('image/jpeg', 736, 512, 512);
  removed := public.remove_my_profile_avatar();
  if removed ->> 'removed' <> 'true'
     or removed #>> '{previous_avatar,storage_key}' <>
        current_setting('mt.test.profile_avatar_storage_key')
     or jsonb_array_length(removed -> 'canceled_uploads') <> 1
     or removed #>> '{canceled_uploads,0,upload_id}' <> pending_created ->> 'upload_id'
     or removed #>> '{canceled_uploads,0,storage_key}' <> pending_created ->> 'storage_key'
     or (select status from public.profile_avatar_upload_intents
         where id = (pending_created ->> 'upload_id')::uuid) <> 'canceled' then
    raise exception 'Profile avatar removal did not return active and pending cleanup coordinates: %', removed;
  end if;
end
$$;
reset role;

do $$
declare
  profile_row public.user_profiles%rowtype;
begin
  select profile.* into profile_row
  from public.user_profiles profile
  where profile.user_id = '00000000-0000-4000-8000-00000000fa01';
  if profile_row.avatar_url is not null
     or profile_row.avatar_storage_bucket is not null
     or profile_row.avatar_storage_key is not null
     or profile_row.avatar_mime_type is not null
     or profile_row.avatar_byte_size is not null
     or profile_row.avatar_width is not null
     or profile_row.avatar_height is not null
     or (select count(*) from public.profile_avatar_upload_intents
         where owner_user_id = '00000000-0000-4000-8000-00000000fa01'
           and status = 'completed') <> 1
     or (select count(*) from public.profile_avatar_upload_intents
         where owner_user_id = '00000000-0000-4000-8000-00000000fa01'
           and status = 'canceled') <> 2 then
    raise exception 'Profile avatar removal did not clear stable metadata or pending state';
  end if;
end
$$;

set local role anon;
do $$
begin
  if public.get_public_creator_avatar('avatar-owner-a') <> '{}'::jsonb then
    raise exception 'Removed avatar remained publicly readable';
  end if;
end
$$;
reset role;

select 'profile_avatar_database_cancel_remove=yes';

select pg_temp.set_profile_avatar_claims(
  '00000000-0000-4000-8000-00000000fa05', 'aal1', false
);
set local role authenticated;
select pg_temp.assert_profile_avatar_mutations_rejected('Admin AAL1');
reset role;

select pg_temp.set_profile_avatar_claims(
  '00000000-0000-4000-8000-00000000fa04', 'aal1', true
);
set local role authenticated;
select pg_temp.assert_profile_avatar_mutations_rejected('recovery session');
reset role;

select pg_temp.set_profile_avatar_claims(
  '00000000-0000-4000-8000-00000000fa03', 'aal1', false
);
set local role authenticated;
select pg_temp.assert_profile_avatar_mutations_rejected('inactive account');
reset role;

do $$
begin
  if exists (
    select 1 from public.profile_avatar_upload_intents
    where owner_user_id in (
      '00000000-0000-4000-8000-00000000fa03',
      '00000000-0000-4000-8000-00000000fa04',
      '00000000-0000-4000-8000-00000000fa05'
    )
  ) then
    raise exception 'Rejected identities changed profile avatar upload state';
  end if;
end
$$;

select 'profile_avatar_database_identity_guards=yes';

rollback;
select 'profile_avatar_database_fixtures_rolled_back=yes';
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
            "Refusing profile avatar database fixtures without "
            "MT_TEST_ENVIRONMENT=development"
        )
    if (
        os.environ.get("MT_ALLOW_PRODUCTION") == "yes"
        or os.environ.get("MT_RUNTIME_ENVIRONMENT") == "production"
        or os.environ.get("MT_DEPLOY_ENVIRONMENT") == "production"
    ):
        raise RuntimeError(
            "Refusing profile avatar database fixtures in a production environment"
        )
    missing = [
        name
        for name in ("PGHOST", "PGDATABASE", "PGUSER", "PGPASSWORD")
        if not os.environ.get(name)
    ]
    if missing:
        raise RuntimeError(f"Missing required database environment variables: {', '.join(missing)}")


def psql_binary() -> str:
    found = shutil.which("psql")
    fallback = Path("/opt/homebrew/opt/libpq/bin/psql")
    if found:
        return found
    if fallback.exists():
        return str(fallback)
    raise RuntimeError("psql is required for the profile avatar database acceptance")


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
        timeout=120,
        check=False,
    )
    if completed.returncode:
        detail = redact_diagnostics(completed.stderr)
        raise RuntimeError(
            "Profile avatar database acceptance failed"
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
          + (select count(*) from public.user_profiles
             where user_id in ({sql_values(USER_IDS)}))
          + (select count(*) from public.user_roles
             where user_id in ({sql_values(USER_IDS)}))
          + (select count(*) from public.profile_avatar_upload_intents
             where owner_user_id in ({sql_values(USER_IDS)}))
          + (select count(*) from storage.objects
             where id in ({sql_values(OBJECT_IDS)})
                or split_part(name, '/', 1) in ({sql_values(USER_IDS)}))
        );
        """
    ).strip()
    if fixture_count != "0":
        raise RuntimeError("Profile avatar database fixture UUIDs remain after rollback")


def main() -> None:
    load_dotenv()
    require_development_environment()
    output = run_psql(SQL)
    lines = {line.strip() for line in output.splitlines() if line.strip()}
    missing = [marker for marker in EXPECTED_MARKERS if marker not in lines]
    if missing:
        raise RuntimeError(
            f"Profile avatar database markers are missing: {', '.join(missing)}"
        )
    assert_fixtures_absent()
    for marker in EXPECTED_MARKERS:
        print(marker)
    print("profile_avatar_database_fixtures_absent=yes")


if __name__ == "__main__":
    main()
