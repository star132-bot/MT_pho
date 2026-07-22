\set ON_ERROR_STOP on

-- Transactional Phase 3 authorization and decision verification.
-- All fixtures, decisions, notifications, and audit rows are rolled back.
begin;

select pg_advisory_xact_lock(hashtextextended('mt-phase3-review-database-test', 0));

do $$
begin
  if not has_function_privilege(
    'authenticated',
    'public.review_decide_submission(uuid,integer,text,jsonb,text,text,jsonb,uuid)',
    'EXECUTE'
  ) or has_function_privilege(
    'anon',
    'public.review_decide_submission(uuid,integer,text,jsonb,text,text,jsonb,uuid)',
    'EXECUTE'
  ) or has_function_privilege(
    'service_role',
    'public.review_decide_submission(uuid,integer,text,jsonb,text,text,jsonb,uuid)',
    'EXECUTE'
  ) then
    raise exception 'review decision RPC grant boundary is invalid';
  end if;
  if has_table_privilege('authenticated', 'public.review_submissions', 'INSERT,UPDATE,DELETE,TRUNCATE')
     or has_table_privilege('authenticated', 'public.review_decisions', 'INSERT,UPDATE,DELETE,TRUNCATE')
     or has_table_privilege('authenticated', 'public.audit_logs', 'INSERT,UPDATE,DELETE,TRUNCATE') then
    raise exception 'authenticated retains direct Review mutation privileges';
  end if;
  if exists (
    select 1
    from information_schema.columns
    where table_schema = 'public'
      and table_name = 'review_decisions'
      and column_name in ('expected_lock_version', 'result_snapshot')
      and is_nullable <> 'NO'
  ) then
    raise exception 'review decision replay evidence remains nullable';
  end if;
end
$$;

create function pg_temp.set_review_claims(
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
        else jsonb_build_array(jsonb_build_object('method', 'password'))
      end
    )::text,
    true
  );
end
$$;

insert into public.users (
  id, auth_subject, email, email_verified_at, account_status
) values
  ('00000000-0000-4000-8000-00000000f301', '00000000-0000-4000-8000-00000000f301', 'phase3-owner@example.test', now(), 'active'),
  ('00000000-0000-4000-8000-00000000f302', '00000000-0000-4000-8000-00000000f302', 'phase3-reviewer@example.test', now(), 'active'),
  ('00000000-0000-4000-8000-00000000f303', '00000000-0000-4000-8000-00000000f303', 'phase3-admin@example.test', now(), 'active'),
  ('00000000-0000-4000-8000-00000000f304', '00000000-0000-4000-8000-00000000f304', 'phase3-user@example.test', now(), 'active');

insert into public.user_profiles (user_id, display_name) values
  ('00000000-0000-4000-8000-00000000f301', 'Phase 3 Owner'),
  ('00000000-0000-4000-8000-00000000f302', 'Phase 3 Reviewer'),
  ('00000000-0000-4000-8000-00000000f303', 'Phase 3 Admin'),
  ('00000000-0000-4000-8000-00000000f304', 'Phase 3 User');

insert into public.user_roles (user_id, role, reason) values
  ('00000000-0000-4000-8000-00000000f301', 'user', 'phase3 database test'),
  ('00000000-0000-4000-8000-00000000f302', 'user', 'phase3 database test'),
  ('00000000-0000-4000-8000-00000000f302', 'reviewer', 'phase3 database test'),
  ('00000000-0000-4000-8000-00000000f303', 'user', 'phase3 database test'),
  ('00000000-0000-4000-8000-00000000f303', 'reviewer', 'phase3 role-stacking test'),
  ('00000000-0000-4000-8000-00000000f303', 'admin', 'phase3 role-stacking test'),
  ('00000000-0000-4000-8000-00000000f304', 'user', 'phase3 database test');

insert into public.folders (id, owner_user_id, name, sort_order, is_system) values
  ('00000000-0000-4000-8000-00000000f371', '00000000-0000-4000-8000-00000000f301', 'Inbox', 0, true),
  ('00000000-0000-4000-8000-00000000f372', '00000000-0000-4000-8000-00000000f302', 'Inbox', 0, true),
  ('00000000-0000-4000-8000-00000000f373', '00000000-0000-4000-8000-00000000f303', 'Inbox', 0, true),
  ('00000000-0000-4000-8000-00000000f374', '00000000-0000-4000-8000-00000000f304', 'Inbox', 0, true);

insert into public.images (
  id, owner_user_id, processing_status, workflow_status, publication_status,
  original_filename, original_width, original_height, checksum_sha256, version
) values
  (
    '00000000-0000-4000-8000-00000000f311',
    '00000000-0000-4000-8000-00000000f301',
    'ready', 'submitted', 'never_published', 'phase3-main.jpg', 1600, 1200,
    repeat('a', 64), 1
  ),
  (
    '00000000-0000-4000-8000-00000000f312',
    '00000000-0000-4000-8000-00000000f302',
    'ready', 'submitted', 'never_published', 'phase3-self.jpg', 1200, 1600,
    repeat('b', 64), 1
  );

insert into public.image_versions (
  id, image_id, version_number, title, alt_text, content_category,
  copyright_holder, copyright_year, contains_recognizable_people,
  model_release_status, property_release_status, rights_declared,
  ai_disclosure, sensitive_content_disclosure, created_by_user_id, locked_at
) values
  (
    '00000000-0000-4000-8000-00000000f321',
    '00000000-0000-4000-8000-00000000f311',
    1, 'Phase 3 Main', 'A database test fixture.', 'concrete',
    'Phase 3 Owner', 2026, false, 'not_applicable', 'not_applicable', true,
    'none', 'none', '00000000-0000-4000-8000-00000000f301', now()
  ),
  (
    '00000000-0000-4000-8000-00000000f322',
    '00000000-0000-4000-8000-00000000f312',
    1, 'Phase 3 Self Review', 'A self-review fixture.', 'concrete',
    'Phase 3 Reviewer', 2026, false, 'not_applicable', 'not_applicable', true,
    'none', 'none', '00000000-0000-4000-8000-00000000f302', now()
  );

update public.images set current_version_id = case id
  when '00000000-0000-4000-8000-00000000f311' then '00000000-0000-4000-8000-00000000f321'::uuid
  else '00000000-0000-4000-8000-00000000f322'::uuid
end
where id in (
  '00000000-0000-4000-8000-00000000f311',
  '00000000-0000-4000-8000-00000000f312'
);

-- The scanner insert trigger correctly requires real Storage objects. This
-- test owns the review boundary, so it inserts already-scanned fixtures while
-- disabling only that trigger inside this rollback-only transaction.
alter table public.image_assets disable trigger image_assets_enqueue_scan_job;
insert into public.image_assets (
  id, image_id, owner_user_id, kind, storage_key, mime_type, byte_size,
  width, height, checksum_sha256, scan_status, scan_result_code,
  scan_completed_at, scan_policy_version, storage_visibility
) values
  (
    '00000000-0000-4000-8000-00000000f341',
    '00000000-0000-4000-8000-00000000f311',
    '00000000-0000-4000-8000-00000000f301',
    'original', '00000000-0000-4000-8000-00000000f301/phase3/original.jpg',
    'image/jpeg', 1200, 1600, 1200, repeat('a', 64), 'clean', 'clean', now(),
    'mt-asset-scan-2026-07-v1', 'private'
  ),
  (
    '00000000-0000-4000-8000-00000000f342',
    '00000000-0000-4000-8000-00000000f311',
    '00000000-0000-4000-8000-00000000f301',
    'display', '00000000-0000-4000-8000-00000000f301/phase3/display.jpg',
    'image/jpeg', 900, 1200, 900, repeat('b', 64), 'clean', 'clean', now(),
    'mt-asset-scan-2026-07-v1', 'private'
  ),
  (
    '00000000-0000-4000-8000-00000000f343',
    '00000000-0000-4000-8000-00000000f311',
    '00000000-0000-4000-8000-00000000f301',
    'thumbnail', '00000000-0000-4000-8000-00000000f301/phase3/thumbnail.jpg',
    'image/jpeg', 300, 400, 300, repeat('c', 64), 'clean', 'clean', now(),
    'mt-asset-scan-2026-07-v1', 'private'
  );
alter table public.image_assets enable trigger image_assets_enqueue_scan_job;

insert into public.review_submissions (
  id, image_id, image_version_id, submitted_by_user_id, idempotency_key,
  status, policy_version, lock_version, readiness_snapshot, asset_snapshot
) values
  (
    '00000000-0000-4000-8000-00000000f331',
    '00000000-0000-4000-8000-00000000f311',
    '00000000-0000-4000-8000-00000000f321',
    '00000000-0000-4000-8000-00000000f301',
    '00000000-0000-4000-8000-00000000f351',
    'submitted', 'mt-review-2026-07-v1', 1,
    '{"ready":true,"checks":[{},{},{},{},{}]}'::jsonb,
    '[{},{},{}]'::jsonb
  ),
  (
    '00000000-0000-4000-8000-00000000f332',
    '00000000-0000-4000-8000-00000000f312',
    '00000000-0000-4000-8000-00000000f322',
    '00000000-0000-4000-8000-00000000f302',
    '00000000-0000-4000-8000-00000000f352',
    'submitted', 'mt-review-2026-07-v1', 1,
    '{"ready":true,"checks":[{},{},{},{},{}]}'::jsonb,
    '[{},{},{}]'::jsonb
  );

select pg_temp.set_review_claims('00000000-0000-4000-8000-00000000f304');
do $$
begin
  begin
    perform public.review_list_submissions('open', 'all', 30, 0);
    raise exception 'normal user opened the Review Queue';
  exception when sqlstate '42501' then
    null;
  end;
end
$$;

select pg_temp.set_review_claims('00000000-0000-4000-8000-00000000f302', 'aal1', true);
do $$
begin
  begin
    perform public.review_list_submissions('open', 'all', 30, 0);
    raise exception 'recovery session opened the Review Queue';
  exception when sqlstate '42501' then
    null;
  end;
end
$$;

select pg_temp.set_review_claims('00000000-0000-4000-8000-00000000f303', 'aal1');
do $$
begin
  begin
    perform public.review_list_submissions('open', 'all', 30, 0);
    raise exception 'stacked Admin AAL1 bypassed MFA through Reviewer';
  exception when sqlstate '42501' then
    null;
  end;
end
$$;

set local role authenticated;
do $$
begin
  if (select count(*) from public.review_submissions) <> 0
     or (select count(*) from public.review_decisions) <> 0
     or (select count(*) from public.image_assets where image_id = '00000000-0000-4000-8000-00000000f311') <> 0 then
    raise exception 'stacked Admin AAL1 direct RLS scope is not empty';
  end if;
end
$$;
reset role;

select pg_temp.set_review_claims('00000000-0000-4000-8000-00000000f302', 'aal1');
do $$
declare
  response jsonb;
  checklist constant jsonb := '{
    "file_integrity": true,
    "rights": true,
    "privacy": true,
    "minors": true,
    "sensitive_content": true,
    "hate_illegal": true,
    "property_release": true,
    "third_party_ip": true,
    "ai_disclosure": true,
    "public_metadata": true
  }'::jsonb;
begin
  response := public.review_list_submissions('open', 'all', 30, 0);
  if response #>> '{pagination,total}' <> '1'
     or response #>> '{items,0,id}' <> '00000000-0000-4000-8000-00000000f331' then
    raise exception 'Reviewer queue did not exclude the self-owned submission';
  end if;
  response := public.review_get_submission('00000000-0000-4000-8000-00000000f331');
  if response #>> '{error,code}' <> 'REVIEW_SUBMISSION_NOT_FOUND' then
    raise exception 'Reviewer loaded unassigned private detail';
  end if;
  response := public.review_assign_submission('00000000-0000-4000-8000-00000000f332', 1);
  if response #>> '{error,code}' <> 'REVIEW_SELF_REVIEW_FORBIDDEN' then
    raise exception 'Reviewer assigned a self-owned submission';
  end if;
  response := public.review_start_submission('00000000-0000-4000-8000-00000000f332', 1);
  if response #>> '{error,code}' <> 'REVIEW_SELF_REVIEW_FORBIDDEN' then
    raise exception 'Reviewer started a self-owned submission';
  end if;
  response := public.review_decide_submission(
    '00000000-0000-4000-8000-00000000f332', 1, 'reject',
    '["content_policy"]'::jsonb, 'Self review must fail.', '', checklist,
    '00000000-0000-4000-8000-00000000f361'
  );
  if response #>> '{error,code}' <> 'REVIEW_SELF_REVIEW_FORBIDDEN' then
    raise exception 'Reviewer decided a self-owned submission';
  end if;

  response := public.review_start_submission('00000000-0000-4000-8000-00000000f331', 1);
  if response #>> '{submission,status}' <> 'in_review'
     or response #>> '{submission,lock_version}' <> '2' then
    raise exception 'Reviewer did not atomically claim and start the submission';
  end if;
  response := public.review_get_submission('00000000-0000-4000-8000-00000000f331');
  if jsonb_array_length(response -> 'assets') <> 3 then
    raise exception 'Assigned Reviewer did not receive the three current clean assets';
  end if;
end
$$;

set local role authenticated;
do $$
begin
  if (select count(*) from public.review_submissions where id = '00000000-0000-4000-8000-00000000f331') <> 1
     or (select count(*) from public.image_assets where image_id = '00000000-0000-4000-8000-00000000f311') <> 3 then
    raise exception 'assigned Reviewer direct RLS scope is incomplete';
  end if;
  if not public.can_read_review_storage_object(
    'image-originals',
    '00000000-0000-4000-8000-00000000f301/phase3/original.jpg',
    '00000000-0000-4000-8000-00000000f301'
  ) or public.can_read_review_storage_object(
    'image-display',
    '00000000-0000-4000-8000-00000000f301/phase3/original.jpg',
    '00000000-0000-4000-8000-00000000f301'
  ) then
    raise exception 'Review Storage bucket-kind binding is invalid';
  end if;
end
$$;
reset role;

update public.image_assets
set scan_policy_version = 'legacy-policy'
where id = '00000000-0000-4000-8000-00000000f343';
do $$
begin
  if public.can_read_review_storage_object(
    'image-thumbnails',
    '00000000-0000-4000-8000-00000000f301/phase3/thumbnail.jpg',
    '00000000-0000-4000-8000-00000000f301'
  ) then
    raise exception 'Review Storage accepted a stale scan policy';
  end if;
end
$$;
update public.image_assets
set scan_policy_version = 'mt-asset-scan-2026-07-v1'
where id = '00000000-0000-4000-8000-00000000f343';

do $$
declare
  response jsonb;
  approval_result jsonb;
  checklist constant jsonb := '{
    "file_integrity": true,
    "rights": true,
    "privacy": true,
    "minors": true,
    "sensitive_content": true,
    "hate_illegal": true,
    "property_release": true,
    "third_party_ip": true,
    "ai_disclosure": true,
    "public_metadata": true
  }'::jsonb;
begin
  response := public.review_decide_submission(
    '00000000-0000-4000-8000-00000000f331', 1, 'approve',
    '["policy_complete"]'::jsonb, 'Approved after review.', 'Reviewer note.', checklist,
    '00000000-0000-4000-8000-00000000f362'
  );
  if response #>> '{error,code}' <> 'REVIEW_VERSION_CONFLICT' then
    raise exception 'stale Review decision did not fail CAS';
  end if;
  response := public.review_decide_submission(
    '00000000-0000-4000-8000-00000000f331', 2, 'approve_and_publish',
    '["policy_complete"]'::jsonb, 'Publish must require Admin.', '', checklist,
    '00000000-0000-4000-8000-00000000f363'
  );
  if response #>> '{error,code}' <> 'REVIEW_PUBLISH_ADMIN_REQUIRED' then
    raise exception 'Reviewer crossed the publish boundary';
  end if;
  approval_result := public.review_decide_submission(
    '00000000-0000-4000-8000-00000000f331', 2, 'approve',
    '["policy_complete"]'::jsonb, 'Approved after review.', 'Reviewer note.', checklist,
    '00000000-0000-4000-8000-00000000f364'
  );
  if approval_result #>> '{submission,status}' <> 'approved'
     or approval_result #>> '{submission,lock_version}' <> '3'
     or approval_result #>> '{image,workflow_status}' <> 'approved'
     or approval_result #>> '{image,publication_status}' <> 'never_published' then
    raise exception 'Reviewer approval result is invalid';
  end if;
  if not exists (
    select 1 from public.review_decisions d
    where d.idempotency_key = '00000000-0000-4000-8000-00000000f364'
      and d.expected_lock_version = 2
      and d.result_snapshot = approval_result
  ) then
    raise exception 'Reviewer approval did not persist immutable replay evidence';
  end if;
end
$$;

set local role authenticated;
do $$
begin
  if (select count(*) from public.review_submissions where id = '00000000-0000-4000-8000-00000000f331') <> 0
     or (select count(*) from public.image_assets where image_id = '00000000-0000-4000-8000-00000000f311') <> 0
     or public.can_read_review_storage_object(
       'image-originals',
       '00000000-0000-4000-8000-00000000f301/phase3/original.jpg',
       '00000000-0000-4000-8000-00000000f301'
     ) then
    raise exception 'Reviewer private access survived the terminal review state';
  end if;
end
$$;
reset role;

select pg_temp.set_review_claims('00000000-0000-4000-8000-00000000f303', 'aal2');
do $$
declare
  response jsonb;
  checklist constant jsonb := '{
    "file_integrity": true,
    "rights": true,
    "privacy": true,
    "minors": true,
    "sensitive_content": true,
    "hate_illegal": true,
    "property_release": true,
    "third_party_ip": true,
    "ai_disclosure": true,
    "public_metadata": true
  }'::jsonb;
begin
  response := public.review_decide_submission(
    '00000000-0000-4000-8000-00000000f331', 3, 'approve_and_publish',
    '["policy_complete"]'::jsonb, 'Approved and published.', 'Admin publish note.', checklist,
    '00000000-0000-4000-8000-00000000f365'
  );
  if response #>> '{submission,status}' <> 'approved'
     or response #>> '{submission,lock_version}' <> '4'
     or response #>> '{image,publication_status}' <> 'published'
     or response #>> '{image,published_at}' is null then
    raise exception 'Admin AAL2 publish result is invalid';
  end if;
end
$$;

set local role authenticated;
do $$
begin
  if (select count(*) from public.review_submissions where id = '00000000-0000-4000-8000-00000000f331') <> 1
     or (select count(*) from public.image_assets where image_id = '00000000-0000-4000-8000-00000000f311') <> 3
     or not public.can_read_review_storage_object(
       'image-originals',
       '00000000-0000-4000-8000-00000000f301/phase3/original.jpg',
       '00000000-0000-4000-8000-00000000f301'
     ) then
    raise exception 'Admin AAL2 full Review scope is incomplete';
  end if;
end
$$;
reset role;

select pg_temp.set_review_claims('00000000-0000-4000-8000-00000000f302', 'aal1');
do $$
declare
  replay_result jsonb;
  conflict_result jsonb;
  checklist constant jsonb := '{
    "file_integrity": true,
    "rights": true,
    "privacy": true,
    "minors": true,
    "sensitive_content": true,
    "hate_illegal": true,
    "property_release": true,
    "third_party_ip": true,
    "ai_disclosure": true,
    "public_metadata": true
  }'::jsonb;
begin
  replay_result := public.review_decide_submission(
    '00000000-0000-4000-8000-00000000f331', 2, 'approve',
    '["policy_complete"]'::jsonb, 'Approved after review.', 'Reviewer note.', checklist,
    '00000000-0000-4000-8000-00000000f364'
  );
  if replay_result #>> '{submission,lock_version}' <> '3'
     or replay_result #>> '{image,publication_status}' <> 'never_published' then
    raise exception 'same-payload replay drifted after a later publish decision';
  end if;
  conflict_result := public.review_decide_submission(
    '00000000-0000-4000-8000-00000000f331', 2, 'approve',
    '["policy_complete"]'::jsonb, 'Different replay payload.', 'Reviewer note.', checklist,
    '00000000-0000-4000-8000-00000000f364'
  );
  if conflict_result #>> '{error,code}' <> 'REVIEW_IDEMPOTENCY_CONFLICT' then
    raise exception 'same key accepted a different Review payload';
  end if;
end
$$;

do $$
declare
  publish_audit public.audit_logs%rowtype;
begin
  if (select count(*) from public.review_decisions where submission_id = '00000000-0000-4000-8000-00000000f331') <> 2 then
    raise exception 'decision replay created duplicate decision rows';
  end if;
  if (
    select count(*) from public.notifications
    where recipient_user_id = '00000000-0000-4000-8000-00000000f301'
      and type in ('image_review_started', 'image_approved', 'image_published')
  ) <> 3 then
    raise exception 'review lifecycle notification count is invalid';
  end if;
  select * into publish_audit from public.audit_logs a
  where a.request_id = '00000000-0000-4000-8000-00000000f365';
  if publish_audit.id is null
     or publish_audit.action <> 'review.approve_and_publish'
     or publish_audit.before_state ->> 'submission_status' <> 'approved'
     or publish_audit.before_state ->> 'publication_status' <> 'never_published'
     or publish_audit.before_state #>> '{asset_storage_visibility,display}' <> 'private'
     or publish_audit.after_state ->> 'submission_status' <> 'approved'
     or publish_audit.after_state ->> 'publication_status' <> 'published'
     or publish_audit.after_state #>> '{asset_storage_visibility,display}' <> 'public'
     or publish_audit.after_state #>> '{asset_storage_visibility,thumbnail}' <> 'public' then
    raise exception 'publish audit before/after evidence is invalid';
  end if;
  if (select storage_visibility from public.image_assets where kind = 'original' and image_id = '00000000-0000-4000-8000-00000000f311') <> 'private'
     or (select count(*) from public.image_assets where image_id = '00000000-0000-4000-8000-00000000f311' and kind in ('display', 'thumbnail') and storage_visibility = 'public') <> 2 then
    raise exception 'publish changed the wrong asset visibility';
  end if;
end
$$;

rollback;

\echo review_database_role_aal_rls=yes
\echo review_database_self_review_denied=yes
\echo review_database_storage_lifecycle=yes
\echo review_database_cas_and_idempotency=yes
\echo review_database_stable_result_snapshot=yes
\echo review_database_notification_audit=yes
\echo review_database_fixtures_rolled_back=yes
