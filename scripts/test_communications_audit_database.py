#!/usr/bin/env python3
"""Development-only, rollback-only Phase 5 communications acceptance."""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess


ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT / ".env"
FIXTURE_PREFIX = "00000000-0000-4000-8000-00000000f9"
EXPECTED = (
    "communications_database_security=yes",
    "communications_database_inquiry=yes",
    "communications_database_isolation=yes",
    "communications_database_inbox=yes",
    "communications_database_status=yes",
    "communications_database_notifications=yes",
    "communications_database_audit_export=yes",
    "communications_database_append_only=yes",
)


SQL = r"""
\set ON_ERROR_STOP on
begin;
select pg_advisory_xact_lock(hashtextextended('mt-communications-database-test', 0));

do $$
begin
  if not (select relrowsecurity from pg_class where oid = 'public.conversations'::regclass)
     or not (select relrowsecurity from pg_class where oid = 'public.conversation_messages'::regclass)
     or not (select relrowsecurity from pg_class where oid = 'public.conversation_status_actions'::regclass)
     or not (select relrowsecurity from pg_class where oid = 'public.audit_export_actions'::regclass) then
    raise exception 'Phase 5 RLS is incomplete';
  end if;
  if has_table_privilege('authenticated', 'public.conversations', 'SELECT')
     or has_table_privilege('anon', 'public.conversation_messages', 'SELECT')
     or has_table_privilege('service_role', 'public.audit_export_actions', 'SELECT') then
    raise exception 'Phase 5 private tables expose direct access';
  end if;
  if not has_function_privilege('anon', 'public.create_project_inquiry(text,text,text,text,text,text,text,text,text,uuid[],uuid)', 'EXECUTE')
     or has_function_privilege('anon', 'public.list_my_conversations(text,integer,timestamptz,uuid)', 'EXECUTE')
     or not has_function_privilege('authenticated', 'public.set_my_conversation_status(uuid,integer,text,uuid)', 'EXECUTE')
     or not has_function_privilege('authenticated', 'public.admin_export_audit_logs(text,text,text,text,text,timestamptz,timestamptz,integer,text,uuid)', 'EXECUTE') then
    raise exception 'Phase 5 function ACL is incomplete';
  end if;
end $$;
select 'communications_database_security=yes';

do $$ begin
  if exists (select 1 from public.users where id::text like '00000000-0000-4000-8000-00000000f9%')
     or exists (select 1 from public.folders where id in (
       '00000000-0000-4000-8000-00000000f911'::uuid,
       '00000000-0000-4000-8000-00000000f912'::uuid
     ))
     or exists (select 1 from public.images where id in (
       '00000000-0000-4000-8000-00000000f921'::uuid,
       '00000000-0000-4000-8000-00000000f922'::uuid
     )) then
    raise exception 'Phase 5 fixture collision';
  end if;
end $$;

create function pg_temp.set_claims(actor_id uuid, actor_role text, actor_aal text default 'aal1')
returns void language plpgsql as $$
begin
  perform set_config('request.jwt.claims', jsonb_build_object(
    'sub', actor_id, 'role', actor_role, 'aal', actor_aal,
    'amr', case when actor_aal = 'aal2' then jsonb_build_array(
      jsonb_build_object('method','password'), jsonb_build_object('method','totp')
    ) else jsonb_build_array(jsonb_build_object('method','password')) end
  )::text, true);
end $$;

insert into public.users (id, auth_subject, email, email_verified_at, account_status, is_system_identity) values
 ('00000000-0000-4000-8000-00000000f901','00000000-0000-4000-8000-00000000f901','creator@example.test',now(),'active',false),
 ('00000000-0000-4000-8000-00000000f902','00000000-0000-4000-8000-00000000f902','sender@example.test',now(),'active',false),
 ('00000000-0000-4000-8000-00000000f903','00000000-0000-4000-8000-00000000f903','outsider@example.test',now(),'active',false),
 ('00000000-0000-4000-8000-00000000f904','00000000-0000-4000-8000-00000000f904','admin@example.test',now(),'active',false),
 ('00000000-0000-4000-8000-00000000f905','00000000-0000-4000-8000-00000000f905','suspended@example.test',now(),'suspended',false),
 ('00000000-0000-4000-8000-00000000f906','00000000-0000-4000-8000-00000000f906','other@example.test',now(),'active',false);
insert into public.user_profiles (user_id, display_name, public_slug) values
 ('00000000-0000-4000-8000-00000000f901','Creator','phase5-creator'),
 ('00000000-0000-4000-8000-00000000f902','Sender','phase5-sender'),
 ('00000000-0000-4000-8000-00000000f903','Outsider','phase5-outsider'),
 ('00000000-0000-4000-8000-00000000f904','Audit Admin','phase5-admin'),
 ('00000000-0000-4000-8000-00000000f906','Other Creator','phase5-other');
insert into public.user_roles (user_id, role, reason)
select id, 'user'::public.role_code, 'Phase 5 acceptance' from public.users
where id::text like '00000000-0000-4000-8000-00000000f9%';
insert into public.user_roles (user_id, role, reason) values
 ('00000000-0000-4000-8000-00000000f904','admin','Phase 5 acceptance');
insert into public.folders (
 id, owner_user_id, name, sort_order, is_system
) values
 ('00000000-0000-4000-8000-00000000f911','00000000-0000-4000-8000-00000000f901','Inbox',0,true),
 ('00000000-0000-4000-8000-00000000f912','00000000-0000-4000-8000-00000000f906','Inbox',0,true);
insert into public.images (
 id, owner_user_id, folder_id, processing_status, workflow_status,
 publication_status, original_filename, published_at
) values
 ('00000000-0000-4000-8000-00000000f921','00000000-0000-4000-8000-00000000f901','00000000-0000-4000-8000-00000000f911','ready','approved','published','phase5-a.jpg',now()),
 ('00000000-0000-4000-8000-00000000f922','00000000-0000-4000-8000-00000000f906','00000000-0000-4000-8000-00000000f912','ready','approved','published','phase5-b.jpg',now());

set local role anon;
select set_config('request.jwt.claims','{"role":"anon"}',true);
do $$
declare result jsonb; replay jsonb;
begin
  result := public.create_project_inquiry(
    'Guest','guest@example.test','commission',null,'Editorial campaign',null,null,
    E'Please share licensing terms.','',array['00000000-0000-4000-8000-00000000f921'::uuid],
    '00000000-0000-4000-8000-00000000f961'
  );
  if (select count(*) from jsonb_object_keys(result)) <> 5 or not (result ?& array[
    'reference','status','created_at','replayed','selected_work_count'
  ]) or result ? 'conversation_id' then raise exception 'unsafe guest DTO: %', result; end if;
  replay := public.create_project_inquiry(
    'Guest','guest@example.test','commission',null,'Editorial campaign',null,null,
    E'Please share licensing terms.','',array['00000000-0000-4000-8000-00000000f921'::uuid],
    '00000000-0000-4000-8000-00000000f961'
  );
  if replay ->> 'replayed' <> 'true' then raise exception 'guest replay failed'; end if;
  result := public.create_project_inquiry(
    E'Bad\nName','bad@example.test','commission',null,'Editorial campaign',null,null,
    'A sufficiently long message','',array[]::uuid[],
    '00000000-0000-4000-8000-00000000f962'
  );
  if result #>> '{error,code}' <> 'INQUIRY_VALIDATION_FAILED' then raise exception 'control input accepted'; end if;
  result := public.create_project_inquiry(
    'Guest','mixed@example.test','commission',null,'Editorial campaign',null,null,
    'A sufficiently long message','',array[
      '00000000-0000-4000-8000-00000000f921'::uuid,
      '00000000-0000-4000-8000-00000000f922'::uuid
    ],'00000000-0000-4000-8000-00000000f963'
  );
  if result #>> '{error,code}' <> 'INQUIRY_WORKS_INVALID' then raise exception 'mixed owners accepted'; end if;
end $$;
reset role;
select 'communications_database_inquiry=yes';

set local role authenticated;
do $$
declare result jsonb; conversation_id uuid;
begin
  perform pg_temp.set_claims('00000000-0000-4000-8000-00000000f902','authenticated');
  result := public.create_project_inquiry(
    'Sender','sender@example.test','editorial','Studio','Editorial feature',null,null,
    'Please discuss publication terms.','',array['00000000-0000-4000-8000-00000000f921'::uuid],
    '00000000-0000-4000-8000-00000000f964'
  );
  conversation_id := (result ->> 'conversation_id')::uuid;
  if conversation_id is null or result ? 'recipient_user_id' then raise exception 'member DTO invalid: %', result; end if;
  perform pg_temp.set_claims('00000000-0000-4000-8000-00000000f903','authenticated');
  if jsonb_array_length(public.list_my_conversations('all',30,null,null)->'items') <> 0
     or public.get_my_conversation(conversation_id,100,null,null) #>> '{error,code}' <> 'CONVERSATION_NOT_FOUND' then
    raise exception 'participant isolation failed';
  end if;
  perform pg_temp.set_claims('00000000-0000-4000-8000-00000000f905','authenticated');
  begin perform public.list_my_conversations('all',30,null,null); raise exception 'suspended read accepted';
  exception when insufficient_privilege then null; end;
end $$;
reset role;
select 'communications_database_isolation=yes';

select set_config(
  'mt_test.guest_conversation_id',
  (select id::text from public.conversations
   where idempotency_key = '00000000-0000-4000-8000-00000000f961'),
  true
);
select set_config(
  'mt_test.member_conversation_id',
  (select id::text from public.conversations
   where idempotency_key = '00000000-0000-4000-8000-00000000f964'),
  true
);

set local role authenticated;
do $$
declare guest_id uuid; member_id uuid; result jsonb; replay jsonb;
begin
  guest_id := current_setting('mt_test.guest_conversation_id')::uuid;
  member_id := current_setting('mt_test.member_conversation_id')::uuid;
  perform pg_temp.set_claims('00000000-0000-4000-8000-00000000f901','authenticated');
  if (public.list_my_conversations('all',30,null,null)#>>'{items,0,unread_count}')::int < 1 then raise exception 'unread missing'; end if;
  result := public.mark_my_conversation_read(guest_id,null);
  if result ->> 'unread_count' <> '0' then raise exception 'mark read failed'; end if;
  result := public.reply_to_conversation(guest_id,1,'Thank you. We will respond manually.','00000000-0000-4000-8000-00000000f965');
  if result #>> '{delivery,provider_status}' <> 'unavailable' then raise exception 'guest delivery truth failed: %', result; end if;
  result := public.set_my_conversation_status(guest_id,2,'closed','00000000-0000-4000-8000-00000000f966');
  if result ->> 'status' <> 'closed' or result #>> '{delivery,provider_status}' <> 'unavailable' then raise exception 'close failed: %', result; end if;
  replay := public.set_my_conversation_status(guest_id,2,'closed','00000000-0000-4000-8000-00000000f966');
  if replay ->> 'replayed' <> 'true' then raise exception 'status replay failed'; end if;
  result := public.reply_to_conversation(guest_id,3,'Closed reply must fail.','00000000-0000-4000-8000-00000000f967');
  if result #>> '{error,code}' <> 'CONVERSATION_STATE_CONFLICT' then raise exception 'closed reply accepted'; end if;
  result := public.set_my_conversation_status(guest_id,3,'open','00000000-0000-4000-8000-00000000f968');
  if result ->> 'status' <> 'open' then raise exception 'reopen failed'; end if;
  result := public.reply_to_conversation(member_id,1,'Member response.','00000000-0000-4000-8000-00000000f969');
  if result #>> '{delivery,provider_status}' <> 'not_required' then raise exception 'member reply failed'; end if;
end $$;
reset role;
select 'communications_database_inbox=yes';
select 'communications_database_status=yes';

set local role authenticated;
do $$ declare result jsonb; begin
  perform pg_temp.set_claims('00000000-0000-4000-8000-00000000f902','authenticated');
  result := public.list_my_notifications(30,null,null);
  if (result ->> 'unread_count')::int < 1
     or (result->'items'->0) ? 'recipient_user_id'
     or (result->'items'->0) ? 'payload'
     or not (result->'items'->0) ? 'href' then raise exception 'notification DTO invalid: %', result; end if;
  perform public.mark_all_my_notifications_read();
  if public.get_my_notification_unread_count()->>'unread_count' <> '0' then raise exception 'notification read failed'; end if;
end $$;
reset role;
select 'communications_database_notifications=yes';

set local role authenticated;
do $$ declare result jsonb; replay jsonb; evidence jsonb; export_id uuid; begin
  perform pg_temp.set_claims('00000000-0000-4000-8000-00000000f904','authenticated','aal1');
  begin perform public.admin_get_audit_log('00000000-0000-4000-8000-00000000f999'); raise exception 'AAL1 audit accepted';
  exception when insufficient_privilege then null; end;
  perform pg_temp.set_claims('00000000-0000-4000-8000-00000000f904','authenticated','aal2');
  result := public.admin_list_audit_logs('success','conversation','conversation.','all','00000000',now()-interval '1 day',now()+interval '1 minute',100,null,null);
  if result ? 'error'
     or result#>'{actor,roles}' <> '["admin"]'::jsonb
     or jsonb_array_length(result->'items') < 1 then
    raise exception 'audit filters or actor role projection failed: %', result;
  end if;
  result := public.admin_export_audit_logs('all','all','','all','',now()-interval '1 day',now()+interval '1 minute',100,'operational_review','00000000-0000-4000-8000-00000000f970');
  export_id := (result#>>'{export,id}')::uuid;
  evidence := public.admin_list_audit_logs(
    'success','audit_export','audit.exported','00000000-0000-4000-8000-00000000f904',
    '00000000-0000-4000-8000-00000000f970',now()-interval '1 day',
    now()+interval '1 minute',10,null,null
  );
  if export_id is null or result#>>'{export,replayed}' <> 'false'
     or jsonb_array_length(evidence->'items') <> 1
     or evidence#>>'{items,0,target_id}' <> export_id::text then
    raise exception 'audit export failed: %, evidence=%', result, evidence;
  end if;
  replay := public.admin_export_audit_logs('all','all','','all','',now()-interval '1 day',now()+interval '1 minute',100,'operational_review','00000000-0000-4000-8000-00000000f970');
  if replay#>>'{export,replayed}' <> 'true' or replay#>>'{export,id}' <> export_id::text then raise exception 'export replay failed'; end if;
  perform set_config('mt_test.audit_export_id', export_id::text, true);
end $$;
reset role;
select 'communications_database_audit_export=yes';

do $$
declare mutation_rejected boolean := false;
begin
  begin
    update public.audit_export_actions set reason_code='compliance_request'
    where id=current_setting('mt_test.audit_export_id')::uuid;
  exception when raise_exception then
    if sqlerrm not like '%append-only%' then raise; end if;
    mutation_rejected := true;
  end;
  if not mutation_rejected then raise exception 'append-only update accepted'; end if;
end $$;
select 'communications_database_append_only=yes';
rollback;
"""


def load_env() -> dict[str, str]:
    env = os.environ.copy()
    if ENV_PATH.is_file():
        for raw in ENV_PATH.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            env.setdefault(key.strip(), value.strip().strip("\"'"))
    return env


def main() -> None:
    env = load_env()
    if env.get("MT_TEST_ENVIRONMENT") != "development" or env.get("MT_ALLOW_PRODUCTION") == "yes":
        raise RuntimeError("Refusing Phase 5 database fixtures outside development")
    missing_env = [name for name in ("PGHOST", "PGDATABASE", "PGUSER", "PGPASSWORD") if not env.get(name)]
    if missing_env:
        raise RuntimeError(f"Missing database environment: {', '.join(missing_env)}")
    psql = shutil.which("psql") or "/opt/homebrew/opt/libpq/bin/psql"
    completed = subprocess.run(
        [psql, "--set", "ON_ERROR_STOP=1"], input=SQL, text=True,
        cwd=ROOT, env=env, capture_output=True, check=False,
    )
    output = completed.stdout + completed.stderr
    if completed.returncode:
        raise RuntimeError(output.strip())
    missing = [marker for marker in EXPECTED if marker not in output]
    if missing:
        raise RuntimeError(f"Missing database markers: {', '.join(missing)}")
    absence = subprocess.run(
        [psql, "--tuples-only", "--no-align", "--command",
         "select "
         "(select count(*) from public.users where id::text like '00000000-0000-4000-8000-00000000f9%') + "
         "(select count(*) from public.folders where id in "
         "('00000000-0000-4000-8000-00000000f911','00000000-0000-4000-8000-00000000f912')) + "
         "(select count(*) from public.images where id in "
         "('00000000-0000-4000-8000-00000000f921','00000000-0000-4000-8000-00000000f922'));"],
        text=True, cwd=ROOT, env=env, capture_output=True, check=False,
    )
    if absence.returncode or absence.stdout.strip() != "0":
        raise RuntimeError("Phase 5 fixtures were not rolled back")
    print("communications_database_fixtures_rolled_back=yes")
    for marker in EXPECTED:
        print(marker)


if __name__ == "__main__":
    main()
