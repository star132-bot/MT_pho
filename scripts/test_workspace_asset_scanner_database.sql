-- Transactional Phase 2F state-machine verification. No verdict is committed.
\set ON_ERROR_STOP on
\getenv mt_test_environment MT_TEST_ENVIRONMENT
\if :{?mt_test_environment}
  select :'mt_test_environment' = 'development' as test_allowed \gset
\else
  \echo Scanner database acceptance requires MT_TEST_ENVIRONMENT=development.
  \quit 2
\endif
\if :test_allowed
\else
  \echo Scanner database acceptance refuses production.
  \quit 2
\endif
begin;

-- Use an empty isolated clone, so no existing user's scan job can be claimed.
do $$ begin
  if exists (select 1 from public.users)
     or exists (select 1 from public.images)
     or exists (select 1 from public.asset_scan_jobs) then
    raise exception 'Scanner state-machine acceptance requires a data-free isolated clone';
  end if;
end $$;

insert into public.users (id, auth_subject, email, email_verified_at, account_status)
values ('00000000-0000-4000-8000-00000000fa01', '00000000-0000-4000-8000-00000000fa01',
        'scanner-isolated@example.test', now(), 'active');
insert into public.folders (id, owner_user_id, name, sort_order, is_system)
values ('00000000-0000-4000-8000-00000000fa21', '00000000-0000-4000-8000-00000000fa01', 'Inbox', 0, true);
insert into public.images (id, owner_user_id, original_filename, original_width, original_height, checksum_sha256)
values ('00000000-0000-4000-8000-00000000fa11', '00000000-0000-4000-8000-00000000fa01',
        'scanner-fixture.jpg', 20, 30, repeat('a',64));
insert into storage.objects (bucket_id, name, owner_id, metadata)
select bucket, '00000000-0000-4000-8000-00000000fa01/scanner-fixture-' || kind || '.jpg',
       '00000000-0000-4000-8000-00000000fa01', jsonb_build_object('mimetype','image/jpeg','size',1200)
from (values ('original','image-originals'), ('display','image-display'), ('thumbnail','image-thumbnails')) assets(kind,bucket);
insert into public.image_assets (image_id, owner_user_id, kind, storage_key, mime_type, byte_size, width, height, checksum_sha256)
select '00000000-0000-4000-8000-00000000fa11', '00000000-0000-4000-8000-00000000fa01',
       kind, '00000000-0000-4000-8000-00000000fa01/scanner-fixture-' || kind || '.jpg',
       'image/jpeg',1200,20,30,repeat('a',64)
from (values ('original'), ('display'), ('thumbnail')) assets(kind);

do $$
declare
  first_claim jsonb;
  second_claim jsonb;
  third_claim jsonb;
  reclaimed_claim jsonb;
  first_job jsonb;
  second_job jsonb;
  third_job jsonb;
  reclaimed_job jsonb;
  clean_result jsonb;
  response jsonb;
  first_asset_id uuid;
  second_asset_id uuid;
  third_asset_id uuid;
  first_token uuid;
  second_token uuid;
  third_token uuid;
  reclaimed_token uuid;
begin
  if not has_function_privilege('service_role', 'public.scanner_claim_asset_scan(text,integer)', 'EXECUTE')
     or has_function_privilege('authenticated', 'public.scanner_claim_asset_scan(text,integer)', 'EXECUTE')
     or has_function_privilege('anon', 'public.scanner_claim_asset_scan(text,integer)', 'EXECUTE') then
    raise exception 'scanner RPC grant boundary is invalid';
  end if;
  if (
    select count(*)
    from information_schema.role_table_grants
    where table_schema = 'public'
      and table_name in ('asset_scan_jobs', 'asset_scan_events')
      and grantee in ('anon', 'authenticated', 'service_role')
  ) <> 0 then
    raise exception 'scanner tables expose generic grants';
  end if;

  first_claim := public.scanner_claim_asset_scan('phase2f-db-test-a', 300);
  second_claim := public.scanner_claim_asset_scan('phase2f-db-test-b', 300);
  third_claim := public.scanner_claim_asset_scan('phase2f-db-test-c', 300);
  first_job := first_claim -> 'job';
  second_job := second_claim -> 'job';
  third_job := third_claim -> 'job';
  if jsonb_typeof(first_job) is distinct from 'object'
     or jsonb_typeof(second_job) is distinct from 'object'
     or jsonb_typeof(third_job) is distinct from 'object' then
    raise exception 'three queued scanner jobs are required for the transactional test';
  end if;

  first_asset_id := (first_job ->> 'asset_id')::uuid;
  second_asset_id := (second_job ->> 'asset_id')::uuid;
  third_asset_id := (third_job ->> 'asset_id')::uuid;
  first_token := (first_job ->> 'lease_token')::uuid;
  second_token := (second_job ->> 'lease_token')::uuid;
  third_token := (third_job ->> 'lease_token')::uuid;
  if first_asset_id = second_asset_id
     or first_asset_id = third_asset_id
     or second_asset_id = third_asset_id then
    raise exception 'SKIP LOCKED claims were not disjoint';
  end if;

  clean_result := jsonb_build_object(
    'outcome', 'clean',
    'result_code', 'clean',
    'scanner_version', 'mt-presence-phase2f-1',
    'engine_name', 'clamav+pillow',
    'engine_version', 'transactional-test',
    'observed_mime_type', first_job ->> 'mime_type',
    'observed_byte_size', (first_job ->> 'byte_size')::bigint,
    'observed_width', (first_job ->> 'width')::integer,
    'observed_height', (first_job ->> 'height')::integer,
    'observed_checksum_sha256', first_job ->> 'checksum_sha256'
  );
  response := public.scanner_complete_asset_scan(first_asset_id, first_token, clean_result);
  if coalesce((response ->> 'completed')::boolean, false) is not true
     or coalesce((response ->> 'idempotent')::boolean, true) is not false then
    raise exception 'first completion did not commit inside the test transaction';
  end if;
  response := public.scanner_complete_asset_scan(first_asset_id, first_token, clean_result);
  if coalesce((response ->> 'idempotent')::boolean, false) is not true then
    raise exception 'same-token completion was not idempotent';
  end if;
  response := public.scanner_complete_asset_scan(
    first_asset_id,
    first_token,
    jsonb_set(clean_result, '{engine_version}', '"different-result"'::jsonb)
  );
  if response #>> '{error,code}' <> 'SCAN_COMPLETION_CONFLICT' then
    raise exception 'same token accepted a conflicting completion';
  end if;

  response := public.scanner_retry_asset_scan(second_asset_id, second_token, 'storage_unavailable', 1);
  if coalesce((response ->> 'retried')::boolean, false) is not true then
    raise exception 'transient retry was not scheduled';
  end if;
  response := public.scanner_complete_asset_scan(second_asset_id, second_token, clean_result);
  if response #>> '{error,code}' <> 'SCAN_LEASE_CONFLICT' then
    raise exception 'old token completed a retry-wait job';
  end if;

  update public.asset_scan_jobs
  set lease_expires_at = now() - interval '1 second'
  where asset_id = third_asset_id;
  reclaimed_claim := public.scanner_claim_asset_scan('phase2f-db-test-d', 300);
  reclaimed_job := reclaimed_claim -> 'job';
  reclaimed_token := (reclaimed_job ->> 'lease_token')::uuid;
  if (reclaimed_job ->> 'asset_id')::uuid <> third_asset_id
     or (reclaimed_job ->> 'attempt_number')::integer <> 2
     or reclaimed_token = third_token then
    raise exception 'expired lease was not safely reclaimed';
  end if;
  response := public.scanner_complete_asset_scan(third_asset_id, third_token, clean_result);
  if response #>> '{error,code}' <> 'SCAN_LEASE_CONFLICT' then
    raise exception 'expired token completed a reclaimed job';
  end if;

  update public.asset_scan_jobs
  set max_attempts = attempt_count
  where asset_id = third_asset_id;
  response := public.scanner_retry_asset_scan(third_asset_id, reclaimed_token, 'clamav_unavailable', 1);
  if coalesce((response ->> 'terminal')::boolean, false) is not true
     or response ->> 'status' <> 'failed' then
    raise exception 'attempt exhaustion did not fail closed';
  end if;
end
$$;

rollback;

\echo workspace_asset_scanner_database_state_machine=yes
