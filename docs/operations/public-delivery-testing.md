# Public Delivery Testing

This runbook covers the published-only Supabase read model used by Works and
public creator profiles. It is a separate boundary from the protected
Dashboard and Review Queue: the MT Web API returns projected metadata and
short-lived display/thumbnail URLs, never private originals or explicit
bucket/key fields in its browser DTOs.

## Required Gates

Run the secret-free gates on every change:

```bash
python3 scripts/validate_public_delivery.py
python3 scripts/test_public_delivery_boundary.py
```

The static validator checks migration, RPC, server projection, authoritative
Works source, CI, and deployment wiring. Static validation cannot prove
PostgreSQL RLS or Storage behavior.

The HTTP boundary starts an in-process Fake Supabase and the real `server.py`
handler. It requires no project URL, database password, service key, browser,
or network access. It proves:

- an unpublished work and creator are absent for anonymous callers;
- ordinary Approve remains unpublished;
- Admin+AAL2 Approve and Publish makes the work and creator visible;
- only display and thumbnail assets receive publishable-identity signatures;
- MT Web API browser DTOs omit email, owner ids, explicit Storage coordinates, review data, and
  non-public EXIF;
- unsafe or unavailable provider responses fail closed before signing;
- an authoritative empty result remains empty and never falls back to samples.

## Development Database Acceptance

The database acceptance inserts fixed disposable rows inside one PostgreSQL
transaction and rolls the transaction back. Run it only against the confirmed
development project:

```bash
set -a
source .env
set +a
MT_TEST_ENVIRONMENT=development python3 scripts/test_public_delivery_database.py
```

The runner refuses to start when `MT_TEST_ENVIRONMENT` is not `development` or
when `MT_ALLOW_PRODUCTION=yes`. A passing run must print both rollback and
post-transaction fixture-absence markers. Do not add this credentialed test to
the ordinary pull-request job; use a protected manual environment if it is
later automated.

## Required Markers

The secret-free boundary must include:

```text
public_delivery_approve_hidden=yes
public_delivery_publish_visible=yes
public_delivery_derivative_signing=yes
public_delivery_original_exposed=no
public_delivery_private_fields_exposed=no
public_delivery_authoritative_empty=yes
```

The development database acceptance must include:

```text
public_delivery_database_pg_proc_security=yes
public_delivery_database_acl_boundary=yes
public_delivery_database_published_only=yes
public_delivery_database_account_status=yes
public_delivery_database_storage_boundary=yes
public_delivery_database_creator_projection=yes
public_delivery_database_owner_cover=yes
public_delivery_database_status=yes
public_delivery_database_fixtures_rolled_back=yes
public_delivery_database_fixtures_absent=yes
```

## Residual Revocation Window

Removing a work from public RPC results is immediate. A derivative URL already
issued to a client can remain valid until its short expiry. Treat that TTL as a
documented revocation window; never sign originals, and do not lengthen the TTL
without a takedown-risk review.

## Provider Locator Boundary

The MT Web API does not expose `storage_bucket` or `storage_key` fields. The
current Supabase delivery implementation still uses an anonymously callable
published-work RPC internally so the server can sign approved derivatives with
only the publishable provider identity. That RPC descriptor, and the signed
provider URL itself, can structurally reveal the public derivative object path;
current object paths may include an owner UUID. This does not grant access to
originals or unpublished objects, but it is not an anonymity boundary for the
provider locator. Hiding that locator requires a separate delivery change:
owner-independent opaque public object paths, or a server-only credential plus
an image-byte proxy. Do not claim locator anonymity until one of those designs
is implemented and tested.
