#!/usr/bin/env python3
"""Provider-neutral client for the public Vaxor Automation V2 API."""

from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


DEFAULT_TIMEOUT = 60
DEFAULT_CREDENTIALS_PATH = Path(os.environ.get(
    "VAXOR_AUTOMATION_CREDENTIALS_FILE",
    str(Path.home() / ".config" / "vaxor" / "automation-credentials.json"),
)).expanduser()
AUTH = "/v1/auth"
STUDIO = "/v2/studio"
SECRET_KEYS = {"authorization", "token", "accesstoken", "refreshtoken", "devicecode", "secret"}
FORBIDDEN_PUBLIC_KEYS = {
    "scenariomodelid", "scenariomodelkey", "providerid", "providerkey",
    "providerdisplayname", "providermodelname", "modelid", "modelkey",
    "modeldisplayname", "bindingid", "bindingkey", "bindingdisplayname",
    "adapterprofilekey", "adapter", "route", "routing", "upstream", "channel",
    "matchedskukey", "matchedruleid", "policyrevision", "contractversion",
    "checksum", "billingpolicy", "parameterschema", "inputcontract",
    "capabilitysnapshot", "workflowdefinition", "providerpayload", "definition",
}
PUBLIC_PARAMETER_KEYS = {"aspectRatio", "resolution", "durationSec", "quantity"}


class ApiError(RuntimeError):
    def __init__(self, message: str, *, status: int | None = None, body: Any = None) -> None:
        super().__init__(message)
        self.status = status
        self.body = body


def load_json(path: str) -> Any:
    return json.loads(sys.stdin.read() if path == "-" else Path(path).expanduser().read_text(encoding="utf-8"))


def normalized_key(value: str) -> str:
    return "".join(character for character in value if character.isalnum()).lower()


def redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: "[REDACTED]" if normalized_key(key) in SECRET_KEYS else redact(item) for key, item in value.items()}
    if isinstance(value, list):
        return [redact(item) for item in value]
    return value


def project_public(value: Any) -> Any:
    if isinstance(value, list):
        return [project_public(item) for item in value]
    if not isinstance(value, dict):
        return value
    result: dict[str, Any] = {}
    for key, nested in value.items():
        normalized = normalized_key(key)
        if normalized in SECRET_KEYS or normalized in FORBIDDEN_PUBLIC_KEYS:
            continue
        result[key] = project_public(nested)
    return result


def public_error_body(value: Any) -> Any:
    if not isinstance(value, dict):
        return None
    code = value.get("code")
    status_code = value.get("statusCode")
    return {
        **({"code": str(code)} if isinstance(code, str) and code else {}),
        **({"statusCode": status_code} if isinstance(status_code, int) else {}),
        "message": "Vaxor request was rejected.",
    }


def public_fields(value: Any, keys: set[str]) -> dict[str, Any]:
    source = value if isinstance(value, dict) else {}
    return {key: project_public(source[key]) for key in keys if key in source}


def public_parameters(value: Any) -> dict[str, Any]:
    return public_fields(value, PUBLIC_PARAMETER_KEYS)


def public_confirmation(value: Any) -> dict[str, Any]:
    return public_fields(value, {"stepId", "quoteConfirmation", "label", "capability", "costCredits", "expiresAt"}) | {
        "parameters": public_parameters(value.get("parameters")) if isinstance(value, dict) and "parameters" in value else {}
    }


def public_input(value: Any) -> dict[str, Any]:
    source = value if isinstance(value, dict) else {}
    result: dict[str, Any] = {}
    for kind in {"image", "video"}:
        item = source.get(kind)
        if isinstance(item, dict):
            result[kind] = public_fields(item, {"required", "maxCount", "maxDurationSec"})
    return result


def public_capability(value: Any) -> dict[str, Any]:
    source = value if isinstance(value, dict) else {}
    parameters = source.get("parameters") if isinstance(source.get("parameters"), dict) else {}
    return public_fields(source, {"capability", "available"}) | {
        "input": public_input(source.get("input")),
        "parameters": public_fields(parameters, {"aspectRatioOptions", "resolutionOptions", "durationSecOptions", "quantityOptions"}),
    }


def public_model(value: Any) -> dict[str, Any]:
    source = value if isinstance(value, dict) else {}
    capabilities = source.get("capabilities") if isinstance(source.get("capabilities"), list) else []
    return {
        **public_fields(source, {"modelRef", "label", "description"}),
        "capabilities": [public_capability(capability) for capability in capabilities if isinstance(capability, dict)],
    }


def public_quote_steps(value: Any) -> list[dict[str, Any]]:
    return [public_confirmation(item) for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def public_credit_estimate(value: Any) -> dict[str, Any]:
    source = value if isinstance(value, dict) else {}
    return {
        **public_fields(source, {"status", "estimatedCredits", "maxCredits", "exceedsMaxCredits", "requiresConfirmation"}),
        "steps": public_quote_steps(source.get("steps")),
    }


def public_plan(value: Any) -> dict[str, Any]:
    source = value if isinstance(value, dict) else {}
    steps = source.get("steps") if isinstance(source.get("steps"), list) else []
    output = source.get("output") if isinstance(source.get("output"), dict) else {}
    return {
        **public_fields(source, {"schemaVersion", "name"}),
        **({"output": public_fields(output, {"finalCollectionId", "aspectRatio", "resolution"})} if output else {}),
        "steps": [
            public_fields(step, {"id", "kind", "title", "prompt", "modelRef", "label", "capability", "collectionId", "inputAssetIds", "inputStepIds", "durationSec"}) | {
                "parameters": public_parameters(step.get("parameters"))
            }
            for step in steps if isinstance(step, dict)
        ],
    }


def public_asset(value: Any) -> dict[str, Any]:
    return public_fields(value, {"id", "sourceType", "sourceId", "resourceId", "kind", "title", "displayTitle", "subtitle", "status", "progressPercent", "collectionId", "assignedFolderId", "folder", "mimeType", "format", "sizeBytes", "width", "height", "durationSec", "generationDurationSec", "archivedAt", "createdAt", "updatedAt"})


def public_export(value: Any) -> dict[str, Any]:
    return public_fields(value, {"id", "instanceId", "timelineStateId", "resourceId", "rootTaskId", "title", "status", "progressPercent", "stageLabel", "deliveryFileName", "deliveryAvailable", "durationSec", "segmentCount", "errorSummary", "createdAt", "updatedAt", "completedAt"})


def public_run(value: Any) -> dict[str, Any]:
    source = value if isinstance(value, dict) else {}
    return {
        **public_fields(source, {"id", "runId", "workflowInstanceId", "status", "runMode", "terminal", "pollAfterMs", "startedAt", "completedAt", "createdAt", "updatedAt"}),
        "failure": public_fields(source.get("failure"), {"nodeId", "itemId", "reason", "code", "summary"}),
        "credits": public_fields(source.get("credits"), {"reserved", "settled"}),
    }


def project_command_response(command: str, value: Any) -> Any:
    body = response_data(value) if isinstance(value, dict) else value
    if command in {"models", "resolve-models"}:
        source = body if isinstance(body, dict) else {}
        return {
            **public_fields(source, {"assetType", "constraints", "strategy", "selectionStatus", "revalidateOnSubmission", "reason"}),
            "models": [public_model(item) for item in source.get("models", []) if isinstance(item, dict)],
        }
    if command == "quote":
        return public_fields(body, {"modelRef", "label", "capability", "costCredits", "expiresAt", "quoteConfirmation"}) | {
            "parameters": public_parameters(body.get("parameters")) if isinstance(body, dict) else {}
        }
    if command == "preview":
        source = body if isinstance(body, dict) else {}
        validation = source.get("validation") if isinstance(source.get("validation"), dict) else {}
        return public_fields(source, {"status", "canRun", "planHash", "stepCount", "totalDurationSec"}) | {
            "plan": public_plan(source.get("plan")),
            "validation": {
                "errors": [public_fields(item, {"code", "path", "message"}) for item in validation.get("errors", []) if isinstance(item, dict)],
                "warnings": [public_fields(item, {"code", "path", "message"}) for item in validation.get("warnings", []) if isinstance(item, dict)],
            },
            "creditEstimate": public_credit_estimate(source.get("creditEstimate")),
        }
    if command == "compile":
        source = body if isinstance(body, dict) else {}
        return public_fields(source, {"status", "planHash", "promptStudioInstanceId", "workflowInstanceId", "preflight"}) | {
            "creditEstimate": public_credit_estimate(source.get("creditEstimate")),
            "quoteConfirmations": public_quote_steps(source.get("quoteConfirmations")),
        }
    if command == "run":
        source = body if isinstance(body, dict) else {}
        return public_fields(source, {"status", "runId", "workflowInstanceId", "planHash", "reservedCredits", "quotedCredits", "queuedAt"}) | {
            "creditEstimate": public_credit_estimate(source.get("creditEstimate")),
            "quoteConfirmations": public_quote_steps(source.get("quoteConfirmations")),
        }
    if command == "status":
        return public_run(body)
    if command == "events":
        source = body if isinstance(body, dict) else {}
        return {
            "nodes": [public_fields(item, {"id", "nodeId", "itemKey", "attempt", "status", "errorCode", "retryable", "startedAt", "completedAt", "createdAt", "updatedAt"}) for item in source.get("nodes", []) if isinstance(item, dict)],
            "items": [public_fields(item, {"id", "itemKey", "itemIndex", "itemType", "status", "createdAt", "updatedAt"}) for item in source.get("items", []) if isinstance(item, dict)],
        }
    if command == "result":
        source = body if isinstance(body, dict) else {}
        return public_run(source) | {
            "outputs": [public_fields(item, {"id", "nodeId", "kind", "resourceId", "createdAt"}) for item in source.get("outputs", []) if isinstance(item, dict)],
        }
    if command == "assets":
        source = body if isinstance(body, dict) else {}
        return public_fields(source, {"success", "nextCursor", "hasMore"}) | {"items": [public_asset(item) for item in source.get("items", []) if isinstance(item, dict)]}
    if command == "folders":
        source = body if isinstance(body, dict) else {}
        return public_fields(source, {"success", "instanceId", "version", "updatedAt"}) | {
            "folders": [public_fields(item, {"id", "kind", "title", "sortOrder", "hidden", "locked"}) for item in source.get("folders", []) if isinstance(item, dict)],
            "placements": [public_fields(item, {"assetKey", "assignedFolderId", "excludedDefaultFolderIds", "updatedAt"}) for item in source.get("placements", []) if isinstance(item, dict)],
        }
    if command in {"exports", "export-status", "export-retry"}:
        source = body if isinstance(body, dict) else {}
        if isinstance(source.get("exports"), list):
            return {"exports": [public_export(item) for item in source["exports"] if isinstance(item, dict)]}
        return public_export(source.get("export")) if isinstance(source.get("export"), dict) else public_export(source)
    if command in {"upload-complete", "asset-import"}:
        source = body if isinstance(body, dict) else {}
        return public_fields(source, {"status", "instanceId", "uploadId", "resourceId", "assetKey"}) | {
            **({"asset": public_asset(source.get("asset"))} if isinstance(source.get("asset"), dict) else {}),
        }
    if command in {"instance", "rename-instance", "ensure-folders", "asset-place", "upload-init", "download-ticket", "ui-links"}:
        return project_public(body)
    return project_public(body)


def require_public_plan(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ApiError("plan must contain an object")
    steps = value.get("steps")
    if not isinstance(steps, list) or not steps:
        raise ApiError("plan must contain at least one step")
    for index, step in enumerate(steps):
        if not isinstance(step, dict):
            raise ApiError(f"plan.steps[{index}] must contain an object")
        if not isinstance(step.get("modelRef"), str) or not step["modelRef"].strip():
            raise ApiError(f"plan.steps[{index}].modelRef is required")
        if "scenarioModelId" in step or "scenario_model_id" in step:
            raise ApiError("legacy scenarioModelId is not accepted; use modelRef")
        parameters = step.get("parameters", {})
        if not isinstance(parameters, dict) or any(key not in PUBLIC_PARAMETER_KEYS for key in parameters):
            raise ApiError(f"plan.steps[{index}].parameters may only use public semantic keys")
        for key in step:
            if normalized_key(key) in FORBIDDEN_PUBLIC_KEYS:
                raise ApiError("plan contains a private connector field")
    return value


def load_confirmations(path: str) -> list[dict[str, str]]:
    value = load_json(path)
    if not isinstance(value, list):
        raise ApiError("confirmations must contain an array")
    confirmations: list[dict[str, str]] = []
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            raise ApiError(f"confirmations[{index}] must contain an object")
        step_id = str(item.get("stepId") or "").strip()
        confirmation = str(item.get("quoteConfirmation") or "").strip()
        if not step_id or not confirmation:
            raise ApiError(f"confirmations[{index}] requires stepId and quoteConfirmation")
        if any(normalized_key(key) in FORBIDDEN_PUBLIC_KEYS for key in item):
            raise ApiError("confirmations contain a private connector field")
        confirmations.append({"stepId": step_id, "quoteConfirmation": confirmation})
    return confirmations


def stable_key(method: str, path: str, payload: Any) -> str:
    raw = json.dumps({"method": method, "path": path, "payload": payload}, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def response_data(value: dict[str, Any]) -> dict[str, Any]:
    return value.get("data") if isinstance(value.get("data"), dict) else value


class CredentialStore:
    def __init__(self, path: str | None = None) -> None:
        self.path = Path(path).expanduser() if path else DEFAULT_CREDENTIALS_PATH

    def load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {}
        value = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise ApiError(f"credentials must contain an object: {self.path}")
        return value

    def save(self, value: dict[str, Any]) -> None:
        self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.chmod(self.path, 0o600)

    def merge(self, value: dict[str, Any]) -> None:
        current = self.load()
        current.update({key: item for key, item in value.items() if item is not None})
        self.save(current)

    def clear(self) -> None:
        if self.path.exists():
            self.path.unlink()


class StudioApi:
    def __init__(self, args: argparse.Namespace) -> None:
        self.credentials = CredentialStore(args.credentials_file)
        stored = self.credentials.load()
        self.base_url = str(args.base_url or os.environ.get("VAXOR_AUTOMATION_BASE_URL") or stored.get("baseUrl") or "").rstrip("/")
        if not self.base_url:
            raise ApiError("set VAXOR_AUTOMATION_BASE_URL to the Vaxor /api/automation root")
        self.token = args.token or os.environ.get("VAXOR_AUTOMATION_TOKEN") or stored.get("accessToken")
        self.dry_run = args.dry_run
        self.idempotency_key = args.idempotency_key

    def request(self, method: str, path: str, payload: Any = None, *, query: dict[str, Any] | None = None, auth: bool = True) -> dict[str, Any]:
        path = "/" + path.lstrip("/")
        url = f"{self.base_url}{path}"
        if query:
            url += "?" + urllib.parse.urlencode({key: str(value) for key, value in query.items() if value is not None})
        key = self.idempotency_key or stable_key(method, path, payload)
        headers = {"Accept": "application/json", "Idempotency-Key": key}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        if payload is not None:
            headers["Content-Type"] = "application/json"
        if self.dry_run:
            print(json.dumps(project_public({"dryRun": True, "method": method, "url": url, "headers": redact(headers), "body": redact(payload), "idempotencyKey": key}), ensure_ascii=False, indent=2))
            return {"dryRun": True}
        if auth and not self.token:
            raise ApiError("authenticate with auth-start/auth-poll first")
        request = urllib.request.Request(url, data=None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8"), headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=DEFAULT_TIMEOUT) as response:
                raw = response.read().decode("utf-8")
                return json.loads(raw) if raw else {"status": response.status}
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace")
            try:
                body: Any = json.loads(raw)
            except json.JSONDecodeError:
                body = raw
            raise ApiError(f"Vaxor API returned HTTP {exc.code}", status=exc.code, body=public_error_body(body)) from exc
        except urllib.error.URLError as exc:
            raise ApiError(f"Vaxor API request failed: {exc.reason}") from exc

    def multipart(self, path: str, file_path: str) -> dict[str, Any]:
        source = Path(file_path).expanduser()
        if not source.is_file():
            raise ApiError(f"upload file does not exist: {source}")
        if self.dry_run:
            return self.request("POST", path, {"fileName": source.name, "sizeBytes": source.stat().st_size})
        if not self.token:
            raise ApiError("authenticate with auth-start/auth-poll first")
        boundary = f"----vaxor-{hashlib.sha256(os.urandom(16)).hexdigest()[:24]}"
        mime_type = mimetypes.guess_type(source.name)[0] or "application/octet-stream"
        body = (
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{source.name.replace(chr(34), '')}\"\r\nContent-Type: {mime_type}\r\n\r\n".encode("utf-8")
            + source.read_bytes() + f"\r\n--{boundary}--\r\n".encode("utf-8")
        )
        request = urllib.request.Request(f"{self.base_url}/{path.lstrip('/')}", data=body, headers={"Accept": "application/json", "Authorization": f"Bearer {self.token}", "Content-Type": f"multipart/form-data; boundary={boundary}", "Idempotency-Key": self.idempotency_key or stable_key("POST", path, {"file": source.name, "size": source.stat().st_size})}, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=DEFAULT_TIMEOUT) as response:
                raw = response.read().decode("utf-8")
                return json.loads(raw) if raw else {"status": response.status}
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace")
            try:
                body: Any = json.loads(raw)
            except json.JSONDecodeError:
                body = None
            raise ApiError(f"Vaxor API returned HTTP {exc.code}", status=exc.code, body=public_error_body(body)) from exc


def q(value: str) -> str:
    return urllib.parse.quote(value, safe="")


def run_command(args: argparse.Namespace) -> dict[str, Any]:
    api = StudioApi(args)
    if args.command == "auth-start":
        result = api.request("POST", f"{AUTH}/device/code", {"clientType": args.client_type, "clientInstanceId": args.client_instance_id, "displayName": args.display_name, "scopes": args.scope}, auth=False)
        if not api.dry_run:
            data = response_data(result)
            api.credentials.merge({"baseUrl": api.base_url, "deviceCode": data.get("deviceCode"), "clientType": args.client_type, "clientInstanceId": args.client_instance_id})
            return {"authorizationPending": True, "userCode": data.get("userCode"), "verificationUri": data.get("verificationUriComplete") or data.get("verificationUri"), "expiresIn": data.get("expiresIn"), "interval": data.get("interval"), "credentialsFile": str(api.credentials.path)}
        return result
    if args.command == "auth-poll":
        device_code = args.device_code or api.credentials.load().get("deviceCode")
        result = api.request("POST", f"{AUTH}/device/token", {"deviceCode": device_code or "[device-code]"}, auth=False)
        if not api.dry_run:
            data = response_data(result)
            if not data.get("accessToken"):
                raise ApiError("token response did not include accessToken", body=redact(result))
            api.credentials.merge({"accessToken": data.get("accessToken"), "refreshToken": data.get("refreshToken"), "expiresAt": data.get("expiresAt"), "scopes": data.get("scopes")})
        return {"authenticated": not api.dry_run, "credentialsFile": str(api.credentials.path)}
    if args.command == "auth-refresh":
        refresh = api.credentials.load().get("refreshToken")
        result = api.request("POST", f"{AUTH}/token/refresh", {"refreshToken": refresh or "[refresh-token]"}, auth=False)
        if not api.dry_run:
            data = response_data(result)
            api.credentials.merge({"accessToken": data.get("accessToken"), "refreshToken": data.get("refreshToken") or refresh, "expiresAt": data.get("expiresAt"), "scopes": data.get("scopes")})
        return {"authenticated": not api.dry_run, "refreshed": True}
    if args.command == "auth-session":
        return api.request("GET", f"{AUTH}/session")
    if args.command == "auth-revoke":
        result = api.request("POST", f"{AUTH}/token/revoke", {})
        if not api.dry_run:
            api.credentials.clear()
        return result
    if args.command == "models":
        return api.request("GET", f"{STUDIO}/models", query={"assetType": args.asset_type})
    if args.command == "resolve-models":
        return api.request("POST", f"{STUDIO}/models/resolve", {"assetType": args.asset_type, "constraints": load_json(args.constraints) if args.constraints else {}, "strategy": args.strategy})
    if args.command == "quote":
        return api.request("POST", f"{STUDIO}/models/quote", {
            "modelRef": args.model_ref,
            "capability": args.capability,
            "parameters": load_json(args.parameters),
            **({"quantity": args.quantity} if args.quantity is not None else {}),
        })
    if args.command == "preview":
        return api.request("POST", f"{STUDIO}/plans/preview", {
            "plan": require_public_plan(load_json(args.plan)),
            **({"maxCredits": args.max_credits} if args.max_credits is not None else {}),
        })
    if args.command == "instance":
        return api.request("POST", f"{STUDIO}/instances", {"name": args.name, "description": args.description})
    if args.command == "rename-instance":
        return api.request("PATCH", f"{STUDIO}/instances/{q(args.instance_id)}", {"name": args.name})
    if args.command in {"folders", "assets", "exports", "ui-links"}:
        suffix = {"folders": "folders", "assets": "assets", "exports": "exports", "ui-links": "ui-links"}[args.command]
        query = {"collectionId": getattr(args, "collection_id", None), "assetType": getattr(args, "asset_type", None), "cursor": getattr(args, "cursor", None), "limit": getattr(args, "limit", None)}
        return api.request("GET", f"{STUDIO}/instances/{q(args.instance_id)}/{suffix}", query=query)
    if args.command == "ensure-folders":
        return api.request("POST", f"{STUDIO}/instances/{q(args.instance_id)}/folders/ensure", {"folders": load_json(args.folders)})
    if args.command in {"upload-init", "asset-import", "asset-place"}:
        suffix, method = {"upload-init": ("assets/uploads", "POST"), "asset-import": ("assets/import", "POST"), "asset-place": ("assets/placements", "PATCH")}[args.command]
        return api.request(method, f"{STUDIO}/instances/{q(args.instance_id)}/{suffix}", load_json(args.payload))
    if args.command == "upload-complete":
        return api.multipart(f"{STUDIO}/instances/{q(args.instance_id)}/assets/uploads/{q(args.upload_id)}/complete", args.file)
    if args.command == "compile":
        return api.request("POST", f"{STUDIO}/instances/{q(args.instance_id)}/workflows/compile", {
            "plan": require_public_plan(load_json(args.plan)),
            "confirm": args.confirm,
            "maxCredits": args.max_credits,
            "quoteConfirmations": load_confirmations(args.confirmations),
        })
    if args.command == "run":
        return api.request("POST", f"{STUDIO}/workflows/{q(args.workflow_instance_id)}/runs", {
            "planHash": args.plan_hash,
            "confirm": args.confirm,
            "maxCredits": args.max_credits,
            "quoteConfirmations": load_confirmations(args.confirmations),
            **({"retryOfRunId": args.retry_of_run_id} if args.retry_of_run_id else {}),
        })
    if args.command in {"status", "events", "result"}:
        suffix = "" if args.command == "status" else "/events" if args.command == "events" else "/result"
        return api.request("GET", f"{STUDIO}/runs/{q(args.run_id)}{suffix}")
    if args.command in {"export-status", "export-retry", "download-ticket"}:
        suffix = "" if args.command == "export-status" else "/retry" if args.command == "export-retry" else "/download-ticket"
        return api.request("GET" if not suffix else "POST", f"{STUDIO}/exports/{q(args.export_id)}{suffix}", load_json(args.payload) if suffix and args.payload else ({} if suffix else None))
    raise ApiError(f"unknown command: {args.command}")


def common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--base-url")
    parser.add_argument("--token")
    parser.add_argument("--credentials-file")
    parser.add_argument("--idempotency-key")
    parser.add_argument("--dry-run", action="store_true")


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    sub = root.add_subparsers(dest="command", required=True)
    start = sub.add_parser("auth-start"); start.add_argument("--client-type", choices=["codex", "chatgpt_work", "zcode", "workbuddy"], default="codex"); start.add_argument("--client-instance-id", required=True); start.add_argument("--display-name", required=True); start.add_argument("--scope", action="append", required=True); common(start)
    poll = sub.add_parser("auth-poll"); poll.add_argument("--device-code"); common(poll)
    for name in ("auth-refresh", "auth-session", "auth-revoke"):
        common(sub.add_parser(name))
    models = sub.add_parser("models"); models.add_argument("--asset-type", choices=["image", "video"], required=True); common(models)
    resolve = sub.add_parser("resolve-models"); resolve.add_argument("--asset-type", choices=["image", "video"], required=True); resolve.add_argument("--constraints"); resolve.add_argument("--strategy", default="manual"); common(resolve)
    quote = sub.add_parser("quote"); quote.add_argument("--model-ref", required=True); quote.add_argument("--capability", required=True); quote.add_argument("--parameters", required=True); quote.add_argument("--quantity", type=int); common(quote)
    preview = sub.add_parser("preview"); preview.add_argument("plan"); preview.add_argument("--max-credits", type=int); common(preview)
    instance = sub.add_parser("instance"); instance.add_argument("--name", required=True); instance.add_argument("--description"); common(instance)
    rename = sub.add_parser("rename-instance"); rename.add_argument("--instance-id", required=True); rename.add_argument("--name", required=True); common(rename)
    folders = sub.add_parser("ensure-folders"); folders.add_argument("--instance-id", required=True); folders.add_argument("--folders", required=True); common(folders)
    for name in ("folders", "exports", "ui-links"):
        item = sub.add_parser(name); item.add_argument("--instance-id", required=True); item.add_argument("--limit", type=int); common(item)
    assets = sub.add_parser("assets"); assets.add_argument("--instance-id", required=True); assets.add_argument("--collection-id"); assets.add_argument("--asset-type", choices=["image", "video", "audio", "document"]); assets.add_argument("--cursor"); assets.add_argument("--limit", type=int); common(assets)
    for name in ("upload-init", "asset-import", "asset-place"):
        item = sub.add_parser(name); item.add_argument("--instance-id", required=True); item.add_argument("--payload", required=True); common(item)
    complete = sub.add_parser("upload-complete"); complete.add_argument("--instance-id", required=True); complete.add_argument("--upload-id", required=True); complete.add_argument("--file", required=True); common(complete)
    compile_command = sub.add_parser("compile"); compile_command.add_argument("--instance-id", required=True); compile_command.add_argument("--confirmations", required=True); compile_command.add_argument("plan"); compile_command.add_argument("--confirm", action="store_true"); compile_command.add_argument("--max-credits", type=int, required=True); common(compile_command)
    run = sub.add_parser("run"); run.add_argument("--workflow-instance-id", required=True); run.add_argument("--plan-hash", required=True); run.add_argument("--confirmations", required=True); run.add_argument("--confirm", action="store_true"); run.add_argument("--max-credits", type=int, required=True); run.add_argument("--retry-of-run-id"); common(run)
    for name in ("status", "events", "result"):
        item = sub.add_parser(name); item.add_argument("--run-id", required=True); common(item)
    for name in ("export-status", "export-retry", "download-ticket"):
        item = sub.add_parser(name); item.add_argument("--export-id", required=True); item.add_argument("--payload"); common(item)
    return root


def main() -> int:
    args = parser().parse_args()
    try:
        result = run_command(args)
    except (ApiError, OSError, json.JSONDecodeError) as exc:
        error: dict[str, Any] = {"error": str(exc)}
        if isinstance(exc, ApiError) and exc.body is not None:
            error["details"] = exc.body
        print(json.dumps(project_public(error), ensure_ascii=False, indent=2), file=sys.stderr)
        return 2
    print(json.dumps(project_command_response(args.command, redact(result)), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
