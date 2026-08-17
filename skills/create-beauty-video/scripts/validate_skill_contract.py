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
    "getSession", "listModels", "resolveModels", "quotePublicModel", "previewExternalWorkflow",
    "createExternalInstance", "compileExternalWorkflow", "startExternalRun",
    "getExternalRun", "getExternalRunEvents", "getExternalRunResult", "listExports", "getExport",
    "retryExport", "createDownloadTicket", "getUiLinks",
}
FORBIDDEN_TERMS = {
    "scenariomodelid", "scenariomodelkey", "providerkey", "providermodelname",
    "bindingkey", "matchedskukey", "policyrevision", "contractversion",
    "capabilitysnapshot", "workflowdefinition",
}
ALLOWED_FILES = {
    "SKILL.md", "agents/openai.yaml", "examples/bad_plan.json",
    "examples/good_plan.json", "examples/host_contract.json", "examples/preview_confirmations.json",
    "references/automation-api.md", "references/automation-openapi.json",
    "scripts/analyze_reference_video.py", "scripts/studio_api.py",
    "scripts/validate_skill_contract.py",
}

ALLOWED_PREFIXES = ("core/", "adapters/", "tests/")


def main() -> int:
    errors: list[str] = []
    try:
        document = json.loads(OPENAPI.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(json.dumps({"valid": False, "errors": [str(exc)]}, ensure_ascii=False, indent=2))
        return 1
    if document.get("openapi") != "3.1.0":
        errors.append("OpenAPI version must be 3.1.0")
    if document.get("info", {}).get("version") != "0.4.0":
        errors.append("OpenAPI version must be 0.4.0")
    serialized_openapi = json.dumps(document, ensure_ascii=False).lower()
    for term in sorted(FORBIDDEN_TERMS):
        if term in serialized_openapi:
            errors.append(f"OpenAPI exposes forbidden term: {term}")
    plan = json.loads((ROOT / "examples" / "good_plan.json").read_text(encoding="utf-8"))
    steps = plan.get("steps") if isinstance(plan, dict) else None
    if not isinstance(steps, list) or any(not isinstance(step, dict) or not step.get("modelRef") for step in steps):
        errors.append("good plan must use modelRef for every step")
    if "scenarioModelId" in json.dumps(plan):
        errors.append("good plan must not include scenarioModelId")
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
        if relative not in ALLOWED_FILES and not relative.startswith(ALLOWED_PREFIXES):
            errors.append(f"unapproved distributable file: {relative}")
    print(json.dumps({"valid": not errors, "errors": errors}, ensure_ascii=False, indent=2))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
