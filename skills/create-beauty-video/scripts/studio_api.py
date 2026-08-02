#!/usr/bin/env python3
"""Small provider-neutral client for Tianzuo's automation API.

The client intentionally has no provider-specific logic. It supports dry-run
request inspection so Codex can show a cost/model preview before side effects.
"""

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
DEFAULT_CREDENTIALS_PATH = Path(
    os.environ.get(
        "TIANZUO_AUTOMATION_CREDENTIALS_FILE",
        str(Path.home() / ".config" / "tianzuo" / "automation-credentials.json"),
    )
).expanduser()
SECRET_KEYS = {
    "authorization",
    "token",
    "accessToken",
    "refreshToken",
    "apiKey",
    "secret",
    "signedUrl",
    "presignedUrl",
    "access_token",
    "refresh_token",
    "deviceCode",
    "device_code",
}
NORMALIZED_SECRET_KEYS = {key.replace("_", "").lower() for key in SECRET_KEYS}


class ApiError(RuntimeError):
    def __init__(self, message: str, *, status: int | None = None, body: Any = None) -> None:
        super().__init__(message)
        self.status = status
        self.body = body


def load_json(path: str) -> Any:
    raw = sys.stdin.read() if path == "-" else Path(path).expanduser().read_text(encoding="utf-8")
    return json.loads(raw)


def redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: "[REDACTED]"
            if key.replace("_", "").lower() in NORMALIZED_SECRET_KEYS
            else redact(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact(item) for item in value]
    return value


def stable_key(method: str, path: str, payload: Any) -> str:
    canonical = json.dumps(
        {"method": method, "path": path, "payload": payload},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:32]


def response_data(value: dict[str, Any]) -> dict[str, Any]:
    data = value.get("data")
    return data if isinstance(data, dict) else value


def first_value(value: dict[str, Any], *names: str) -> Any:
    for name in names:
        if name in value:
            return value[name]
    return None


class CredentialStore:
    """Store OAuth device state without printing bearer credentials."""

    def __init__(self, path: str | None = None):
        self.path = Path(path).expanduser() if path else DEFAULT_CREDENTIALS_PATH

    def load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {}
        value = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise ApiError(f"credentials file must contain an object: {self.path}")
        return value

    def save(self, value: dict[str, Any]) -> None:
        self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(value, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        os.chmod(self.path, 0o600)

    def merge(self, value: dict[str, Any]) -> dict[str, Any]:
        current = self.load()
        current.update({key: item for key, item in value.items() if item is not None})
        self.save(current)
        return current

    def clear(self) -> None:
        if self.path.exists():
            self.path.unlink()


class StudioApi:
    def __init__(
        self,
        base_url: str | None = None,
        token: str | None = None,
        timeout: int = DEFAULT_TIMEOUT,
        credentials_file: str | None = None,
    ):
        self.credentials = CredentialStore(credentials_file)
        stored = self.credentials.load()
        configured = (
            base_url
            or os.environ.get("TIANZUO_AUTOMATION_BASE_URL")
            or first_value(stored, "baseUrl", "base_url")
        )
        if not configured:
            raise ApiError("set TIANZUO_AUTOMATION_BASE_URL before using the automation client")
        self.base_url = configured.rstrip("/")
        self.token = (
            token
            if token is not None
            else os.environ.get("TIANZUO_AUTOMATION_TOKEN")
            or first_value(stored, "accessToken", "access_token")
        )
        self.timeout = timeout

    def request(
        self,
        method: str,
        path: str,
        payload: Any = None,
        *,
        query: dict[str, str] | None = None,
        idempotency_key: str | None = None,
        dry_run: bool = False,
        auth_required: bool = True,
        send_token: bool = True,
    ) -> dict[str, Any]:
        path = "/" + path.lstrip("/")
        url = f"{self.base_url}{path}"
        if query:
            url = f"{url}?{urllib.parse.urlencode(query)}"
        key = idempotency_key or stable_key(method, path, payload)
        headers = {"Accept": "application/json", "Idempotency-Key": key}
        if send_token and self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        if payload is not None:
            headers["Content-Type"] = "application/json"
        if dry_run:
            print(json.dumps({
                "dryRun": True,
                "method": method,
                "url": url,
                "headers": redact(headers),
                "body": redact(payload),
                "idempotencyKey": key,
            }, ensure_ascii=False, indent=2))
            return {"dryRun": True, "idempotencyKey": key}
        if auth_required and not self.token:
            raise ApiError("authenticate with auth-start/auth-poll or set TIANZUO_AUTOMATION_TOKEN")
        body = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(url, data=body, headers=headers, method=method.upper())
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                raw = response.read().decode("utf-8")
                if not raw:
                    return {"status": response.status}
                try:
                    return json.loads(raw)
                except json.JSONDecodeError:
                    return {"status": response.status, "raw": raw}
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace")
            try:
                parsed: Any = json.loads(raw)
            except json.JSONDecodeError:
                parsed = raw
            raise ApiError(
                f"automation API returned HTTP {exc.code}",
                status=exc.code,
                body=redact(parsed),
            ) from exc
        except urllib.error.URLError as exc:
            raise ApiError(f"automation API request failed: {exc.reason}") from exc

    def request_multipart(
        self,
        method: str,
        path: str,
        file_path: str,
        *,
        idempotency_key: str | None = None,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        path = "/" + path.lstrip("/")
        url = f"{self.base_url}{path}"
        source = Path(file_path).expanduser()
        if not source.is_file():
            raise ApiError(f"upload file does not exist: {source}")
        key = idempotency_key or stable_key(method, path, {"file": source.name, "size": source.stat().st_size})
        if dry_run:
            print(json.dumps({
                "dryRun": True,
                "method": method,
                "url": url,
                "headers": {"Authorization": "[REDACTED]", "Idempotency-Key": key},
                "multipart": {"fieldName": "file", "fileName": source.name, "sizeBytes": source.stat().st_size},
            }, ensure_ascii=False, indent=2))
            return {"dryRun": True, "idempotencyKey": key}
        if not self.token:
            raise ApiError("authenticate with auth-start/auth-poll or set TIANZUO_AUTOMATION_TOKEN")
        boundary = f"----tianzuo-automation-{hashlib.sha256(os.urandom(16)).hexdigest()[:24]}"
        mime_type = mimetypes.guess_type(source.name)[0] or "application/octet-stream"
        prefix = (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="file"; filename="{source.name.replace(chr(34), "")}\r\n'
            f"Content-Type: {mime_type}\r\n\r\n"
        ).encode("utf-8")
        suffix = f"\r\n--{boundary}--\r\n".encode("utf-8")
        body = prefix + source.read_bytes() + suffix
        headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {self.token}",
            "Idempotency-Key": key,
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        }
        request = urllib.request.Request(url, data=body, headers=headers, method=method.upper())
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                raw = response.read().decode("utf-8")
                return json.loads(raw) if raw else {"status": response.status}
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace")
            try:
                parsed: Any = json.loads(raw)
            except json.JSONDecodeError:
                parsed = raw
            raise ApiError(f"automation API returned HTTP {exc.code}", status=exc.code, body=redact(parsed)) from exc
        except urllib.error.URLError as exc:
            raise ApiError(f"automation API request failed: {exc.reason}") from exc


def add_common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--base-url")
    parser.add_argument("--token")
    parser.add_argument("--credentials-file")
    parser.add_argument("--idempotency-key")
    parser.add_argument("--dry-run", action="store_true")


def run_command(args: argparse.Namespace) -> dict[str, Any]:
    api = StudioApi(args.base_url, args.token, credentials_file=args.credentials_file)
    if args.command == "auth-start":
        result = api.request(
            "POST",
            "/auth/device/code",
            {
                "clientType": args.client_type,
                "clientInstanceId": args.client_instance_id,
                "displayName": args.display_name,
                "scopes": args.scope,
            },
            idempotency_key=args.idempotency_key,
            dry_run=args.dry_run,
            auth_required=False,
            send_token=False,
        )
        if not args.dry_run:
            data = response_data(result)
            device_code = first_value(data, "deviceCode", "device_code")
            if not device_code:
                raise ApiError("device authorization response did not include deviceCode")
            api.credentials.merge({
                "baseUrl": api.base_url,
                "deviceCode": device_code,
                "clientType": args.client_type,
                "clientInstanceId": args.client_instance_id,
            })
            return {
                "authorizationPending": True,
                "userCode": first_value(data, "userCode", "user_code"),
                "verificationUri": first_value(
                    data, "verificationUriComplete", "verification_uri_complete",
                    "verificationUri", "verification_uri"
                ),
                "expiresIn": first_value(data, "expiresIn", "expires_in"),
                "interval": first_value(data, "interval", "pollInterval", "poll_interval"),
                "credentialsFile": str(api.credentials.path),
            }
        return result
    if args.command == "auth-poll":
        stored = api.credentials.load()
        device_code = args.device_code or first_value(stored, "deviceCode", "device_code")
        if not device_code and not args.dry_run:
            raise ApiError("run auth-start first or pass --device-code")
        result = api.request(
            "POST",
            "/auth/device/token",
            {"deviceCode": device_code or "[device-code-from-auth-start]"},
            idempotency_key=args.idempotency_key,
            dry_run=args.dry_run,
            auth_required=False,
            send_token=False,
        )
        if not args.dry_run:
            data = response_data(result)
            access_token = first_value(data, "accessToken", "access_token")
            refresh_token = first_value(data, "refreshToken", "refresh_token")
            if not access_token:
                raise ApiError("token response did not include accessToken", body=redact(result))
            api.credentials.merge({
                "accessToken": access_token,
                "refreshToken": refresh_token,
                "expiresAt": first_value(data, "expiresAt", "expires_at"),
                "expiresIn": first_value(data, "expiresIn", "expires_in"),
                "scopes": first_value(data, "scopes", "scope"),
                "deviceCode": None,
            })
            stored = api.credentials.load()
            stored.pop("deviceCode", None)
            api.credentials.save(stored)
            return {
                "authenticated": True,
                "expiresAt": first_value(data, "expiresAt", "expires_at"),
                "expiresIn": first_value(data, "expiresIn", "expires_in"),
                "scopes": first_value(data, "scopes", "scope"),
                "credentialsFile": str(api.credentials.path),
            }
        return result
    if args.command == "auth-refresh":
        stored = api.credentials.load()
        refresh_token = first_value(stored, "refreshToken", "refresh_token")
        if not refresh_token and not args.dry_run:
            raise ApiError("no refresh token is available; run auth-start again")
        result = api.request(
            "POST",
            "/auth/token/refresh",
            {"refreshToken": refresh_token or "[refresh-token-from-credential-store]"},
            idempotency_key=args.idempotency_key,
            dry_run=args.dry_run,
            auth_required=False,
            send_token=False,
        )
        if not args.dry_run:
            data = response_data(result)
            access_token = first_value(data, "accessToken", "access_token")
            if not access_token:
                raise ApiError("refresh response did not include accessToken", body=redact(result))
            api.credentials.merge({
                "accessToken": access_token,
                "refreshToken": first_value(data, "refreshToken", "refresh_token") or refresh_token,
                "expiresAt": first_value(data, "expiresAt", "expires_at"),
                "expiresIn": first_value(data, "expiresIn", "expires_in"),
                "scopes": first_value(data, "scopes", "scope"),
            })
            return {"authenticated": True, "refreshed": True, "credentialsFile": str(api.credentials.path)}
        return result
    if args.command == "auth-session":
        return api.request("GET", "/auth/session", dry_run=args.dry_run)
    if args.command == "auth-connections":
        return api.request("GET", "/auth/connections", dry_run=args.dry_run)
    if args.command == "auth-revoke":
        result = api.request(
            "POST",
            "/auth/token/revoke",
            {},
            idempotency_key=args.idempotency_key,
            dry_run=args.dry_run,
        )
        if not args.dry_run:
            api.credentials.clear()
            return {"revoked": True, "credentialsRemoved": True}
        return result
    if args.command == "models":
        return api.request(
            "GET",
            "/studio/models",
            query={"assetType": args.asset_type},
            dry_run=args.dry_run,
        )
    if args.command == "resolve-models":
        constraints = load_json(args.constraints) if args.constraints else {}
        return api.request(
            "POST",
            "/studio/models/resolve",
            {
                "assetType": args.asset_type,
                "constraints": constraints,
                "strategy": args.strategy,
            },
            idempotency_key=args.idempotency_key,
            dry_run=args.dry_run,
        )
    if args.command == "plan":
        plan = load_json(args.plan)
        return api.request(
            "POST",
            "/studio/plans",
            {
                "plan": plan,
                "confirm": args.confirm,
                "maxCredits": args.max_credits,
                "modelStrategy": args.model_strategy,
            },
            idempotency_key=args.idempotency_key,
            dry_run=args.dry_run,
        )
    if args.command == "instance":
        plan = load_json(args.plan)
        return api.request(
            "POST",
            "/studio/instances",
            {
                "name": args.name,
                "plan": plan,
                "planHash": plan.get("planHash"),
            },
            idempotency_key=args.idempotency_key,
            dry_run=args.dry_run,
        )
    if args.command == "ensure-folders":
        folders = load_json(args.folders)
        instance_id = urllib.parse.quote(args.instance_id, safe="")
        return api.request(
            "POST",
            f"/studio/instances/{instance_id}/folders/ensure",
            {"folders": folders},
            idempotency_key=args.idempotency_key,
            dry_run=args.dry_run,
        )
    if args.command in {"assets", "folders", "exports", "ui-links"}:
        instance_id = urllib.parse.quote(args.instance_id, safe="")
        suffix = {
            "assets": "assets",
            "folders": "folders",
            "exports": "exports",
            "ui-links": "ui-links",
        }[args.command]
        query = {}
        for key, value in ({
            "rootTaskId": getattr(args, "root_task_id", None),
            "limit": getattr(args, "limit", None),
        } if args.command == "exports" else {
            "collectionId": getattr(args, "collection_id", None),
            "assetType": getattr(args, "asset_type", None),
            "cursor": getattr(args, "cursor", None),
            "limit": getattr(args, "limit", None),
        }).items():
            if value is not None:
                query[key] = str(value)
        return api.request(
            "GET", f"/studio/instances/{instance_id}/{suffix}",
            query=query, dry_run=args.dry_run
        )
    if args.command in {"upload-init", "asset-import", "asset-place"}:
        instance_id = urllib.parse.quote(args.instance_id, safe="")
        payload = load_json(args.payload)
        if args.command == "upload-init":
            path = f"/studio/instances/{instance_id}/assets/uploads"
            method = "POST"
        elif args.command == "asset-import":
            path = f"/studio/instances/{instance_id}/assets/import"
            method = "POST"
        else:
            path = f"/studio/instances/{instance_id}/assets/placements"
            method = "PATCH"
        return api.request(
            method, path, payload,
            idempotency_key=args.idempotency_key,
            dry_run=args.dry_run,
        )
    if args.command == "upload-complete":
        instance_id = urllib.parse.quote(args.instance_id, safe="")
        upload_id = urllib.parse.quote(args.upload_id, safe="")
        return api.request_multipart(
            "POST",
            f"/studio/instances/{instance_id}/assets/uploads/{upload_id}/complete",
            args.file,
            idempotency_key=args.idempotency_key,
            dry_run=args.dry_run,
        )
    if args.command == "compile":
        plan = load_json(args.plan)
        instance_id = urllib.parse.quote(args.instance_id, safe="")
        return api.request(
            "POST",
            f"/studio/instances/{instance_id}/workflows/compile",
            {
                "plan": plan,
                "planHash": args.plan_hash,
                "confirm": args.confirm,
                "maxCredits": args.max_credits,
            },
            idempotency_key=args.idempotency_key,
            dry_run=args.dry_run,
        )
    if args.command == "run":
        workflow_id = urllib.parse.quote(args.workflow_instance_id, safe="")
        return api.request(
            "POST",
            f"/studio/workflows/{workflow_id}/runs",
            {
                "planHash": args.plan_hash,
                "confirm": args.confirm,
                "maxCredits": args.max_credits,
                "retryOfRunId": args.retry_of_run_id,
            },
            idempotency_key=args.idempotency_key,
            dry_run=args.dry_run,
        )
    if args.command == "schedule-create":
        plan = load_json(args.plan)
        workflow_id = urllib.parse.quote(args.workflow_instance_id, safe="")
        payload = {
            "name": args.name,
            "cronExpression": args.cron_expression,
            "timezone": args.timezone,
            "plan": plan,
            "planHash": args.plan_hash,
            "maxCredits": args.max_credits,
            "runtimeInputs": load_json(args.runtime_inputs) if args.runtime_inputs else {},
            "confirm": args.confirm,
        }
        return api.request(
            "POST",
            f"/studio/workflows/{workflow_id}/schedules",
            payload,
            idempotency_key=args.idempotency_key,
            dry_run=args.dry_run,
        )
    if args.command == "schedules":
        query = {}
        if args.status:
            query["status"] = args.status
        if args.limit:
            query["limit"] = str(args.limit)
        return api.request("GET", "/studio/schedules", query=query, dry_run=args.dry_run)
    if args.command == "schedule-update":
        schedule_id = urllib.parse.quote(args.schedule_id, safe="")
        payload = {
            key: value for key, value in {
                "name": args.name,
                "cronExpression": args.cron_expression,
                "timezone": args.timezone,
                "status": args.status,
                "maxCredits": args.max_credits,
                "runtimeInputs": load_json(args.runtime_inputs) if args.runtime_inputs else None,
            }.items() if value is not None
        }
        return api.request(
            "PATCH",
            f"/studio/schedules/{schedule_id}",
            payload,
            idempotency_key=args.idempotency_key,
            dry_run=args.dry_run,
        )
    if args.command == "schedule-delete":
        schedule_id = urllib.parse.quote(args.schedule_id, safe="")
        return api.request(
            "DELETE",
            f"/studio/schedules/{schedule_id}",
            idempotency_key=args.idempotency_key,
            dry_run=args.dry_run,
        )
    if args.command == "schedule-trigger":
        schedule_id = urllib.parse.quote(args.schedule_id, safe="")
        return api.request(
            "POST",
            f"/studio/schedules/{schedule_id}/trigger",
            {"confirm": args.confirm},
            idempotency_key=args.idempotency_key,
            dry_run=args.dry_run,
        )
    if args.command in {"status", "events"}:
        run_id = urllib.parse.quote(args.run_id, safe="")
        suffix = "/events" if args.command == "events" else ""
        return api.request("GET", f"/studio/runs/{run_id}{suffix}", dry_run=args.dry_run)
    if args.command == "result":
        run_id = urllib.parse.quote(args.run_id, safe="")
        return api.request("GET", f"/studio/runs/{run_id}/result", dry_run=args.dry_run)
    if args.command in {"export-status", "export-retry", "download-ticket"}:
        export_id = urllib.parse.quote(args.export_id, safe="")
        if args.command == "export-status":
            return api.request("GET", f"/studio/exports/{export_id}", dry_run=args.dry_run)
        suffix = "retry" if args.command == "export-retry" else "download-ticket"
        payload = load_json(args.payload) if args.payload else {}
        return api.request(
            "POST", f"/studio/exports/{export_id}/{suffix}", payload,
            idempotency_key=args.idempotency_key,
            dry_run=args.dry_run,
        )
    raise ApiError(f"unknown command: {args.command}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    auth_start = subparsers.add_parser("auth-start")
    auth_start.add_argument("--client-type", choices=["codex", "chatgpt_work", "zcode", "workbuddy"], default="codex")
    auth_start.add_argument("--client-instance-id", required=True)
    auth_start.add_argument("--display-name", required=True)
    auth_start.add_argument("--scope", action="append", required=True)
    add_common(auth_start)

    auth_poll = subparsers.add_parser("auth-poll")
    auth_poll.add_argument("--device-code")
    add_common(auth_poll)

    for name in ("auth-refresh", "auth-session", "auth-connections"):
        auth = subparsers.add_parser(name)
        add_common(auth)

    add_common(subparsers.add_parser("auth-revoke"))

    models = subparsers.add_parser("models")
    models.add_argument("--asset-type", choices=["image", "video"], required=True)
    add_common(models)

    resolve = subparsers.add_parser("resolve-models")
    resolve.add_argument("--asset-type", choices=["image", "video"], required=True)
    resolve.add_argument("--constraints", help="JSON file or -")
    resolve.add_argument("--strategy", default="balanced")
    add_common(resolve)

    plan = subparsers.add_parser("plan")
    plan.add_argument("plan")
    plan.add_argument("--confirm", action="store_true")
    plan.add_argument("--max-credits", type=int)
    plan.add_argument("--model-strategy", default="balanced")
    add_common(plan)

    instance = subparsers.add_parser("instance")
    instance.add_argument("--name", required=True)
    instance.add_argument("--plan", required=True)
    add_common(instance)

    folders = subparsers.add_parser("ensure-folders")
    folders.add_argument("--instance-id", required=True)
    folders.add_argument("--folders", required=True)
    add_common(folders)

    assets = subparsers.add_parser("assets")
    assets.add_argument("--instance-id", required=True)
    assets.add_argument("--collection-id")
    assets.add_argument("--asset-type", choices=["image", "video", "audio", "document"])
    assets.add_argument("--cursor")
    assets.add_argument("--limit", type=int)
    add_common(assets)

    folders_list = subparsers.add_parser("folders")
    folders_list.add_argument("--instance-id", required=True)
    add_common(folders_list)

    exports = subparsers.add_parser("exports")
    exports.add_argument("--instance-id", required=True)
    exports.add_argument("--root-task-id")
    exports.add_argument("--limit", type=int)
    add_common(exports)

    ui_links = subparsers.add_parser("ui-links")
    ui_links.add_argument("--instance-id", required=True)
    add_common(ui_links)

    for name in ("upload-init", "asset-import", "asset-place"):
        asset_mutation = subparsers.add_parser(name)
        asset_mutation.add_argument("--instance-id", required=True)
        asset_mutation.add_argument("--payload", required=True, help="JSON file or -")
        add_common(asset_mutation)

    upload_complete = subparsers.add_parser("upload-complete")
    upload_complete.add_argument("--instance-id", required=True)
    upload_complete.add_argument("--upload-id", required=True)
    upload_complete.add_argument("--file", required=True)
    add_common(upload_complete)

    compile_parser = subparsers.add_parser("compile")
    compile_parser.add_argument("--instance-id", required=True)
    compile_parser.add_argument("plan")
    compile_parser.add_argument("--plan-hash")
    compile_parser.add_argument("--confirm", action="store_true")
    compile_parser.add_argument("--max-credits", type=int, required=True)
    add_common(compile_parser)

    run = subparsers.add_parser("run")
    run.add_argument("--workflow-instance-id", required=True)
    run.add_argument("--plan-hash", required=True)
    run.add_argument("--confirm", action="store_true")
    run.add_argument("--max-credits", type=int, required=True)
    run.add_argument("--retry-of-run-id")
    add_common(run)

    schedule_create = subparsers.add_parser("schedule-create")
    schedule_create.add_argument("--workflow-instance-id", required=True)
    schedule_create.add_argument("--name", required=True)
    schedule_create.add_argument("--cron-expression", required=True)
    schedule_create.add_argument("--timezone", default="Asia/Shanghai")
    schedule_create.add_argument("--plan", required=True)
    schedule_create.add_argument("--plan-hash", required=True)
    schedule_create.add_argument("--max-credits", type=int, required=True)
    schedule_create.add_argument("--runtime-inputs")
    schedule_create.add_argument("--confirm", action="store_true")
    add_common(schedule_create)

    schedules = subparsers.add_parser("schedules")
    schedules.add_argument("--status", choices=["active", "paused", "cancelled", "error"])
    schedules.add_argument("--limit", type=int)
    add_common(schedules)

    schedule_update = subparsers.add_parser("schedule-update")
    schedule_update.add_argument("--schedule-id", required=True)
    schedule_update.add_argument("--name")
    schedule_update.add_argument("--cron-expression")
    schedule_update.add_argument("--timezone")
    schedule_update.add_argument("--status", choices=["active", "paused"])
    schedule_update.add_argument("--max-credits", type=int)
    schedule_update.add_argument("--runtime-inputs")
    add_common(schedule_update)

    schedule_delete = subparsers.add_parser("schedule-delete")
    schedule_delete.add_argument("--schedule-id", required=True)
    add_common(schedule_delete)

    schedule_trigger = subparsers.add_parser("schedule-trigger")
    schedule_trigger.add_argument("--schedule-id", required=True)
    schedule_trigger.add_argument("--confirm", action="store_true")
    add_common(schedule_trigger)

    for name in ("status", "events"):
        status = subparsers.add_parser(name)
        status.add_argument("--run-id", required=True)
        add_common(status)
    result = subparsers.add_parser("result")
    result.add_argument("--run-id", required=True)
    add_common(result)

    export_status = subparsers.add_parser("export-status")
    export_status.add_argument("--export-id", required=True)
    add_common(export_status)

    for name in ("export-retry", "download-ticket"):
        export_mutation = subparsers.add_parser(name)
        export_mutation.add_argument("--export-id", required=True)
        export_mutation.add_argument("--payload", help="optional JSON file or -")
        add_common(export_mutation)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        result = run_command(args)
    except (ApiError, OSError, json.JSONDecodeError) as exc:
        error: dict[str, Any] = {"error": str(exc)}
        if isinstance(exc, ApiError) and exc.body is not None:
            error["details"] = exc.body
        print(json.dumps(error, ensure_ascii=False, indent=2), file=sys.stderr)
        return 2
    print(json.dumps(redact(result), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
