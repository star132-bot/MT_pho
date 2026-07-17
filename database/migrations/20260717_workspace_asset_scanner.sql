-- Phase 2F: trusted, leased asset scanning for Workspace uploads.
begin;

alter table public.image_assets
  add column if not exists scan_completed_at timestamptz,
  add column if not exists scan_policy_version text;

create table if not exists public.asset_scan_jobs (
  id uuid primary key default gen_random_uuid(),
  asset_id uuid not null unique references public.image_assets(id) on delete restrict,
  status text not null default 'queued'
    check (status in ('queued', 'leased', 'retry_wait', 'clean', 'flagged', 'failed')),
  attempt_count integer not null default 0 check (attempt_count >= 0),
  max_attempts integer not null default 5 check (max_attempts between 1 and 20),
  available_at timestamptz not null default now(),
  lease_token uuid,
  lease_owner text,
  lease_expires_at timestamptz,
  last_lease_token uuid,
  last_completed_attempt integer check (last_completed_attempt is null or last_completed_attempt > 0),
  last_outcome text check (last_outcome is null or last_outcome in ('retry', 'clean', 'flagged', 'failed')),
  last_result_fingerprint char(64),
  expected_storage_object_id uuid,
  storage_bucket text not null check (storage_bucket in ('image-originals', 'image-display', 'image-thumbnails')),
  storage_key text not null,
  mime_type text not null,
  byte_size bigint not null check (byte_size > 0),
  width integer not null check (width > 0),
  height integer not null check (height > 0),
  checksum_sha256 char(64),
  scan_policy_version text not null,
  scanner_version text,
  engine_name text,
  engine_version text,
  result_code text,
  result_details jsonb not null default '{}'::jsonb
    check (jsonb_typeof(result_details) = 'object' and octet_length(result_details::text) <= 16384),
  completed_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  check (attempt_count <= max_attempts),
  check (
    (status = 'leased' and lease_token is not null and lease_owner is not null and lease_expires_at is not null)
    or (status <> 'leased' and lease_token is null and lease_owner is null and lease_expires_at is null)
  ),
  check (
    (status in ('clean', 'flagged', 'failed') and completed_at is not null and result_code is not null)
    or (status not in ('clean', 'flagged', 'failed') and completed_at is null)
  ),
  constraint asset_scan_jobs_claim_prerequisites check (
    status not in ('queued', 'leased', 'retry_wait')
    or (
      expected_storage_object_id is not null
      and checksum_sha256 is not null
      and lower(checksum_sha256::text) ~ '^[0-9a-f]{64}$'
    )
  )
);

create index if not exists asset_scan_jobs_claim_idx
  on public.asset_scan_jobs (status, available_at, created_at)
  where status in ('queued', 'retry_wait', 'leased');
create index if not exists asset_scan_jobs_expired_lease_idx
  on public.asset_scan_jobs (lease_expires_at)
  where status = 'leased';

create table if not exists public.asset_scan_events (
  id uuid primary key default gen_random_uuid(),
  job_id uuid not null references public.asset_scan_jobs(id) on delete restrict,
  asset_id uuid not null references public.image_assets(id) on delete restrict,
  attempt_number integer not null check (attempt_number >= 0),
  event_type text not null check (event_type in (
    'queued', 'claimed', 'lease_expired', 'retry_scheduled', 'clean', 'flagged', 'failed'
  )),
  worker_id text,
  result_code text,
  details jsonb not null default '{}'::jsonb
    check (jsonb_typeof(details) = 'object' and octet_length(details::text) <= 16384),
  created_at timestamptz not null default now()
);

create index if not exists asset_scan_events_asset_idx
  on public.asset_scan_events (asset_id, created_at desc);
create index if not exists asset_scan_events_job_idx
  on public.asset_scan_events (job_id, created_at desc);
create unique index if not exists asset_scan_events_job_attempt_type_key
  on public.asset_scan_events (job_id, attempt_number, event_type);

alter table public.asset_scan_jobs enable row level security;
alter table public.asset_scan_events enable row level security;
revoke all on public.asset_scan_jobs from public, anon, authenticated, service_role;
revoke all on public.asset_scan_events from public, anon, authenticated, service_role;
revoke insert on public.image_assets from service_role;
revoke update on public.image_assets from service_role;
revoke delete on public.image_assets from service_role;

-- Normalize legacy terminal rows before the stricter terminal metadata
-- constraint is validated. These values describe preserved historical trust;
-- they are not represented as results from the new scanner.
update public.image_assets set
  scan_result_code = coalesce(nullif(btrim(scan_result_code), ''), 'legacy_' || scan_status),
  scan_completed_at = coalesce(scan_completed_at, created_at, now()),
  scan_policy_version = coalesce(nullif(btrim(scan_policy_version), ''), 'legacy-preserved-v1')
where scan_status in ('clean', 'flagged', 'failed');

update public.image_assets set
  scan_result_code = null,
  scan_completed_at = null,
  scan_policy_version = null
where scan_status = 'pending';

-- Preserve immutable submission snapshots, but never treat a legacy current
-- asset verdict as trusted. Every non-Phase-2F clean asset is queued again so
-- a later changes-requested or republish flow cannot reuse legacy trust.
update public.image_assets a set
  scan_status = 'pending',
  scan_result_code = null,
  scan_completed_at = null,
  scan_policy_version = null
where a.deleted_at is null
  and a.scan_status = 'clean'
  and coalesce(a.scan_policy_version, '') <> 'mt-asset-scan-2026-07-v1'
  and not exists (
    select 1 from public.asset_scan_jobs existing_job
    where existing_job.asset_id = a.id
  );

-- Never put an unclaimable legacy asset into the live queue. Existing pending
-- rows must have a canonical checksum and a matching immutable Storage object.
update public.image_assets a set
  scan_status = 'failed',
  scan_result_code = case
    when a.mime_type not in ('image/jpeg', 'image/png', 'image/webp')
      or a.checksum_sha256 is null
      or lower(a.checksum_sha256::text) !~ '^[0-9a-f]{64}$'
      then 'scan_backfill_invalid_metadata'
    else 'scan_backfill_storage_mismatch'
  end,
  scan_completed_at = now(),
  scan_policy_version = 'mt-asset-scan-2026-07-v1'
where a.deleted_at is null
  and a.scan_status = 'pending'
  and not exists (
    select 1 from public.asset_scan_jobs existing_job
    where existing_job.asset_id = a.id
  )
  and (
    a.mime_type not in ('image/jpeg', 'image/png', 'image/webp')
    or a.checksum_sha256 is null
    or lower(a.checksum_sha256::text) !~ '^[0-9a-f]{64}$'
    or not exists (
      select 1
      from storage.objects o
      where o.bucket_id = case a.kind
        when 'original' then 'image-originals'
        when 'display' then 'image-display'
        else 'image-thumbnails'
      end
        and o.name = a.storage_key
        and o.owner_id = a.owner_user_id::text
        and lower(coalesce(o.metadata ->> 'mimetype', '')) = lower(a.mime_type)
        and coalesce(o.metadata ->> 'size', '') = a.byte_size::text
    )
  );

insert into public.asset_scan_jobs (
  asset_id,
  status,
  attempt_count,
  max_attempts,
  available_at,
  expected_storage_object_id,
  storage_bucket,
  storage_key,
  mime_type,
  byte_size,
  width,
  height,
  checksum_sha256,
  scan_policy_version,
  scanner_version,
  engine_name,
  engine_version,
  result_code,
  result_details,
  completed_at
)
select
  a.id,
  case when a.scan_status = 'pending' then 'queued' else a.scan_status end,
  0,
  5,
  now(),
  (
    select o.id from storage.objects o
    where o.bucket_id = case a.kind
      when 'original' then 'image-originals'
      when 'display' then 'image-display'
      else 'image-thumbnails'
    end
      and o.name = a.storage_key
      and o.owner_id = a.owner_user_id::text
      and lower(coalesce(o.metadata ->> 'mimetype', '')) = lower(a.mime_type)
      and coalesce(o.metadata ->> 'size', '') = a.byte_size::text
    limit 1
  ),
  case a.kind
    when 'original' then 'image-originals'
    when 'display' then 'image-display'
    else 'image-thumbnails'
  end,
  a.storage_key,
  a.mime_type,
  a.byte_size,
  a.width,
  a.height,
  a.checksum_sha256,
  case when a.scan_status = 'pending'
    then 'mt-asset-scan-2026-07-v1'
    else coalesce(a.scan_policy_version, 'legacy-preserved-v1')
  end,
  case when a.scan_status = 'pending' then null else 'legacy-preserved' end,
  case when a.scan_status = 'pending' then null else 'legacy-preserved' end,
  case when a.scan_status = 'pending' then null else 'legacy-preserved' end,
  case when a.scan_status = 'pending' then null else coalesce(a.scan_result_code, 'legacy_' || a.scan_status) end,
  case when a.scan_status = 'pending' then '{}'::jsonb else jsonb_build_object('source', 'legacy-preserved') end,
  case when a.scan_status = 'pending' then null else coalesce(a.scan_completed_at, now()) end
from public.image_assets a
where a.deleted_at is null
on conflict (asset_id) do nothing;

insert into public.asset_scan_events (
  job_id, asset_id, attempt_number, event_type, result_code, details
)
select
  j.id,
  j.asset_id,
  0,
  case when j.status in ('queued', 'leased', 'retry_wait') then 'queued' else j.status end,
  j.result_code,
  jsonb_build_object('source', 'migration-backfill')
from public.asset_scan_jobs j
where j.attempt_count = 0
  and not exists (
  select 1 from public.asset_scan_events e
  where e.job_id = j.id
)
on conflict do nothing;

do $$
begin
  if not exists (
    select 1 from pg_constraint
    where conrelid = 'public.image_assets'::regclass
      and conname = 'image_assets_scan_terminal_metadata'
  ) then
    alter table public.image_assets
      add constraint image_assets_scan_terminal_metadata check (
        (scan_status = 'pending' and scan_completed_at is null and scan_policy_version is null)
        or (
          scan_status in ('clean', 'flagged', 'failed')
          and scan_completed_at is not null
          and scan_policy_version is not null
          and scan_result_code is not null
        )
      ) not valid;
  end if;
end
$$;

alter table public.image_assets
  validate constraint image_assets_scan_terminal_metadata;

create or replace function public.protect_terminal_asset_scan_job()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
  if tg_op = 'DELETE' or old.status in ('clean', 'flagged', 'failed') then
    raise exception 'terminal asset scan jobs are immutable' using errcode = '55000';
  end if;
  return new;
end;
$$;
revoke all on function public.protect_terminal_asset_scan_job() from public, anon, authenticated, service_role;

drop trigger if exists asset_scan_jobs_terminal_immutable on public.asset_scan_jobs;
create trigger asset_scan_jobs_terminal_immutable
before update or delete on public.asset_scan_jobs
for each row execute function public.protect_terminal_asset_scan_job();

drop trigger if exists asset_scan_events_append_only on public.asset_scan_events;
create trigger asset_scan_events_append_only
before update or delete on public.asset_scan_events
for each row execute function public.reject_mutation();

create or replace function public.enqueue_asset_scan_job()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
declare
  created_job_id uuid;
  object_id uuid;
  asset_bucket text := case new.kind
    when 'original' then 'image-originals'
    when 'display' then 'image-display'
    else 'image-thumbnails'
  end;
begin
  if new.scan_status <> 'pending' then
    raise exception 'new image assets must start with a pending scan' using errcode = '23514';
  end if;
  if new.mime_type not in ('image/jpeg', 'image/png', 'image/webp')
     or new.checksum_sha256 is null
     or lower(new.checksum_sha256::text) !~ '^[0-9a-f]{64}$' then
    raise exception 'new image assets require scanner-compatible metadata' using errcode = '23514';
  end if;
  select o.id into object_id
  from storage.objects o
  where o.bucket_id = asset_bucket
    and o.name = new.storage_key
    and o.owner_id = new.owner_user_id::text
    and lower(coalesce(o.metadata ->> 'mimetype', '')) = lower(new.mime_type)
    and coalesce(o.metadata ->> 'size', '') = new.byte_size::text
  limit 1;
  if object_id is null then
    raise exception 'new image assets require a matching Storage object' using errcode = '23514';
  end if;

  insert into public.asset_scan_jobs (
    asset_id, expected_storage_object_id, storage_bucket, storage_key,
    mime_type, byte_size, width, height, checksum_sha256, scan_policy_version
  ) values (
    new.id, object_id, asset_bucket, new.storage_key,
    new.mime_type, new.byte_size, new.width, new.height,
    new.checksum_sha256, 'mt-asset-scan-2026-07-v1'
  )
  on conflict (asset_id) do nothing
  returning id into created_job_id;

  if created_job_id is not null then
    insert into public.asset_scan_events (
      job_id, asset_id, attempt_number, event_type, details
    ) values (
      created_job_id, new.id, 0, 'queued', jsonb_build_object('source', 'image-asset-insert')
    );
  end if;
  return new;
end;
$$;
revoke all on function public.enqueue_asset_scan_job() from public, anon, authenticated, service_role;

drop trigger if exists image_assets_enqueue_scan_job on public.image_assets;
create trigger image_assets_enqueue_scan_job
after insert on public.image_assets
for each row execute function public.enqueue_asset_scan_job();

create or replace function public.scanner_claim_asset_scan(
  worker_id text,
  lease_seconds integer default 300
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  requested_worker text := btrim(worker_id);
  requested_lease_seconds integer := lease_seconds;
  job_row public.asset_scan_jobs%rowtype;
  asset_row public.image_assets%rowtype;
  image_row public.images%rowtype;
  previous_lease_token uuid;
  previous_lease_owner text;
  new_lease_token uuid;
  claim_time timestamptz;
  loop_count integer;
begin
  if requested_worker is null
     or requested_worker !~ '^[A-Za-z0-9][A-Za-z0-9._:@-]{0,119}$' then
    return jsonb_build_object('error', jsonb_build_object(
      'code', 'SCAN_WORKER_ID_INVALID',
      'message', 'A stable worker identifier is required.'
    ));
  end if;
  if requested_lease_seconds is null or requested_lease_seconds not between 30 and 900 then
    return jsonb_build_object('error', jsonb_build_object(
      'code', 'SCAN_LEASE_INVALID',
      'message', 'Use a lease from 30 to 900 seconds.'
    ));
  end if;

  for loop_count in 1..10 loop
    job_row := null;
    select j.* into job_row
    from public.asset_scan_jobs j
    join public.image_assets a on a.id = j.asset_id and a.deleted_at is null
    join public.images i on i.id = a.image_id and i.deleted_at is null
    where (
      (j.status in ('queued', 'retry_wait') and j.available_at <= now())
      or (j.status = 'leased' and j.lease_expires_at <= now())
    )
    order by
      case when j.status = 'leased' and j.attempt_count >= j.max_attempts then 0 else 1 end,
      j.available_at,
      j.created_at,
      j.id
    for update of j skip locked
    limit 1;

    if job_row.id is null then
      return jsonb_build_object('job', null);
    end if;

    select i.* into image_row
    from public.images i
    join public.image_assets a on a.image_id = i.id
    where a.id = job_row.asset_id
    for update of i;
    select * into asset_row from public.image_assets a
    where a.id = job_row.asset_id for update;

    if job_row.status = 'leased' and job_row.lease_expires_at <= now() then
      previous_lease_token := job_row.lease_token;
      previous_lease_owner := job_row.lease_owner;
      insert into public.asset_scan_events (
        job_id, asset_id, attempt_number, event_type, worker_id, result_code
      ) values (
        job_row.id, job_row.asset_id, job_row.attempt_count, 'lease_expired',
        previous_lease_owner, 'scan_lease_expired'
      ) on conflict do nothing;

      if job_row.attempt_count >= job_row.max_attempts then
        update public.asset_scan_jobs j set
          status = 'failed',
          lease_token = null,
          lease_owner = null,
          lease_expires_at = null,
          last_lease_token = previous_lease_token,
          last_completed_attempt = job_row.attempt_count,
          last_outcome = 'failed',
          last_result_fingerprint = null,
          result_code = 'scan_retry_exhausted',
          result_details = jsonb_build_object('cause', 'lease_expired'),
          completed_at = now(),
          updated_at = now()
        where j.id = job_row.id;
        update public.image_assets a set
          scan_status = 'failed',
          scan_result_code = 'scan_retry_exhausted',
          scan_completed_at = now(),
          scan_policy_version = job_row.scan_policy_version
        where a.id = job_row.asset_id;
        insert into public.asset_scan_events (
          job_id, asset_id, attempt_number, event_type, worker_id, result_code, details
        ) values (
          job_row.id, job_row.asset_id, job_row.attempt_count, 'failed',
          requested_worker, 'scan_retry_exhausted', jsonb_build_object('cause', 'lease_expired')
        ) on conflict do nothing;
        insert into public.audit_logs (
          actor_user_id, actor_role, action, target_type, target_id, request_id,
          reason_code, before_state, after_state, policy_version, result
        ) values (
          null, null, 'asset.scan.failed', 'image_asset', job_row.asset_id::text,
          job_row.id::text || ':' || job_row.attempt_count::text, 'scan_retry_exhausted',
          jsonb_build_object('status', 'leased', 'attempt_number', job_row.attempt_count),
          jsonb_build_object('status', 'failed', 'result_code', 'scan_retry_exhausted'),
          job_row.scan_policy_version, 'success'
        );
        insert into public.notifications (recipient_user_id, type, payload)
        values (
          asset_row.owner_user_id,
          'asset_scan_blocked',
          jsonb_build_object(
            'image_id', asset_row.image_id,
            'asset_id', asset_row.id,
            'kind', asset_row.kind,
            'scan_status', 'failed',
            'result_code', 'scan_retry_exhausted'
          )
        );
        continue;
      end if;
    end if;

    new_lease_token := gen_random_uuid();
    claim_time := now();
    update public.asset_scan_jobs j set
      status = 'leased',
      attempt_count = j.attempt_count + 1,
      lease_token = new_lease_token,
      lease_owner = requested_worker,
      lease_expires_at = claim_time + make_interval(secs => requested_lease_seconds),
      updated_at = claim_time
    where j.id = job_row.id
    returning * into job_row;

    insert into public.asset_scan_events (
      job_id, asset_id, attempt_number, event_type, worker_id, details
    ) values (
      job_row.id,
      job_row.asset_id,
      job_row.attempt_count,
      'claimed',
      requested_worker,
      jsonb_build_object('lease_expires_at', job_row.lease_expires_at)
    ) on conflict do nothing;

    return jsonb_build_object('job', jsonb_build_object(
      'asset_id', asset_row.id,
      'image_id', asset_row.image_id,
      'kind', asset_row.kind,
      'storage_bucket', job_row.storage_bucket,
      'storage_key', job_row.storage_key,
      'mime_type', job_row.mime_type,
      'byte_size', job_row.byte_size,
      'width', job_row.width,
      'height', job_row.height,
      'checksum_sha256', job_row.checksum_sha256,
      'lease_token', job_row.lease_token,
      'attempt_number', job_row.attempt_count,
      'lease_expires_at', job_row.lease_expires_at
    ));
  end loop;
  return jsonb_build_object('job', null);
end;
$$;

create or replace function public.scanner_retry_asset_scan(
  asset_id uuid,
  lease_token uuid,
  error_code text,
  retry_after_seconds integer
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  target_asset_id alias for $1;
  provided_lease_token alias for $2;
  provided_error_code text := lower(btrim(error_code));
  requested_retry_seconds integer := retry_after_seconds;
  job_row public.asset_scan_jobs%rowtype;
  asset_row public.image_assets%rowtype;
  image_row public.images%rowtype;
  lease_worker text;
  request_fingerprint text;
begin
  if provided_error_code is null or provided_error_code !~ '^[a-z][a-z0-9_]{0,63}$' then
    return jsonb_build_object('error', jsonb_build_object(
      'code', 'SCAN_RESULT_INVALID',
      'message', 'Use a stable retry error code.'
    ));
  end if;
  if requested_retry_seconds is null or requested_retry_seconds not between 1 and 3600 then
    return jsonb_build_object('error', jsonb_build_object(
      'code', 'SCAN_RETRY_DELAY_INVALID',
      'message', 'Use a retry delay from 1 to 3600 seconds.'
    ));
  end if;
  request_fingerprint := encode(sha256(convert_to(jsonb_build_object(
    'error_code', provided_error_code,
    'retry_after_seconds', requested_retry_seconds
  )::text, 'UTF8')), 'hex');

  select * into job_row from public.asset_scan_jobs j
  where j.asset_id = target_asset_id for update;
  if job_row.id is null then
    return jsonb_build_object('error', jsonb_build_object(
      'code', 'SCAN_JOB_NOT_FOUND',
      'message', 'The asset scan job is unavailable.'
    ));
  end if;
  if job_row.last_lease_token = provided_lease_token
     and job_row.last_result_fingerprint is not null
     and (
       job_row.last_outcome = 'retry'
       or (job_row.last_outcome = 'failed' and job_row.result_code = 'scan_retry_exhausted')
     ) then
    if job_row.last_result_fingerprint is distinct from request_fingerprint then
      return jsonb_build_object('error', jsonb_build_object(
        'code', 'SCAN_COMPLETION_CONFLICT',
        'message', 'This lease token was already completed with different retry data.'
      ));
    end if;
    return jsonb_build_object(
      'retried', job_row.last_outcome = 'retry',
      'terminal', job_row.status = 'failed',
      'idempotent', true,
      'asset_id', target_asset_id,
      'attempt_number', job_row.last_completed_attempt,
      'status', job_row.status,
      'available_at', job_row.available_at
    );
  end if;
  if job_row.status <> 'leased' or job_row.lease_token is distinct from provided_lease_token then
    return jsonb_build_object('error', jsonb_build_object(
      'code', 'SCAN_LEASE_CONFLICT',
      'message', 'The scan lease is no longer current.'
    ));
  end if;
  if job_row.lease_expires_at <= now() then
    return jsonb_build_object('error', jsonb_build_object(
      'code', 'SCAN_LEASE_EXPIRED',
      'message', 'The scan lease expired before retry was requested.'
    ));
  end if;
  lease_worker := job_row.lease_owner;

  select * into asset_row from public.image_assets a
  where a.id = target_asset_id;
  select * into image_row from public.images i
  where i.id = asset_row.image_id for update;
  select * into asset_row from public.image_assets a
  where a.id = target_asset_id for update;

  if job_row.attempt_count >= job_row.max_attempts then
    update public.asset_scan_jobs j set
      status = 'failed',
      lease_token = null,
      lease_owner = null,
      lease_expires_at = null,
      last_lease_token = provided_lease_token,
      last_completed_attempt = job_row.attempt_count,
      last_outcome = 'failed',
      last_result_fingerprint = request_fingerprint,
      result_code = 'scan_retry_exhausted',
      result_details = jsonb_build_object('last_error_code', provided_error_code),
      completed_at = now(),
      updated_at = now()
    where j.id = job_row.id
    returning * into job_row;
    update public.image_assets a set
      scan_status = 'failed',
      scan_result_code = 'scan_retry_exhausted',
      scan_completed_at = now(),
      scan_policy_version = job_row.scan_policy_version
    where a.id = target_asset_id;
    insert into public.asset_scan_events (
      job_id, asset_id, attempt_number, event_type, worker_id, result_code, details
    ) values (
      job_row.id, target_asset_id, job_row.attempt_count, 'failed',
      lease_worker, 'scan_retry_exhausted', jsonb_build_object('last_error_code', provided_error_code)
    ) on conflict do nothing;
    insert into public.notifications (recipient_user_id, type, payload)
    values (
      asset_row.owner_user_id,
      'asset_scan_blocked',
      jsonb_build_object(
        'image_id', asset_row.image_id,
        'asset_id', asset_row.id,
        'kind', asset_row.kind,
        'scan_status', 'failed',
        'result_code', 'scan_retry_exhausted'
      )
    );
  else
    update public.asset_scan_jobs j set
      status = 'retry_wait',
      available_at = now() + make_interval(secs => requested_retry_seconds),
      lease_token = null,
      lease_owner = null,
      lease_expires_at = null,
      last_lease_token = provided_lease_token,
      last_completed_attempt = job_row.attempt_count,
      last_outcome = 'retry',
      last_result_fingerprint = request_fingerprint,
      result_code = provided_error_code,
      result_details = jsonb_build_object('retry_after_seconds', requested_retry_seconds),
      updated_at = now()
    where j.id = job_row.id
    returning * into job_row;
    insert into public.asset_scan_events (
      job_id, asset_id, attempt_number, event_type, worker_id, result_code, details
    ) values (
      job_row.id, target_asset_id, job_row.attempt_count, 'retry_scheduled',
      lease_worker, provided_error_code,
      jsonb_build_object('available_at', job_row.available_at)
    ) on conflict do nothing;
  end if;

  insert into public.audit_logs (
    actor_user_id, actor_role, action, target_type, target_id, request_id,
    reason_code, before_state, after_state, policy_version, result
  ) values (
    null, null,
    case when job_row.status = 'failed' then 'asset.scan.failed' else 'asset.scan.retry' end,
    'image_asset', target_asset_id::text,
    job_row.id::text || ':' || job_row.attempt_count::text, provided_error_code,
    jsonb_build_object('status', 'leased', 'attempt_number', job_row.attempt_count),
    jsonb_build_object('status', job_row.status, 'result_code', job_row.result_code),
    job_row.scan_policy_version, 'success'
  );

  return jsonb_build_object(
    'retried', job_row.status = 'retry_wait',
    'terminal', job_row.status = 'failed',
    'idempotent', false,
    'asset_id', target_asset_id,
    'attempt_number', job_row.attempt_count,
    'status', job_row.status,
    'available_at', job_row.available_at
  );
end;
$$;

create or replace function public.scanner_complete_asset_scan(
  asset_id uuid,
  lease_token uuid,
  result jsonb
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  target_asset_id alias for $1;
  provided_lease_token alias for $2;
  provided_result alias for $3;
  required_result_keys constant text[] := array[
    'outcome', 'result_code', 'scanner_version', 'engine_name', 'engine_version',
    'observed_mime_type', 'observed_byte_size', 'observed_width',
    'observed_height', 'observed_checksum_sha256'
  ];
  allowed_failed_result_codes constant text[] := array[
    'download_size_limit_exceeded', 'byte_size_mismatch', 'checksum_mismatch',
    'file_signature_invalid', 'mime_type_mismatch', 'storage_object_missing',
    'multiple_frames_not_allowed', 'decoded_format_mismatch',
    'image_size_limit_exceeded', 'dimension_mismatch', 'decompression_bomb',
    'image_decode_failed'
  ];
  unsupported_fields text;
  job_row public.asset_scan_jobs%rowtype;
  asset_row public.image_assets%rowtype;
  image_row public.images%rowtype;
  object_row storage.objects%rowtype;
  outcome_value text;
  result_code_value text;
  scanner_version_value text;
  engine_name_value text;
  engine_version_value text;
  observed_mime_type_value text;
  observed_checksum_value text;
  observed_byte_size_value bigint;
  observed_width_value integer;
  observed_height_value integer;
  lease_worker text;
  result_fingerprint text;
  all_assets_clean boolean;
  scan_policy_constant constant text := 'mt-asset-scan-2026-07-v1';
begin
  if provided_result is null or jsonb_typeof(provided_result) <> 'object' then
    return jsonb_build_object('error', jsonb_build_object(
      'code', 'SCAN_RESULT_INVALID',
      'message', 'Scanner result must be an object.'
    ));
  end if;
  select string_agg(key, ', ' order by key) into unsupported_fields
  from jsonb_object_keys(provided_result) keys(key)
  where key <> all(required_result_keys);
  if unsupported_fields is not null or not (provided_result ?& required_result_keys) then
    return jsonb_build_object('error', jsonb_build_object(
      'code', 'SCAN_RESULT_INVALID',
      'message', 'Scanner result fields do not match the completion contract.'
    ));
  end if;
  if jsonb_typeof(provided_result -> 'outcome') <> 'string'
     or jsonb_typeof(provided_result -> 'result_code') <> 'string'
     or jsonb_typeof(provided_result -> 'scanner_version') <> 'string'
     or jsonb_typeof(provided_result -> 'engine_name') <> 'string'
     or jsonb_typeof(provided_result -> 'engine_version') <> 'string'
     or jsonb_typeof(provided_result -> 'observed_mime_type') not in ('string', 'null')
     or jsonb_typeof(provided_result -> 'observed_byte_size') not in ('number', 'null')
     or jsonb_typeof(provided_result -> 'observed_width') not in ('number', 'null')
     or jsonb_typeof(provided_result -> 'observed_height') not in ('number', 'null')
     or jsonb_typeof(provided_result -> 'observed_checksum_sha256') not in ('string', 'null') then
    return jsonb_build_object('error', jsonb_build_object(
      'code', 'SCAN_RESULT_INVALID',
      'message', 'Scanner result field types do not match the completion contract.'
    ));
  end if;

  outcome_value := lower(btrim(provided_result ->> 'outcome'));
  result_code_value := lower(btrim(provided_result ->> 'result_code'));
  scanner_version_value := btrim(provided_result ->> 'scanner_version');
  engine_name_value := btrim(provided_result ->> 'engine_name');
  engine_version_value := btrim(provided_result ->> 'engine_version');
  observed_mime_type_value := lower(btrim(provided_result ->> 'observed_mime_type'));
  observed_checksum_value := lower(btrim(provided_result ->> 'observed_checksum_sha256'));

  if outcome_value not in ('clean', 'flagged', 'failed')
     or result_code_value is null
     or result_code_value !~ '^[a-z][a-z0-9_]{0,63}$'
     or scanner_version_value is null or length(scanner_version_value) not between 1 and 120
     or engine_name_value is null or length(engine_name_value) not between 1 and 120
     or engine_version_value is null or length(engine_version_value) not between 1 and 120
     or scanner_version_value <> 'mt-presence-phase2f-1'
     or engine_name_value <> 'clamav+pillow'
     or scanner_version_value ~ '[[:cntrl:]]'
     or engine_name_value ~ '[[:cntrl:]]'
     or engine_version_value ~ '[[:cntrl:]]' then
    return jsonb_build_object('error', jsonb_build_object(
      'code', 'SCAN_RESULT_INVALID',
      'message', 'Scanner outcome, result code, and engine identity are required.'
    ));
  end if;
  if outcome_value = 'clean' and result_code_value <> 'clean' then
    return jsonb_build_object('error', jsonb_build_object(
      'code', 'SCAN_RESULT_INVALID',
      'message', 'A clean outcome must use the clean result code.'
    ));
  end if;
  if outcome_value = 'flagged' and result_code_value <> 'malware_detected' then
    return jsonb_build_object('error', jsonb_build_object(
      'code', 'SCAN_RESULT_INVALID',
      'message', 'A flagged outcome must use an allowlisted finding code.'
    ));
  end if;
  if outcome_value = 'failed' and not (result_code_value = any(allowed_failed_result_codes)) then
    return jsonb_build_object('error', jsonb_build_object(
      'code', 'SCAN_RESULT_INVALID',
      'message', 'A failed outcome must use an allowlisted deterministic failure code.'
    ));
  end if;

  if jsonb_typeof(provided_result -> 'observed_byte_size') = 'number'
     and provided_result ->> 'observed_byte_size' ~ '^[0-9]{1,18}$' then
    begin
      observed_byte_size_value := (provided_result ->> 'observed_byte_size')::bigint;
    exception when numeric_value_out_of_range then
      observed_byte_size_value := null;
    end;
  end if;
  if jsonb_typeof(provided_result -> 'observed_width') = 'number'
     and provided_result ->> 'observed_width' ~ '^[0-9]{1,6}$' then
    observed_width_value := (provided_result ->> 'observed_width')::integer;
  end if;
  if jsonb_typeof(provided_result -> 'observed_height') = 'number'
     and provided_result ->> 'observed_height' ~ '^[0-9]{1,6}$' then
    observed_height_value := (provided_result ->> 'observed_height')::integer;
  end if;

  if (jsonb_typeof(provided_result -> 'observed_byte_size') = 'number'
      and observed_byte_size_value is null)
     or (jsonb_typeof(provided_result -> 'observed_width') = 'number'
      and observed_width_value is null)
     or (jsonb_typeof(provided_result -> 'observed_height') = 'number'
      and observed_height_value is null)
     or observed_byte_size_value < 0
     or observed_width_value < 0
     or observed_height_value < 0
     or (observed_mime_type_value is not null
      and observed_mime_type_value not in ('image/jpeg', 'image/png', 'image/webp'))
     or (observed_checksum_value is not null
      and observed_checksum_value !~ '^[0-9a-f]{64}$') then
    return jsonb_build_object('error', jsonb_build_object(
      'code', 'SCAN_RESULT_INVALID',
      'message', 'Observed asset metadata is malformed.'
    ));
  end if;

  if outcome_value = 'clean' and (
    observed_mime_type_value is null
    or observed_mime_type_value not in ('image/jpeg', 'image/png', 'image/webp')
    or observed_byte_size_value is null or observed_byte_size_value < 1
    or observed_width_value is null or observed_width_value < 1
    or observed_height_value is null or observed_height_value < 1
    or observed_checksum_value is null
    or observed_checksum_value !~ '^[0-9a-f]{64}$'
  ) then
    return jsonb_build_object('error', jsonb_build_object(
      'code', 'SCAN_RESULT_INVALID',
      'message', 'Clean results require complete observed asset metadata.'
    ));
  end if;
  if outcome_value = 'flagged' and (
    observed_mime_type_value is null
    or observed_byte_size_value is null or observed_byte_size_value < 1
    or observed_checksum_value is null
    or (observed_width_value is null) <> (observed_height_value is null)
  ) then
    return jsonb_build_object('error', jsonb_build_object(
      'code', 'SCAN_RESULT_INVALID',
      'message', 'Flagged results require the observed byte identity.'
    ));
  end if;

  result_fingerprint := encode(sha256(convert_to(provided_result::text, 'UTF8')), 'hex');
  select * into job_row from public.asset_scan_jobs j
  where j.asset_id = target_asset_id for update;
  if job_row.id is null then
    return jsonb_build_object('error', jsonb_build_object(
      'code', 'SCAN_JOB_NOT_FOUND',
      'message', 'The asset scan job is unavailable.'
    ));
  end if;
  if job_row.last_lease_token = provided_lease_token
     and job_row.last_outcome in ('clean', 'flagged', 'failed') then
    if job_row.last_result_fingerprint is distinct from result_fingerprint then
      return jsonb_build_object('error', jsonb_build_object(
        'code', 'SCAN_COMPLETION_CONFLICT',
        'message', 'This lease token was already completed with a different result.'
      ));
    end if;
    return jsonb_build_object(
      'completed', true,
      'idempotent', true,
      'asset_id', target_asset_id,
      'attempt_number', job_row.last_completed_attempt,
      'scan_status', job_row.status,
      'result_code', job_row.result_code
    );
  end if;
  if job_row.status <> 'leased' or job_row.lease_token is distinct from provided_lease_token then
    return jsonb_build_object('error', jsonb_build_object(
      'code', 'SCAN_LEASE_CONFLICT',
      'message', 'The scan lease is no longer current.'
    ));
  end if;
  if job_row.lease_expires_at <= now() then
    return jsonb_build_object('error', jsonb_build_object(
      'code', 'SCAN_LEASE_EXPIRED',
      'message', 'The scan lease expired before completion.'
    ));
  end if;
  lease_worker := job_row.lease_owner;

  select i.* into image_row
  from public.images i
  join public.image_assets a on a.image_id = i.id
  where a.id = target_asset_id
  for update of i;
  select * into asset_row from public.image_assets a
  where a.id = target_asset_id and a.deleted_at is null for update;
  if asset_row.id is null or image_row.id is null then
    return jsonb_build_object('error', jsonb_build_object(
      'code', 'SCAN_ASSET_UNAVAILABLE',
      'message', 'The asset is no longer available for scanning.'
    ));
  end if;
  if asset_row.storage_key is distinct from job_row.storage_key
     or asset_row.mime_type is distinct from job_row.mime_type
     or asset_row.byte_size is distinct from job_row.byte_size
     or asset_row.width is distinct from job_row.width
     or asset_row.height is distinct from job_row.height
     or asset_row.checksum_sha256 is distinct from job_row.checksum_sha256 then
    return jsonb_build_object('error', jsonb_build_object(
      'code', 'SCAN_ASSET_CHANGED',
      'message', 'Asset metadata changed after this scan was claimed.'
    ));
  end if;

  select * into object_row from storage.objects o
  where o.id = job_row.expected_storage_object_id
    and o.bucket_id = job_row.storage_bucket
    and o.name = job_row.storage_key
    and o.owner_id = asset_row.owner_user_id::text
  for share;
  if object_row.id is null
     and not (outcome_value = 'failed' and result_code_value = 'storage_object_missing') then
    return jsonb_build_object('error', jsonb_build_object(
      'code', 'SCAN_STORAGE_OBJECT_CHANGED',
      'message', 'The registered Storage object is no longer available.'
    ));
  end if;
  if object_row.id is not null
     and (
       lower(coalesce(object_row.metadata ->> 'mimetype', '')) <> lower(job_row.mime_type)
       or coalesce(object_row.metadata ->> 'size', '') <> job_row.byte_size::text
     ) then
    return jsonb_build_object('error', jsonb_build_object(
      'code', 'SCAN_STORAGE_OBJECT_CHANGED',
      'message', 'The Storage object metadata no longer matches the claimed asset.'
    ));
  end if;
  if outcome_value = 'failed'
     and result_code_value = 'storage_object_missing'
     and object_row.id is not null then
    return jsonb_build_object('error', jsonb_build_object(
      'code', 'SCAN_OBSERVATION_MISMATCH',
      'message', 'The scanner reported a missing object that is still registered.'
    ));
  end if;

  if outcome_value = 'clean' and (
    observed_mime_type_value is distinct from lower(job_row.mime_type)
    or observed_byte_size_value is distinct from job_row.byte_size
    or observed_width_value is distinct from job_row.width
    or observed_height_value is distinct from job_row.height
    or observed_checksum_value is distinct from lower(job_row.checksum_sha256::text)
  ) then
    return jsonb_build_object('error', jsonb_build_object(
      'code', 'SCAN_OBSERVATION_MISMATCH',
      'message', 'Observed bytes do not match the registered asset metadata.'
    ));
  end if;
  if outcome_value = 'flagged' and (
    observed_mime_type_value is distinct from lower(job_row.mime_type)
    or observed_byte_size_value is distinct from job_row.byte_size
    or observed_checksum_value is distinct from lower(job_row.checksum_sha256::text)
    or (observed_width_value is not null and observed_width_value is distinct from job_row.width)
    or (observed_height_value is not null and observed_height_value is distinct from job_row.height)
  ) then
    return jsonb_build_object('error', jsonb_build_object(
      'code', 'SCAN_OBSERVATION_MISMATCH',
      'message', 'Observed flagged bytes do not match the registered asset metadata.'
    ));
  end if;

  update public.asset_scan_jobs j set
    status = outcome_value,
    lease_token = null,
    lease_owner = null,
    lease_expires_at = null,
    last_lease_token = provided_lease_token,
    last_completed_attempt = job_row.attempt_count,
    last_outcome = outcome_value,
    last_result_fingerprint = result_fingerprint,
    scanner_version = scanner_version_value,
    engine_name = engine_name_value,
    engine_version = engine_version_value,
    result_code = result_code_value,
    result_details = jsonb_build_object(
      'observed_mime_type', nullif(observed_mime_type_value, ''),
      'observed_byte_size', observed_byte_size_value,
      'observed_width', observed_width_value,
      'observed_height', observed_height_value,
      'observed_checksum_sha256', nullif(observed_checksum_value, '')
    ),
    completed_at = now(),
    updated_at = now(),
    scan_policy_version = scan_policy_constant
  where j.id = job_row.id
  returning * into job_row;

  update public.image_assets a set
    scan_status = outcome_value,
    scan_result_code = result_code_value,
    scan_completed_at = now(),
    scan_policy_version = scan_policy_constant
  where a.id = target_asset_id;

  insert into public.asset_scan_events (
    job_id, asset_id, attempt_number, event_type, worker_id, result_code, details
  ) values (
    job_row.id,
    target_asset_id,
    job_row.attempt_count,
    outcome_value,
    lease_worker,
    result_code_value,
    jsonb_build_object(
      'scanner_version', scanner_version_value,
      'engine_name', engine_name_value,
      'engine_version', engine_version_value
    )
  ) on conflict do nothing;

  insert into public.audit_logs (
    actor_user_id, actor_role, action, target_type, target_id, request_id,
    reason_code, before_state, after_state, policy_version, result
  ) values (
    null, null, 'asset.scan.completed', 'image_asset', target_asset_id::text,
    job_row.id::text || ':' || job_row.attempt_count::text, result_code_value,
    jsonb_build_object('scan_status', asset_row.scan_status, 'attempt_number', job_row.attempt_count),
    jsonb_build_object('scan_status', outcome_value, 'result_code', result_code_value),
    scan_policy_constant, 'success'
  );

  if outcome_value in ('flagged', 'failed') then
    insert into public.notifications (recipient_user_id, type, payload)
    values (
      asset_row.owner_user_id,
      'asset_scan_blocked',
      jsonb_build_object(
        'image_id', asset_row.image_id,
        'asset_id', asset_row.id,
        'kind', asset_row.kind,
        'scan_status', outcome_value,
        'result_code', result_code_value
      )
    );
  elsif outcome_value = 'clean' then
    select coalesce(bool_and(a.scan_status = 'clean'), false) and count(*) = 3
    into all_assets_clean
    from public.image_assets a
    where a.image_id = asset_row.image_id and a.deleted_at is null;
    if all_assets_clean and not exists (
      select 1 from public.notifications n
      where n.recipient_user_id = asset_row.owner_user_id
        and n.type = 'assets_scan_complete'
        and n.payload ->> 'image_id' = asset_row.image_id::text
    ) then
      insert into public.notifications (recipient_user_id, type, payload)
      values (
        asset_row.owner_user_id,
        'assets_scan_complete',
        jsonb_build_object('image_id', asset_row.image_id, 'scan_status', 'clean')
      );
    end if;
  end if;

  return jsonb_build_object(
    'completed', true,
    'idempotent', false,
    'asset_id', target_asset_id,
    'attempt_number', job_row.attempt_count,
    'scan_status', outcome_value,
    'result_code', result_code_value
  );
end;
$$;

revoke all on function public.scanner_claim_asset_scan(text, integer) from public, anon, authenticated;
revoke all on function public.scanner_retry_asset_scan(uuid, uuid, text, integer) from public, anon, authenticated;
revoke all on function public.scanner_complete_asset_scan(uuid, uuid, jsonb) from public, anon, authenticated;
grant execute on function public.scanner_claim_asset_scan(text, integer) to service_role;
grant execute on function public.scanner_retry_asset_scan(uuid, uuid, text, integer) to service_role;
grant execute on function public.scanner_complete_asset_scan(uuid, uuid, jsonb) to service_role;

commit;
