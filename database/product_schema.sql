-- MT Presence product schema (PostgreSQL 14+ / Supabase compatible).
-- This is the Phase 0 target model. Authentication is delegated to a mature
-- provider; users.auth_subject maps the provider identity into this schema.

CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TYPE account_status AS ENUM ('pending_verification', 'active', 'suspended', 'banned', 'deletion_requested', 'deleted');
CREATE TYPE role_code AS ENUM ('user', 'reviewer', 'admin', 'super_admin');
CREATE TYPE processing_status AS ENUM ('pending', 'uploading', 'processing', 'ready', 'failed', 'canceled');
CREATE TYPE workflow_status AS ENUM ('draft', 'submitted', 'in_review', 'changes_requested', 'rejected', 'approved');
CREATE TYPE publication_status AS ENUM ('never_published', 'published', 'unpublished', 'quarantined', 'archived', 'deleted');
CREATE TYPE submission_status AS ENUM ('submitted', 'in_review', 'changes_requested', 'rejected', 'approved', 'withdrawn', 'escalated');
CREATE TYPE review_decision AS ENUM ('request_changes', 'reject', 'approve', 'approve_and_publish', 'escalate', 'quarantine');

CREATE TABLE users (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  auth_subject text NOT NULL UNIQUE,
  email text NOT NULL,
  email_normalized text GENERATED ALWAYS AS (lower(email)) STORED UNIQUE,
  email_verified_at timestamptz,
  account_status account_status NOT NULL DEFAULT 'pending_verification',
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  last_active_at timestamptz
);

CREATE TABLE user_profiles (
  user_id uuid PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
  display_name text NOT NULL CHECK (length(display_name) BETWEEN 1 AND 120),
  avatar_url text,
  bio text,
  website_url text,
  country_code char(2),
  preferred_locale text NOT NULL DEFAULT 'en',
  timezone text NOT NULL DEFAULT 'UTC',
  copyright_name text,
  default_license_preference text,
  public_fields jsonb NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE user_roles (
  user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  role role_code NOT NULL,
  assigned_by uuid REFERENCES users(id) ON DELETE RESTRICT,
  reason text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (user_id, role)
);

CREATE TABLE folders (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  owner_user_id uuid NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
  parent_id uuid REFERENCES folders(id) ON DELETE RESTRICT,
  name text NOT NULL CHECK (length(name) BETWEEN 1 AND 120),
  sort_order integer NOT NULL DEFAULT 0,
  is_system boolean NOT NULL DEFAULT false,
  deleted_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX folders_owner_active_name_key ON folders (owner_user_id, lower(name)) WHERE deleted_at IS NULL;

CREATE TABLE images (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  owner_user_id uuid NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
  folder_id uuid REFERENCES folders(id) ON DELETE RESTRICT,
  current_version_id uuid,
  processing_status processing_status NOT NULL DEFAULT 'pending',
  workflow_status workflow_status NOT NULL DEFAULT 'draft',
  publication_status publication_status NOT NULL DEFAULT 'never_published',
  original_filename text NOT NULL,
  original_width integer CHECK (original_width > 0),
  original_height integer CHECK (original_height > 0),
  checksum_sha256 char(64),
  version integer NOT NULL DEFAULT 1 CHECK (version > 0),
  published_at timestamptz,
  unpublished_at timestamptz,
  deleted_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CHECK ((publication_status = 'published') = (published_at IS NOT NULL))
);

CREATE TABLE image_versions (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  image_id uuid NOT NULL REFERENCES images(id) ON DELETE RESTRICT,
  version_number integer NOT NULL CHECK (version_number > 0),
  title text NOT NULL DEFAULT '' CHECK (length(title) <= 180),
  caption text NOT NULL DEFAULT '' CHECK (length(caption) <= 500),
  description text NOT NULL DEFAULT '',
  alt_text text NOT NULL DEFAULT '' CHECK (length(alt_text) <= 500),
  tags jsonb NOT NULL DEFAULT '[]'::jsonb CHECK (jsonb_typeof(tags) = 'array'),
  content_category text,
  captured_at timestamptz,
  location_name text,
  gps_visibility text NOT NULL DEFAULT 'private' CHECK (gps_visibility IN ('private', 'approximate', 'public')),
  public_exif jsonb NOT NULL DEFAULT '{}'::jsonb,
  copyright_holder text CHECK (copyright_holder IS NULL OR length(copyright_holder) <= 160),
  copyright_year integer CHECK (copyright_year IS NULL OR copyright_year BETWEEN 1000 AND 2200),
  contains_recognizable_people boolean,
  model_release_status text CHECK (model_release_status IS NULL OR model_release_status IN ('not_applicable', 'available', 'not_available', 'pending')),
  property_release_status text CHECK (property_release_status IS NULL OR property_release_status IN ('not_applicable', 'available', 'not_available', 'pending')),
  rights_declared boolean NOT NULL DEFAULT false,
  ai_disclosure text CHECK (ai_disclosure IS NULL OR ai_disclosure IN ('none', 'ai_edited', 'ai_generated')),
  sensitive_content_disclosure text CHECK (sensitive_content_disclosure IS NULL OR sensitive_content_disclosure IN ('none', 'contains_sensitive_content')),
  created_by_user_id uuid NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
  created_at timestamptz NOT NULL DEFAULT now(),
  locked_at timestamptz,
  UNIQUE (image_id, version_number)
);
ALTER TABLE images ADD CONSTRAINT images_current_version_fk FOREIGN KEY (current_version_id) REFERENCES image_versions(id) ON DELETE RESTRICT;

CREATE TABLE image_assets (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  image_id uuid NOT NULL REFERENCES images(id) ON DELETE RESTRICT,
  owner_user_id uuid NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
  kind text NOT NULL CHECK (kind IN ('original', 'display', 'thumbnail')),
  storage_key text NOT NULL UNIQUE,
  mime_type text NOT NULL,
  byte_size bigint NOT NULL CHECK (byte_size > 0),
  width integer NOT NULL CHECK (width > 0),
  height integer NOT NULL CHECK (height > 0),
  checksum_sha256 char(64),
  scan_status text NOT NULL DEFAULT 'pending' CHECK (scan_status IN ('pending', 'clean', 'flagged', 'failed')),
  scan_result_code text,
  scan_completed_at timestamptz,
  scan_policy_version text,
  storage_visibility text NOT NULL DEFAULT 'private' CHECK (storage_visibility IN ('private', 'public')),
  deleted_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT image_assets_scan_terminal_metadata CHECK (
    (scan_status = 'pending' AND scan_completed_at IS NULL AND scan_policy_version IS NULL)
    OR (
      scan_status IN ('clean', 'flagged', 'failed')
      AND scan_completed_at IS NOT NULL
      AND scan_policy_version IS NOT NULL
      AND scan_result_code IS NOT NULL
    )
  ),
  UNIQUE (image_id, kind)
);

CREATE TABLE upload_intents (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  owner_user_id uuid NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
  image_id uuid NOT NULL UNIQUE DEFAULT gen_random_uuid(),
  folder_id uuid REFERENCES folders(id) ON DELETE RESTRICT,
  status text NOT NULL DEFAULT 'issued' CHECK (status IN ('issued', 'completed', 'expired', 'canceled')),
  original_filename text NOT NULL,
  original_width integer NOT NULL CHECK (original_width > 0),
  original_height integer NOT NULL CHECK (original_height > 0),
  checksum_sha256 char(64) NOT NULL,
  expected_assets jsonb NOT NULL CHECK (jsonb_typeof(expected_assets) = 'array'),
  expires_at timestamptz NOT NULL DEFAULT (now() + interval '2 hours'),
  completed_at timestamptz,
  canceled_at timestamptz,
  cleanup_status text NOT NULL DEFAULT 'not_required' CHECK (cleanup_status IN ('not_required', 'pending', 'complete', 'failed')),
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX upload_intents_owner_status_idx ON upload_intents (owner_user_id, status, created_at DESC);

CREATE TABLE asset_scan_jobs (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  asset_id uuid NOT NULL UNIQUE REFERENCES image_assets(id) ON DELETE RESTRICT,
  status text NOT NULL DEFAULT 'queued'
    CHECK (status IN ('queued', 'leased', 'retry_wait', 'clean', 'flagged', 'failed')),
  attempt_count integer NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
  max_attempts integer NOT NULL DEFAULT 5 CHECK (max_attempts BETWEEN 1 AND 20),
  available_at timestamptz NOT NULL DEFAULT now(),
  lease_token uuid,
  lease_owner text,
  lease_expires_at timestamptz,
  last_lease_token uuid,
  last_completed_attempt integer CHECK (last_completed_attempt IS NULL OR last_completed_attempt > 0),
  last_outcome text CHECK (last_outcome IS NULL OR last_outcome IN ('retry', 'clean', 'flagged', 'failed')),
  last_result_fingerprint char(64),
  expected_storage_object_id uuid,
  storage_bucket text NOT NULL CHECK (storage_bucket IN ('image-originals', 'image-display', 'image-thumbnails')),
  storage_key text NOT NULL,
  mime_type text NOT NULL,
  byte_size bigint NOT NULL CHECK (byte_size > 0),
  width integer NOT NULL CHECK (width > 0),
  height integer NOT NULL CHECK (height > 0),
  checksum_sha256 char(64),
  scan_policy_version text NOT NULL,
  scanner_version text,
  engine_name text,
  engine_version text,
  result_code text,
  result_details jsonb NOT NULL DEFAULT '{}'::jsonb
    CHECK (jsonb_typeof(result_details) = 'object' AND octet_length(result_details::text) <= 16384),
  completed_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CHECK (attempt_count <= max_attempts),
  CHECK (
    (status = 'leased' AND lease_token IS NOT NULL AND lease_owner IS NOT NULL AND lease_expires_at IS NOT NULL)
    OR (status <> 'leased' AND lease_token IS NULL AND lease_owner IS NULL AND lease_expires_at IS NULL)
  ),
  CHECK (
    (status IN ('clean', 'flagged', 'failed') AND completed_at IS NOT NULL AND result_code IS NOT NULL)
    OR (status NOT IN ('clean', 'flagged', 'failed') AND completed_at IS NULL)
  ),
  CONSTRAINT asset_scan_jobs_claim_prerequisites CHECK (
    status NOT IN ('queued', 'leased', 'retry_wait')
    OR (
      expected_storage_object_id IS NOT NULL
      AND checksum_sha256 IS NOT NULL
      AND lower(checksum_sha256::text) ~ '^[0-9a-f]{64}$'
    )
  )
);
CREATE INDEX asset_scan_jobs_claim_idx
  ON asset_scan_jobs (status, available_at, created_at)
  WHERE status IN ('queued', 'retry_wait', 'leased');
CREATE INDEX asset_scan_jobs_expired_lease_idx
  ON asset_scan_jobs (lease_expires_at)
  WHERE status = 'leased';

CREATE TABLE asset_scan_events (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  job_id uuid NOT NULL REFERENCES asset_scan_jobs(id) ON DELETE RESTRICT,
  asset_id uuid NOT NULL REFERENCES image_assets(id) ON DELETE RESTRICT,
  attempt_number integer NOT NULL CHECK (attempt_number >= 0),
  event_type text NOT NULL CHECK (event_type IN (
    'queued', 'claimed', 'lease_expired', 'retry_scheduled', 'clean', 'flagged', 'failed'
  )),
  worker_id text,
  result_code text,
  details jsonb NOT NULL DEFAULT '{}'::jsonb
    CHECK (jsonb_typeof(details) = 'object' AND octet_length(details::text) <= 16384),
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX asset_scan_events_asset_idx ON asset_scan_events (asset_id, created_at DESC);
CREATE INDEX asset_scan_events_job_idx ON asset_scan_events (job_id, created_at DESC);
CREATE UNIQUE INDEX asset_scan_events_job_attempt_type_key
  ON asset_scan_events (job_id, attempt_number, event_type);
ALTER TABLE asset_scan_jobs ENABLE ROW LEVEL SECURITY;
ALTER TABLE asset_scan_events ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON asset_scan_jobs FROM PUBLIC, anon, authenticated, service_role;
REVOKE ALL ON asset_scan_events FROM PUBLIC, anon, authenticated, service_role;

CREATE TABLE review_submissions (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  image_id uuid NOT NULL REFERENCES images(id) ON DELETE RESTRICT,
  image_version_id uuid NOT NULL REFERENCES image_versions(id) ON DELETE RESTRICT,
  submitted_by_user_id uuid NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
  idempotency_key uuid NOT NULL,
  status submission_status NOT NULL DEFAULT 'submitted',
  assigned_reviewer_id uuid REFERENCES users(id) ON DELETE RESTRICT,
  policy_version text NOT NULL,
  lock_version integer NOT NULL DEFAULT 1
    CONSTRAINT review_submissions_lock_version_positive CHECK (lock_version > 0),
  readiness_snapshot jsonb NOT NULL
    CONSTRAINT review_submissions_readiness_snapshot_object
    CHECK (
      jsonb_typeof(readiness_snapshot) = 'object'
      AND jsonb_typeof(readiness_snapshot -> 'checks') = 'array'
      AND jsonb_array_length(readiness_snapshot -> 'checks') = 5
    ),
  asset_snapshot jsonb NOT NULL
    CONSTRAINT review_submissions_asset_snapshot_complete CHECK (
    jsonb_typeof(asset_snapshot) = 'array'
    AND jsonb_array_length(asset_snapshot) = 3
  ),
  submitted_at timestamptz NOT NULL DEFAULT now(),
  review_started_at timestamptz,
  completed_at timestamptz
);
CREATE UNIQUE INDEX review_submissions_idempotency_key ON review_submissions (idempotency_key);
CREATE UNIQUE INDEX review_submissions_one_open_per_image ON review_submissions (image_id) WHERE status IN ('submitted', 'in_review', 'escalated');

CREATE TABLE review_decisions (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  submission_id uuid NOT NULL REFERENCES review_submissions(id) ON DELETE RESTRICT,
  reviewer_id uuid NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
  decision review_decision NOT NULL,
  reason_codes jsonb NOT NULL CHECK (jsonb_typeof(reason_codes) = 'array' AND jsonb_array_length(reason_codes) > 0),
  user_message text NOT NULL,
  internal_note text,
  checklist_result jsonb NOT NULL,
  policy_version text NOT NULL,
  idempotency_key text NOT NULL UNIQUE,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE notifications (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  recipient_user_id uuid NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
  type text NOT NULL,
  payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  read_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE takedown_cases (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  image_id uuid NOT NULL REFERENCES images(id) ON DELETE RESTRICT,
  requester_user_id uuid REFERENCES users(id) ON DELETE RESTRICT,
  reason_code text NOT NULL,
  evidence_reference text,
  status text NOT NULL CHECK (status IN ('open', 'investigating', 'restored', 'unpublished', 'closed')),
  assigned_admin_id uuid REFERENCES users(id) ON DELETE RESTRICT,
  legal_hold boolean NOT NULL DEFAULT false,
  created_at timestamptz NOT NULL DEFAULT now(),
  resolved_at timestamptz
);

CREATE TABLE audit_logs (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  actor_user_id uuid REFERENCES users(id) ON DELETE RESTRICT,
  actor_role role_code,
  action text NOT NULL,
  target_type text NOT NULL,
  target_id text NOT NULL,
  request_id text NOT NULL,
  reason_code text,
  before_state jsonb,
  after_state jsonb,
  policy_version text,
  result text NOT NULL CHECK (result IN ('success', 'failure')),
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE FUNCTION reject_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION '% is append-only', TG_TABLE_NAME;
END;
$$;

CREATE FUNCTION protect_terminal_asset_scan_job() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF TG_OP = 'DELETE' OR OLD.status IN ('clean', 'flagged', 'failed') THEN
    RAISE EXCEPTION 'terminal asset scan jobs are immutable' USING ERRCODE = '55000';
  END IF;
  RETURN NEW;
END;
$$;
CREATE TRIGGER asset_scan_jobs_terminal_immutable
BEFORE UPDATE OR DELETE ON asset_scan_jobs
FOR EACH ROW EXECUTE FUNCTION protect_terminal_asset_scan_job();

CREATE TRIGGER asset_scan_events_append_only
BEFORE UPDATE OR DELETE ON asset_scan_events
FOR EACH ROW EXECUTE FUNCTION reject_mutation();

CREATE FUNCTION protect_locked_image_version() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF OLD.locked_at IS NOT NULL THEN
    RAISE EXCEPTION 'locked image versions are immutable' USING ERRCODE = '55000';
  END IF;
  IF TG_OP = 'DELETE' THEN
    RETURN OLD;
  END IF;
  RETURN NEW;
END;
$$;
CREATE TRIGGER image_versions_locked_immutable
BEFORE UPDATE OR DELETE ON image_versions
FOR EACH ROW EXECUTE FUNCTION protect_locked_image_version();

CREATE FUNCTION protect_review_submission_snapshot() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'review submission snapshots are immutable' USING ERRCODE = '55000';
  END IF;
  IF NEW.image_id IS DISTINCT FROM OLD.image_id
     OR NEW.image_version_id IS DISTINCT FROM OLD.image_version_id
     OR NEW.submitted_by_user_id IS DISTINCT FROM OLD.submitted_by_user_id
     OR NEW.idempotency_key IS DISTINCT FROM OLD.idempotency_key
     OR NEW.policy_version IS DISTINCT FROM OLD.policy_version
     OR NEW.readiness_snapshot IS DISTINCT FROM OLD.readiness_snapshot
     OR NEW.asset_snapshot IS DISTINCT FROM OLD.asset_snapshot
     OR NEW.submitted_at IS DISTINCT FROM OLD.submitted_at THEN
    RAISE EXCEPTION 'review submission snapshots are immutable' USING ERRCODE = '55000';
  END IF;
  RETURN NEW;
END;
$$;
CREATE TRIGGER review_submissions_snapshot_immutable
BEFORE UPDATE OR DELETE ON review_submissions
FOR EACH ROW EXECUTE FUNCTION protect_review_submission_snapshot();

CREATE TRIGGER review_decisions_append_only BEFORE UPDATE OR DELETE ON review_decisions FOR EACH ROW EXECUTE FUNCTION reject_mutation();
CREATE TRIGGER audit_logs_append_only BEFORE UPDATE OR DELETE ON audit_logs FOR EACH ROW EXECUTE FUNCTION reject_mutation();

CREATE INDEX images_owner_status_idx ON images (owner_user_id, workflow_status, publication_status, updated_at DESC);
CREATE INDEX public_images_idx ON images (published_at DESC) WHERE publication_status = 'published' AND deleted_at IS NULL;
CREATE INDEX review_queue_idx ON review_submissions (status, assigned_reviewer_id, submitted_at);
CREATE INDEX audit_target_idx ON audit_logs (target_type, target_id, created_at DESC);
CREATE INDEX audit_actor_idx ON audit_logs (actor_user_id, created_at DESC);

-- Public consumers must use this view rather than the legacy visibility field.
CREATE VIEW public_works AS
SELECT i.id, v.title, v.caption, v.description, v.alt_text, v.tags,
       v.content_category, v.captured_at, v.location_name, v.public_exif,
       i.published_at
FROM images i
JOIN image_versions v ON v.id = i.current_version_id
WHERE i.publication_status = 'published' AND i.deleted_at IS NULL;
