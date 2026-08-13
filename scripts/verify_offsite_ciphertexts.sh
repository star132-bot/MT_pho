#!/usr/bin/env bash
set -euo pipefail
umask 077

backup_root="${1:-/srv/mt-presence-backup}"
minimum_free_percent="${MT_OFFSITE_MIN_FREE_PERCENT:-15}"
receive_user="${MT_OFFSITE_RECEIVE_USER:-mtpresence-backup}"
if [[ ! -d "$backup_root" || -L "$backup_root" || ! "$minimum_free_percent" =~ ^[0-9]+$ ]]; then
  echo "Offsite backup verifier configuration is invalid." >&2
  exit 2
fi
for command in cp sha256sum; do
  if ! command -v "$command" >/dev/null 2>&1; then
    echo "Offsite backup verifier dependency is missing." >&2
    exit 2
  fi
done

incoming="$backup_root/incoming"
vault="$backup_root/vault"
staging_root="$backup_root/.staging"
if ! receive_uid="$(id -u "$receive_user" 2>/dev/null)"; then
  echo "Offsite receive account is unavailable." >&2
  exit 2
fi
verifier_uid="$(id -u)"
install -d -m 0700 "$vault" "$staging_root"
lock_dir="$backup_root/.verify.lock"
if ! mkdir -- "$lock_dir" 2>/dev/null; then
  echo "An offsite backup verification is already running." >&2
  exit 2
fi
cleanup_lock() {
  local status="$?"
  rmdir -- "$lock_dir" >/dev/null 2>&1 || true
  exit "$status"
}
trap cleanup_lock EXIT

file_mode() {
  local path="$1"
  if stat -c '%a' "$path" >/dev/null 2>&1; then
    stat -c '%a' "$path"
  else
    stat -f '%Lp' "$path"
  fi
}

file_mtime() {
  local path="$1"
  if stat -c '%Y' "$path" >/dev/null 2>&1; then
    stat -c '%Y' "$path"
  else
    stat -f '%m' "$path"
  fi
}

file_uid() {
  local path="$1"
  if stat -c '%u' "$path" >/dev/null 2>&1; then
    stat -c '%u' "$path"
  else
    stat -f '%u' "$path"
  fi
}

safe_file() {
  local path="$1"
  local expected_uid="$2"
  if [[ -L "$path" || ! -f "$path" || "$(file_mode "$path")" != "600" || "$(file_uid "$path")" != "$expected_uid" ]]; then
    echo "Offsite backup contains an unsafe file." >&2
    exit 4
  fi
}

if [[ -L "$incoming" || ! -d "$incoming" || "$(file_mode "$incoming")" != "700" || "$(file_uid "$incoming")" != "$receive_uid" ]]; then
  echo "Offsite incoming directory ownership or mode is unsafe." >&2
  exit 2
fi
for directory in "$vault" "$staging_root"; do
  if [[ -L "$directory" || ! -d "$directory" || "$(file_mode "$directory")" != "700" || "$(file_uid "$directory")" != "$verifier_uid" ]]; then
    echo "Offsite verifier directory ownership or mode is unsafe." >&2
    exit 2
  fi
done

batch_name() {
  local filename="$1"
  if [[ ! "$filename" =~ ^(mt-presence-offsite-[0-9]{8}T[0-9]{6}Z)\.tar\.gpg$ ]]; then
    echo "Offsite backup filename is invalid." >&2
    exit 4
  fi
  printf '%s\n' "${BASH_REMATCH[1]}"
}

incoming_manifest_count=0
incoming_ciphertext_count=0
for path in "$incoming"/*.tar.gpg.sha256; do
  [[ -e "$path" || -L "$path" ]] || continue
  incoming_manifest_count=$((incoming_manifest_count + 1))
done
for path in "$incoming"/*.tar.gpg; do
  [[ -e "$path" || -L "$path" ]] || continue
  incoming_ciphertext_count=$((incoming_ciphertext_count + 1))
done
incoming_entry_count="$(find "$incoming" -mindepth 1 -maxdepth 1 | wc -l | tr -d ' ')"
if ((incoming_entry_count != incoming_manifest_count + incoming_ciphertext_count)); then
  echo "Offsite incoming directory contains an unexpected entry." >&2
  exit 4
fi
if ((incoming_manifest_count != incoming_ciphertext_count)); then
  echo "Offsite incoming backup pair is incomplete." >&2
  exit 3
fi

promoted=0
for manifest in "$incoming"/*.tar.gpg.sha256; do
  [[ -e "$manifest" || -L "$manifest" ]] || continue
  safe_file "$manifest" "$receive_uid"
  cipher="${manifest%.sha256}"
  safe_file "$cipher" "$receive_uid"
  batch="$(batch_name "$(basename "$cipher")")"
  destination="$vault/$batch"
  if [[ -e "$destination" || -L "$destination" ]]; then
    echo "Offsite immutable vault already contains this batch." >&2
    exit 4
  fi
  stage="$(mktemp -d "$staging_root/${batch}.XXXXXXXX")"
  chmod 0700 "$stage"
  cp -- "$cipher" "$manifest" "$stage/"
  chmod 0600 "$stage/$(basename "$cipher")" "$stage/$(basename "$manifest")"
  (
    cd "$stage"
    sha256sum --check --status "$(basename "$manifest")"
  ) || {
    rm -rf -- "$stage"
    echo "Offsite incoming backup checksum verification failed." >&2
    exit 5
  }
  mv -- "$stage" "$destination"
  rm -f -- "$cipher" "$manifest"
  promoted=$((promoted + 1))
done

vault_batch_count=0
for directory in "$vault"/mt-presence-offsite-*; do
  [[ -e "$directory" || -L "$directory" ]] || continue
  vault_batch_count=$((vault_batch_count + 1))
done
if ((vault_batch_count == 0)); then
  echo "Offsite immutable vault has no recovery point." >&2
  exit 3
fi

newest_seconds=0
for directory in "$vault"/mt-presence-offsite-*; do
  [[ -e "$directory" || -L "$directory" ]] || continue
  if [[ -L "$directory" || ! -d "$directory" || "$(file_mode "$directory")" != "700" || "$(file_uid "$directory")" != "$verifier_uid" ]]; then
    echo "Offsite immutable vault contains an unsafe directory." >&2
    exit 4
  fi
  batch="$(basename "$directory")"
  if [[ ! "$batch" =~ ^mt-presence-offsite-[0-9]{8}T[0-9]{6}Z$ ]]; then
    echo "Offsite immutable vault batch name is invalid." >&2
    exit 4
  fi
  cipher="$directory/$batch.tar.gpg"
  manifest="$cipher.sha256"
  safe_file "$cipher" "$verifier_uid"
  safe_file "$manifest" "$verifier_uid"
  file_count="$(find "$directory" -mindepth 1 -maxdepth 1 -type f | wc -l | tr -d ' ')"
  entry_count="$(find "$directory" -mindepth 1 -maxdepth 1 | wc -l | tr -d ' ')"
  if [[ "$file_count" != "2" || "$entry_count" != "2" ]]; then
    echo "Offsite immutable vault batch contains unexpected entries." >&2
    exit 4
  fi
  (
    cd "$directory"
    sha256sum --check --status "$(basename "$manifest")"
  ) || {
    echo "Offsite immutable vault checksum verification failed." >&2
    exit 5
  }
  modified="$(file_mtime "$cipher")"
  if ((modified > newest_seconds)); then
    newest_seconds="$modified"
  fi
done

now="$(date +%s)"
if [[ -z "$newest_seconds" || $((now - newest_seconds)) -gt 129600 ]]; then
  echo "The newest offsite backup is older than 36 hours." >&2
  exit 6
fi

available_blocks="$(df -P "$backup_root" | awk 'NR == 2 { print $4 }')"
total_blocks="$(df -P "$backup_root" | awk 'NR == 2 { print $2 }')"
free_percent=$((available_blocks * 100 / total_blocks))
if ((free_percent < minimum_free_percent)); then
  echo "Offsite backup disk free space is below policy." >&2
  exit 7
fi

echo "offsite_backup_promoted=$promoted"
echo "offsite_backup_ciphertexts_verified=$vault_batch_count"
echo "offsite_backup_free_percent=$free_percent"
