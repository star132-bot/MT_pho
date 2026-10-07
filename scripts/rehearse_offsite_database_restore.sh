#!/usr/bin/env bash
set -euo pipefail
umask 077

root="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if (($# != 2)); then
  echo "Usage: rehearse_offsite_database_restore.sh <dump> <sha256-manifest>" >&2
  exit 2
fi

required=(
  PGHOST PGDATABASE PGUSER PGPASSWORD
  MT_RECOVERY_TARGET MT_RECOVERY_TARGET_REF MT_RECOVERY_PRODUCTION_REF
  MT_RECOVERY_CONFIRM MT_RECOVERY_ALLOW_HTTP_LOOPBACK
)
missing=()
for name in "${required[@]}"; do
  [[ -n "${!name:-}" ]] || missing+=("$name")
done
if ((${#missing[@]})); then
  echo "Missing recovery environment variables: ${missing[*]}" >&2
  exit 2
fi

target_ref="$MT_RECOVERY_TARGET_REF"
if [[ "$MT_RECOVERY_TARGET" != "isolated-supabase" \
  || "$MT_RECOVERY_ALLOW_HTTP_LOOPBACK" != "1" \
  || ! "$target_ref" =~ ^local-mt-presence-recovery-[a-z0-9-]{8,80}$ \
  || ! "$MT_RECOVERY_PRODUCTION_REF" =~ ^[a-z0-9-]{8,80}$ \
  || "$target_ref" == "$MT_RECOVERY_PRODUCTION_REF" \
  || "$MT_RECOVERY_CONFIRM" != "$target_ref" ]]; then
  echo "Recovery target confirmation or environment boundary is invalid." >&2
  exit 3
fi
case "$PGHOST" in
  127.0.0.1|localhost|::1) ;;
  *)
    echo "Automated recovery rehearsal only permits a loopback Supabase target." >&2
    exit 3
    ;;
esac
if [[ -z "$PGDATABASE" || -z "$PGUSER" || ! "${PGPORT:-5432}" =~ ^[0-9]+$ ]]; then
  echo "Recovery PostgreSQL target is invalid." >&2
  exit 3
fi

dump="$1"
manifest="$2"
for path in "$dump" "$manifest"; do
  if [[ -L "$path" || ! -f "$path" ]]; then
    echo "Recovery input is missing or unsafe." >&2
    exit 3
  fi
done
for command in pg_restore psql sha256sum; do
  command -v "$command" >/dev/null 2>&1 || {
    echo "Recovery dependency is unavailable: $command" >&2
    exit 4
  }
done

bash "$root/verify_production_backup.sh" "$dump" "$manifest"
psql_base=(
  psql --no-psqlrc --no-password --quiet --tuples-only --no-align
  --set=ON_ERROR_STOP=1 --host="$PGHOST" --port="${PGPORT:-5432}"
  --username="$PGUSER" --dbname="$PGDATABASE"
)
guard="$("${psql_base[@]}" --command="select coalesce(shobj_description(oid, 'pg_database'), '') from pg_database where datname = current_database()")"
if [[ "$guard" != "mt-presence-recovery:$target_ref" ]]; then
  echo "Recovery database does not carry the expected disposable-target guard." >&2
  exit 5
fi
extra_schemas="$("${psql_base[@]}" --command="select count(*) from pg_namespace where nspname not like 'pg_%' and nspname not in ('information_schema', 'public')")"
public_objects="$("${psql_base[@]}" --command="select count(*) from pg_class c join pg_namespace n on n.oid=c.relnamespace where n.nspname='public' and c.relkind in ('r','p','v','m','S','f')")"
if [[ "$extra_schemas" != "0" || "$public_objects" != "0" ]]; then
  echo "Recovery database is not an empty disposable target." >&2
  exit 5
fi

"${psql_base[@]}" --command="drop schema if exists public cascade; create schema public"
pg_restore \
  --host="$PGHOST" \
  --port="${PGPORT:-5432}" \
  --username="$PGUSER" \
  --dbname="$PGDATABASE" \
  --single-transaction \
  --exit-on-error \
  "$dump"

evidence="$("${psql_base[@]}" --field-separator='=' --command="
select 'database_schemas', count(*) from pg_namespace where nspname in ('auth','public','storage');
select 'database_tables', count(*) from pg_class c join pg_namespace n on n.oid=c.relnamespace where n.nspname in ('auth','public','storage') and c.relkind in ('r','p');
select 'database_functions', count(*) from pg_proc p join pg_namespace n on n.oid=p.pronamespace where n.nspname='public';
select 'database_rls_tables', count(*) from pg_class c join pg_namespace n on n.oid=c.relnamespace where n.nspname in ('public','storage') and c.relrowsecurity;
select 'database_policies', count(*) from pg_policy;
select 'database_acl_rows', count(*) from information_schema.role_table_grants where grantee in ('anon','authenticated','service_role');
select 'auth_users', count(*) from auth.users;
select 'application_users', count(*) from public.users;
select 'application_images', count(*) from public.images;
select 'storage_objects', count(*) from storage.objects;
")"
for key in database_schemas database_tables database_functions database_rls_tables database_policies database_acl_rows auth_users application_users application_images storage_objects; do
  value="$(printf '%s\n' "$evidence" | awk -F= -v wanted="$key" '$1 == wanted { print $2 }')"
  if [[ ! "$value" =~ ^[0-9]+$ ]]; then
    echo "Recovery evidence query returned an invalid value: $key" >&2
    exit 6
  fi
  case "$key" in
    database_schemas|database_tables|database_functions|database_rls_tables|database_policies|database_acl_rows)
      if [[ "$value" == "0" ]]; then
        echo "Recovery database is missing required security metadata: $key" >&2
        exit 6
      fi
      ;;
  esac
  echo "$key=$value"
done
echo "offsite_database_restore=passed"
