#!/usr/bin/env python3
"""Validate the bundled OpenAPI and multi-host contract without third-party packages."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


SKILL_ROOT = Path(__file__).resolve().parent.parent
OPENAPI_PATH = SKILL_ROOT / "references" / "automation-openapi.json"
HOST_PATH = SKILL_ROOT / "examples" / "host_contract.json"
REQUIRED_HOSTS = {"codex", "chatgpt_work", "zcode", "workbuddy"}
REQUIRED_OPERATIONS = {
    "startDeviceAuthorization", "pollDeviceToken", "refreshToken", "revokeToken",
    "getSession", "createInstance", "listAssets", "initializeUpload", "completeUpload",
    "importAsset", "placeAssets", "getRun", "getRunResult", "listExports",
    "getExport", "retryExport", "createDownloadTicket", "getUiLinks",
}


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} root must be an object")
    return value


def validate() -> list[str]:
    errors: list[str] = []
    openapi = load(OPENAPI_PATH)
    if openapi.get("openapi") != "3.1.0":
        errors.append("OpenAPI version must be 3.1.0")
    if "bearerAuth" not in openapi.get("components", {}).get("securitySchemes", {}):
        errors.append("bearerAuth security scheme is missing")
    operations: set[str] = set()
    for path, path_item in openapi.get("paths", {}).items():
        if not isinstance(path_item, dict):
            continue
        for method, operation in path_item.items():
            if method not in {"get", "post", "patch", "put", "delete"} or not isinstance(operation, dict):
                continue
            operation_id = operation.get("operationId")
            if operation_id in operations:
                errors.append(f"duplicate operationId: {operation_id}")
            if isinstance(operation_id, str):
                operations.add(operation_id)
            if "x-required-scopes" not in operation:
                errors.append(f"{method.upper()} {path} is missing x-required-scopes")
    missing = REQUIRED_OPERATIONS - operations
    if missing:
        errors.append(f"missing operations: {', '.join(sorted(missing))}")

    hosts = load(HOST_PATH)
    actual_hosts = {
        item.get("clientType") for item in hosts.get("hosts", []) if isinstance(item, dict)
    }
    if actual_hosts != REQUIRED_HOSTS:
        errors.append(f"host fixture must contain exactly: {', '.join(sorted(REQUIRED_HOSTS))}")
    if hosts.get("invariants", {}).get("tokensInUrls") is not False:
        errors.append("host fixture must prohibit tokens in URLs")
    return errors


def main() -> int:
    try:
        errors = validate()
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        errors = [str(exc)]
    print(json.dumps({"valid": not errors, "errors": errors}, ensure_ascii=False, indent=2))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
