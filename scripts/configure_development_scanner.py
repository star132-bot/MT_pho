#!/usr/bin/env python3
"""Create a secret-isolated local scanner environment without logging secrets."""

from __future__ import annotations

import argparse
import getpass
import os
from pathlib import Path
import re
import shlex
import shutil
import stat
import subprocess
import sys
import tempfile
from urllib.parse import urlparse
import uuid


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_WEB_ENV_PATH = ROOT / ".env"
DEFAULT_TEMPLATE_PATH = ROOT / ".env.worker.example"
DEFAULT_OUTPUT_PATH = ROOT / ".env.worker"
LOCAL_SIGNATURE_PATH = ROOT / ".scanner-runtime" / "clamav-db"
ASSIGNMENT_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
WORKER_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:@-]{0,119}$")
CURRENT_SECRET_NAME = "SUPABASE_SECRET_KEY"
LEGACY_SECRET_NAME = "SUPABASE_SERVICE_ROLE_KEY"


class SetupError(RuntimeError):
    """A setup failure represented by a stable, non-sensitive code."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def read_assignments(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, raw_value = line.split("=", 1)
        name = name.strip()
        if not ASSIGNMENT_PATTERN.fullmatch(name):
            continue
        value = raw_value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        values[name] = value
    return values


def validate_url(value: str) -> str:
    url = value.strip().rstrip("/")
    parsed = urlparse(url)
    local_http = parsed.scheme == "http" and parsed.hostname in {"127.0.0.1", "localhost"}
    if (
        not url
        or parsed.username
        or parsed.password
        or not parsed.hostname
        or parsed.query
        or parsed.fragment
        or parsed.path not in {"", "/"}
        or (parsed.scheme != "https" and not local_http)
    ):
        raise SetupError("scanner_url_invalid")
    return url


def validate_secret(name: str, value: str) -> str:
    secret = value.strip()
    if (
        not secret
        or any(character.isspace() or ord(character) < 32 or ord(character) == 127 for character in secret)
        or "replace_me" in secret.lower()
        or secret.startswith("sb_publishable_")
    ):
        raise SetupError("scanner_secret_invalid")
    if name == CURRENT_SECRET_NAME:
        if not secret.startswith("sb_secret_") or len(secret) < 24:
            raise SetupError("scanner_secret_invalid")
        return secret
    if name == LEGACY_SECRET_NAME:
        segments = secret.split(".")
        if len(segments) != 3 or len(secret) < 80 or any(not segment for segment in segments):
            raise SetupError("scanner_secret_invalid")
        return secret
    raise SetupError("scanner_secret_invalid")


def select_secret(environment: dict[str, str], *, allow_prompt: bool) -> tuple[str, str]:
    current = environment.get(CURRENT_SECRET_NAME, "").strip()
    legacy = environment.get(LEGACY_SECRET_NAME, "").strip()
    if current:
        return CURRENT_SECRET_NAME, validate_secret(CURRENT_SECRET_NAME, current)
    if legacy:
        return LEGACY_SECRET_NAME, validate_secret(LEGACY_SECRET_NAME, legacy)
    if allow_prompt:
        entered = getpass.getpass("Supabase secret key: ")
        return CURRENT_SECRET_NAME, validate_secret(CURRENT_SECRET_NAME, entered)
    raise SetupError("scanner_secret_missing")


def select_worker_id(existing: dict[str, str]) -> str:
    worker_id = existing.get("MT_SCANNER_ID", "").strip()
    if worker_id and WORKER_ID_PATTERN.fullmatch(worker_id):
        return worker_id
    return str(uuid.uuid4())


def select_clamav_command(explicit: str) -> tuple[str, ...]:
    if explicit.strip():
        try:
            command = tuple(shlex.split(explicit))
        except ValueError as error:
            raise SetupError("clamav_command_invalid") from error
        if not command:
            raise SetupError("clamav_command_invalid")
        return command

    clamscan = shutil.which("clamscan")
    required_signatures = ["main.cvd", "daily.cvd", "bytecode.cvd"]
    if clamscan and all((LOCAL_SIGNATURE_PATH / name).is_file() for name in required_signatures):
        return (
            clamscan,
            f"--database={LOCAL_SIGNATURE_PATH}",
            "--official-db-only=yes",
            "--fail-if-cvd-older-than=2",
            "--no-summary",
            "--suppress-ok-results",
        )
    clamdscan = shutil.which("clamdscan")
    if clamdscan:
        return (clamdscan, "--fdpass", "--no-summary")
    if clamscan:
        return (
            clamscan,
            "--official-db-only=yes",
            "--fail-if-cvd-older-than=2",
            "--no-summary",
            "--suppress-ok-results",
        )
    raise SetupError("clamav_unavailable")


def preflight_clamav(command: tuple[str, ...]) -> None:
    executable = shutil.which(command[0])
    if not executable:
        raise SetupError("clamav_unavailable")
    normalized = (str(Path(executable).resolve()), *command[1:])
    environment = {
        "PATH": "/usr/local/bin:/usr/bin:/bin:/opt/homebrew/bin",
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
    }
    try:
        version = subprocess.run(
            [normalized[0], "--version"],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
            env=environment,
        )
        if version.returncode != 0:
            raise SetupError("clamav_unavailable")
        descriptor, probe_name = tempfile.mkstemp(prefix="mt-scanner-preflight-")
        try:
            os.fchmod(descriptor, stat.S_IRUSR | stat.S_IWUSR)
            os.close(descriptor)
            scanned = subprocess.run(
                [*normalized, probe_name],
                capture_output=True,
                text=True,
                timeout=90,
                check=False,
                env=environment,
            )
            if scanned.returncode != 0:
                raise SetupError("clamav_preflight_failed")
        finally:
            try:
                os.close(descriptor)
            except OSError:
                pass
            Path(probe_name).unlink(missing_ok=True)
    except subprocess.TimeoutExpired as error:
        raise SetupError("clamav_preflight_timeout") from error
    except OSError as error:
        raise SetupError("clamav_unavailable") from error


def render_configuration(
    template: dict[str, str],
    *,
    url: str,
    secret_name: str,
    secret: str,
    worker_id: str,
    clamav_command: tuple[str, ...],
) -> str:
    values = {
        name: value
        for name, value in template.items()
        if name.startswith("MT_SCANNER_")
    }
    values.update(
        {
            "SUPABASE_URL": url,
            secret_name: secret,
            "MT_SCANNER_ID": worker_id,
            "MT_SCANNER_CLAMAV_COMMAND": shlex.join(clamav_command),
        }
    )
    ordered_names = [
        "SUPABASE_URL",
        secret_name,
        "MT_SCANNER_ID",
        "MT_SCANNER_CLAMAV_COMMAND",
        *sorted(
            name
            for name in values
            if name.startswith("MT_SCANNER_")
            and name not in {"MT_SCANNER_ID", "MT_SCANNER_CLAMAV_COMMAND"}
        ),
    ]
    lines = [
        "# Generated by scripts/configure_development_scanner.py.",
        "# Scanner-only credentials. Never source this file into server.py.",
    ]
    lines.extend(f"{name}={shlex.quote(values[name])}" for name in ordered_names)
    return "\n".join(lines) + "\n"


def write_private(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=".env.worker-", dir=path.parent)
    try:
        os.fchmod(descriptor, stat.S_IRUSR | stat.S_IWUSR)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, path)
        path.chmod(stat.S_IRUSR | stat.S_IWUSR)
    finally:
        Path(temporary_name).unlink(missing_ok=True)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create a gitignored development scanner environment without logging its secret.",
    )
    parser.add_argument("--web-env", type=Path, default=DEFAULT_WEB_ENV_PATH)
    parser.add_argument("--template", type=Path, default=DEFAULT_TEMPLATE_PATH)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument(
        "--clamav-command",
        default="",
        help="Non-secret ClamAV command override; the secret is never accepted as an argument.",
    )
    return parser.parse_args()


def main() -> int:
    arguments = parse_arguments()
    try:
        web_values = read_assignments(arguments.web_env)
        template = read_assignments(arguments.template)
        if not template:
            raise SetupError("scanner_template_missing")
        url = validate_url(os.environ.get("SUPABASE_URL", "") or web_values.get("SUPABASE_URL", ""))
        secret_name, secret = select_secret(dict(os.environ), allow_prompt=sys.stdin.isatty())
        existing = read_assignments(arguments.output)
        worker_id = select_worker_id(existing)
        command = select_clamav_command(arguments.clamav_command)
        preflight_clamav(command)
        content = render_configuration(
            template,
            url=url,
            secret_name=secret_name,
            secret=secret,
            worker_id=worker_id,
            clamav_command=command,
        )
        write_private(arguments.output, content)
    except SetupError as error:
        print(f"scanner_configuration_failed={error.code}", file=sys.stderr)
        return 2
    except OSError:
        print("scanner_configuration_failed=scanner_configuration_write_failed", file=sys.stderr)
        return 2

    print("scanner_configuration_written=yes")
    print("scanner_configuration_mode=0600")
    print("scanner_clamav_preflight=yes")
    print("credentials_logged=no")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
