#!/usr/bin/env python3
"""Validate that the distributable Skill remains a public Vaxor V2 connector."""

from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
OPENAPI = ROOT / "references" / "automation-openapi.json"
REQUIRED_OPERATIONS = {
    "startDeviceAuthorization", "pollDeviceToken", "refreshToken", "revokeToken",
    "getSession", "listModels", "resolveModels", "previewExternalWorkflow",
    "createExternalInstance", "compileExternalWorkflow", "startExternalRun",
    "getExternalRun", "getExternalRunResult", "listExports", "getExport",
    "retryExport", "createDownloadTicket", "getUiLinks",
}
ALLOWED_FILES = {
    "SKILL.md", "agents/openai.yaml", "examples/bad_plan.json",
    "examples/good_plan.json", "examples/host_contract.json",
    "references/automation-api.md", "references/automation-openapi.json",
    "scripts/analyze_reference_video.py", "scripts/studio_api.py",
    "scripts/validate_skill_contract.py",
}


def main() -> int:
    errors: list[str] = []
    try:
        document = json.loads(OPENAPI.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(json.dumps({"valid": False, "errors": [str(exc)]}, ensure_ascii=False, indent=2))
        return 1
    if document.get("openapi") != "3.1.0":
        errors.append("OpenAPI version must be 3.1.0")
    operations = {
        operation.get("operationId")
        for path in document.get("paths", {}).values() if isinstance(path, dict)
        for operation in path.values() if isinstance(operation, dict)
    }
    missing = sorted(REQUIRED_OPERATIONS - operations)
    if missing:
        errors.append(f"missing operations: {', '.join(missing)}")
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        relative = str(path.relative_to(ROOT))
        if relative not in ALLOWED_FILES:
            errors.append(f"unapproved distributable file: {relative}")
    print(json.dumps({"valid": not errors, "errors": errors}, ensure_ascii=False, indent=2))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
