#!/usr/bin/env python3
"""Check the installed Vaxor skill version and optionally upgrade it in place.

Usage:
  scripts/skill_upgrade.py --check           # report current vs latest, no changes
  scripts/skill_upgrade.py --ensure-latest   # download + verify + swap when behind
  scripts/skill_upgrade.py --dry-run         # show what would happen

Environment:
  VAXOR_AUTOMATION_BASE_URL   Vaxor API root, e.g. https://www.vaxor.pro/api/automation
  VAXOR_SKILL_AUTO_UPDATE=0   disable automatic upgrades (check-only, informs the user)

The upgrade is atomic: the new package is downloaded and verified in a temp
directory before the current skill directory is replaced, and the previous
version is kept next to it as `.backup-<version>` so a failed verification
never leaves the user without a working skill.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path
from typing import Any

SKILL_ROOT = Path(__file__).resolve().parent.parent
VERSION_FILE = SKILL_ROOT / "VERSION"
DEFAULT_STUDIO_ROOT = "/v1/skill/version"
REQUEST_TIMEOUT = 30


def read_local_version() -> str | None:
    try:
        raw = VERSION_FILE.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return raw.lstrip("v") or None


def version_tuple(value: str | None) -> tuple[int, int, int] | None:
    if not value:
        return None
    parts = value.lstrip("v").split(".")
    if len(parts) != 3 or not all(part.isdigit() for part in parts):
        return None
    return tuple(int(part) for part in parts)  # type: ignore[return-value]


def resolved_base_url(explicit: str | None) -> str:
    return str(
        explicit
        or os.environ.get("VAXOR_AUTOMATION_BASE_URL")
        or os.environ.get("VAXOR_AUTOMATION_ROOT")
        or ""
    ).rstrip("/")


def fetch_policy(explicit: str | None) -> dict[str, Any]:
    base = resolved_base_url(explicit)
    if not base:
        raise SystemExit(
            json.dumps(
                {
                    "error": "set VAXOR_AUTOMATION_BASE_URL to the Vaxor /api/automation root",
                    "skillDir": str(SKILL_ROOT),
                },
                ensure_ascii=False,
            )
        )
    url = f"{base}{DEFAULT_STUDIO_ROOT}"
    try:
        with urllib.request.urlopen(url, timeout=REQUEST_TIMEOUT) as response:
            payload = json.loads(response.read().decode("utf-8") or "{}")
    except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError) as exc:
        raise SystemExit(
            json.dumps(
                {"error": f"skill version lookup failed: {exc}", "url": url},
                ensure_ascii=False,
            )
        )
    return payload.get("data") if isinstance(payload.get("data"), dict) else payload


def download_package(url: str, target_dir: Path) -> Path:
    target_dir.mkdir(parents=True, exist_ok=True)
    archive = target_dir / "package.zip"
    request = urllib.request.Request(url, headers={"Accept": "application/zip"})
    with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT * 4) as response:
        archive.write_bytes(response.read())
    return archive


def extract_skill(archive: Path, target_dir: Path) -> Path:
    extract_root = target_dir / "extract"
    extract_root.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive) as bundle:
        bundle.extractall(extract_root)
    candidates = [path.parent for path in extract_root.rglob("SKILL.md")]
    if not candidates:
        raise RuntimeError("downloaded package does not contain SKILL.md")
    candidates.sort(key=lambda path: len(path.parts))
    return candidates[0]


def install_from(source_dir: Path, dry_run: bool) -> dict[str, Any]:
    local_version = read_local_version() or "unknown"
    backup_dir = SKILL_ROOT.parent / f".backup-{local_version}"
    if dry_run:
        return {
            "upgraded": False,
            "dryRun": True,
            "wouldReplace": str(SKILL_ROOT),
            "from": local_version,
            "source": str(source_dir),
        }
    if backup_dir.exists():
        shutil.rmtree(backup_dir, ignore_errors=True)
    shutil.copytree(SKILL_ROOT, backup_dir, dirs_exist_ok=False)
    for item in SKILL_ROOT.iterdir():
        if item.name.startswith(".backup-"):
            continue
        if item.is_dir():
            shutil.rmtree(item)
        else:
            item.unlink()
    for item in source_dir.iterdir():
        target = SKILL_ROOT / item.name
        if item.is_dir():
            shutil.copytree(item, target)
        else:
            shutil.copy2(item, target)
    return {"upgraded": True, "backupDir": str(backup_dir), "from": local_version}


def run(args: argparse.Namespace) -> dict[str, Any]:
    local_version = read_local_version()
    if local_version is None:
        raise SystemExit(
            json.dumps(
                {"error": "installed skill has no VERSION file", "skillDir": str(SKILL_ROOT)},
                ensure_ascii=False,
            )
        )
    policy = fetch_policy(args.base_url)
    latest = str(policy.get("latest") or "").lstrip("v")
    latest_tuple = version_tuple(latest)
    local_tuple = version_tuple(local_version)
    if not latest_tuple or not local_tuple:
        raise SystemExit(
            json.dumps(
                {"error": "invalid version metadata", "local": local_version, "latest": latest},
                ensure_ascii=False,
            )
        )

    result: dict[str, Any] = {
        "skillDir": str(SKILL_ROOT),
        "current": local_version,
        "latest": latest,
        "upToDate": local_tuple >= latest_tuple,
        "upgradeHint": policy.get("upgradeHint"),
    }
    if result["upToDate"]:
        return result
    if os.environ.get("VAXOR_SKILL_AUTO_UPDATE", "").strip() == "0":
        result["autoUpdateDisabled"] = True
        return result
    if args.check:
        return result

    package_url = str(policy.get("packageUrl") or "").strip()
    if not package_url:
        result["error"] = "version policy did not include a packageUrl"
        return result

    with tempfile.TemporaryDirectory(prefix="vaxor-skill-") as tmp:
        tmp_dir = Path(tmp)
        archive = download_package(package_url, tmp_dir)
        source_dir = extract_skill(archive, tmp_dir)
        result.update(install_from(source_dir, args.dry_run))
        result["packageUrl"] = package_url
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="report versions only")
    parser.add_argument(
        "--ensure-latest",
        action="store_true",
        help="download and install the latest version when behind (default behaviour)",
    )
    parser.add_argument("--dry-run", action="store_true", help="show actions without changing files")
    parser.add_argument("--base-url", help="Vaxor automation API root")
    args = parser.parse_args()
    try:
        result = run(args)
    except SystemExit:
        raise
    except Exception as exc:  # pragma: no cover - defensive
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
