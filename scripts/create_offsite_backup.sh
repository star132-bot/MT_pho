#!/usr/bin/env bash
set -euo pipefail
umask 077

root="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
required=(
  PGHOST PGDATABASE PGUSER PGPASSWORD SUPABASE_URL
  MT_OFFSITE_BACKUP_HOST MT_OFFSITE_SSH_KEY MT_OFFSITE_KNOWN_HOSTS
  MT_OFFSITE_GNUPG_HOME MT_OFFSITE_GPG_RECIPIENT MT_OFFSITE_LOCAL_DIR
)
missing=()
for name in "${required[@]}"; do
  if [[ -z "${!name:-}" ]]; then
    missing+=("$name")
  fi
done
if [[ -z "${SUPABASE_SECRET_KEY:-}${SUPABASE_SERVICE_ROLE_KEY:-}" ]]; then
  missing+=("SUPABASE_SECRET_KEY")
fi
if ((${#missing[@]})); then
  echo "Missing offsite backup environment variables: ${missing[*]}" >&2
  exit 2
fi

if [[ ! "$MT_OFFSITE_BACKUP_HOST" =~ ^[A-Za-z0-9.-]+$ ]]; then
  echo "MT_OFFSITE_BACKUP_HOST is invalid." >&2
  exit 3
fi
if [[ ! "${MT_OFFSITE_SSH_PORT:-22}" =~ ^[0-9]+$ ]]; then
  echo "MT_OFFSITE_SSH_PORT is invalid." >&2
  exit 3
fi
for path in "$MT_OFFSITE_SSH_KEY" "$MT_OFFSITE_KNOWN_HOSTS"; do
  if [[ ! -f "$path" || -L "$path" ]]; then
    echo "Offsite SSH material is missing or unsafe." >&2
    exit 3
  fi
done
if [[ ! -d "$MT_OFFSITE_GNUPG_HOME" || -L "$MT_OFFSITE_GNUPG_HOME" ]]; then
  echo "Offsite GnuPG home is missing or unsafe." >&2
  exit 3
fi

for command in flock gpg pg_dump pg_restore psql python3 rsync sha256sum tar; do
  if ! command -v "$command" >/dev/null 2>&1; then
    echo "Required offsite backup command is unavailable: $command" >&2
    exit 4
  fi
done

install -d -o root -g root -m 0700 "$MT_OFFSITE_LOCAL_DIR"
exec 9>"$MT_OFFSITE_LOCAL_DIR/.backup.lock"
if ! flock -n 9; then
  echo "An offsite backup is already running." >&2
  exit 5
fi

stage="$(mktemp -d "$MT_OFFSITE_LOCAL_DIR/.stage.XXXXXXXX")"
bundle=""
cipher_partial=""
cleanup() {
  rm -rf -- "$stage"
  [[ -z "$bundle" ]] || rm -f -- "$bundle"
  [[ -z "$cipher_partial" ]] || rm -f -- "$cipher_partial"
}
trap cleanup EXIT

batch_id="mt-presence-offsite-$(date -u +%Y%m%dT%H%M%SZ)"
inventory_before="$stage/storage-inventory.before.csv"
inventory="$stage/storage-inventory.csv"
storage_root="$stage/storage"
storage_manifest="$stage/storage-manifest.jsonl"
database_dir="$stage/database"
mkdir -p "$database_dir"

inventory_query="copy (
  select bucket_id, name, coalesce(metadata->>'size', '0') as expected_size, updated_at::text
  from storage.objects
  where bucket_id in ('image-display', 'image-originals', 'image-thumbnails', 'profile-avatars')
  order by bucket_id, name
) to stdout with (format csv, header true)"

write_inventory() {
  local destination="$1"
  psql \
    --no-psqlrc \
    --no-password \
    --quiet \
    --set=ON_ERROR_STOP=1 \
    --host="$PGHOST" \
    --port="${PGPORT:-5432}" \
    --username="$PGUSER" \
    --dbname="$PGDATABASE" \
    --command="$inventory_query" > "$destination"
}

write_inventory "$inventory_before"
MT_BACKUP_DIR="$database_dir" "$root/backup_production_database.sh"
dump_files=("$database_dir"/*.dump)
if ((${#dump_files[@]} != 1)); then
  echo "Offsite backup did not create exactly one database dump." >&2
  exit 6
fi
dump="${dump_files[0]}"
"$root/verify_production_backup.sh" "$dump" "$dump.sha256"
(
  cd "$database_dir"
  sha256sum "$(basename "$dump")" > "$(basename "$dump").sha256"
)

storage_summary="$(python3 "$root/export_production_storage.py" export \
  --inventory "$inventory_before" \
  --output "$storage_root" \
  --manifest "$storage_manifest")"
python3 "$root/export_production_storage.py" verify \
  --inventory "$inventory_before" \
  --output "$storage_root" \
  --manifest "$storage_manifest"
write_inventory "$inventory"
if ! cmp -s "$inventory_before" "$inventory"; then
  echo "Storage inventory changed during backup; the batch was discarded." >&2
  exit 7
fi
rm -f -- "$inventory_before"

cat > "$stage/BACKUP-MANIFEST.txt" <<EOF
format=mt-presence-offsite-v1
batch_id=$batch_id
created_at=$(date -u +%FT%TZ)
database_dump=$(basename "$dump")
$storage_summary
EOF
(
  cd "$stage"
  find BACKUP-MANIFEST.txt database storage storage-inventory.csv storage-manifest.jsonl -type f -print0 \
    | sort -z \
    | xargs -0 sha256sum > FILES.sha256
)

bundle="$MT_OFFSITE_LOCAL_DIR/.${batch_id}.tar"
tar --format=pax --create --file="$bundle" --directory="$stage" .
cipher_partial="$MT_OFFSITE_LOCAL_DIR/.${batch_id}.tar.gpg.partial"
gpg \
  --homedir "$MT_OFFSITE_GNUPG_HOME" \
  --batch \
  --yes \
  --trust-model always \
  --recipient "$MT_OFFSITE_GPG_RECIPIENT" \
  --output "$cipher_partial" \
  --encrypt "$bundle"

cipher="$MT_OFFSITE_LOCAL_DIR/${batch_id}.tar.gpg"
mv -- "$cipher_partial" "$cipher"
cipher_partial=""
chmod 0600 "$cipher"
(
  cd "$MT_OFFSITE_LOCAL_DIR"
  sha256sum "$(basename "$cipher")" > "$(basename "$cipher").sha256"
  sha256sum --check --status "$(basename "$cipher").sha256"
)

rsync_shell="ssh -i $MT_OFFSITE_SSH_KEY -p ${MT_OFFSITE_SSH_PORT:-22} -o BatchMode=yes -o IdentitiesOnly=yes -o StrictHostKeyChecking=yes -o UserKnownHostsFile=$MT_OFFSITE_KNOWN_HOSTS"
rsync \
  --recursive \
  --times \
  --perms \
  --checksum \
  --ignore-existing \
  --rsh="$rsync_shell" \
  "$cipher" "$cipher.sha256" \
  "mtpresence-backup@$MT_OFFSITE_BACKUP_HOST:incoming/"

echo "offsite_backup_completed=$batch_id"
