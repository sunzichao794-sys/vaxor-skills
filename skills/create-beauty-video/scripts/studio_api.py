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


class ApiError(RuntimeError):
    def __init__(self, message: str, *, status: int | None = None, body: Any = None) -> None:
        super().__init__(message)
        self.status = status
        self.body = body


def load_json(path: str) -> Any:
    return json.loads(sys.stdin.read() if path == "-" else Path(path).expanduser().read_text(encoding="utf-8"))


def redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: "[REDACTED]" if key.replace("_", "").lower() in SECRET_KEYS else redact(item) for key, item in value.items()}
    if isinstance(value, list):
        return [redact(item) for item in value]
    return value


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
            print(json.dumps({"dryRun": True, "method": method, "url": url, "headers": redact(headers), "body": redact(payload), "idempotencyKey": key}, ensure_ascii=False, indent=2))
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
            raise ApiError(f"Vaxor API returned HTTP {exc.code}", status=exc.code, body=redact(body)) from exc
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
            raise ApiError(f"Vaxor API returned HTTP {exc.code}", status=exc.code, body=redact(exc.read().decode("utf-8", errors="replace"))) from exc


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
    if args.command == "preview":
        return api.request("POST", f"{STUDIO}/plans/preview", {"plan": load_json(args.plan)})
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
        return api.request("POST", f"{STUDIO}/instances/{q(args.instance_id)}/workflows/compile", {"plan": load_json(args.plan), "confirm": args.confirm, "maxCredits": args.max_credits})
    if args.command == "run":
        return api.request("POST", f"{STUDIO}/workflows/{q(args.workflow_instance_id)}/runs", {"planHash": args.plan_hash, "confirm": args.confirm, "maxCredits": args.max_credits, "retryOfRunId": args.retry_of_run_id})
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
    preview = sub.add_parser("preview"); preview.add_argument("plan"); common(preview)
    instance = sub.add_parser("instance"); instance.add_argument("--name", required=True); instance.add_argument("--description"); common(instance)
    rename = sub.add_parser("rename-instance"); rename.add_argument("--instance-id", required=True); rename.add_argument("--name", required=True); common(rename)
    folders = sub.add_parser("ensure-folders"); folders.add_argument("--instance-id", required=True); folders.add_argument("--folders", required=True); common(folders)
    for name in ("folders", "exports", "ui-links"):
        item = sub.add_parser(name); item.add_argument("--instance-id", required=True); item.add_argument("--limit", type=int); common(item)
    assets = sub.add_parser("assets"); assets.add_argument("--instance-id", required=True); assets.add_argument("--collection-id"); assets.add_argument("--asset-type", choices=["image", "video", "audio", "document"]); assets.add_argument("--cursor"); assets.add_argument("--limit", type=int); common(assets)
    for name in ("upload-init", "asset-import", "asset-place"):
        item = sub.add_parser(name); item.add_argument("--instance-id", required=True); item.add_argument("--payload", required=True); common(item)
    complete = sub.add_parser("upload-complete"); complete.add_argument("--instance-id", required=True); complete.add_argument("--upload-id", required=True); complete.add_argument("--file", required=True); common(complete)
    compile_command = sub.add_parser("compile"); compile_command.add_argument("--instance-id", required=True); compile_command.add_argument("plan"); compile_command.add_argument("--confirm", action="store_true"); compile_command.add_argument("--max-credits", type=int, required=True); common(compile_command)
    run = sub.add_parser("run"); run.add_argument("--workflow-instance-id", required=True); run.add_argument("--plan-hash", required=True); run.add_argument("--confirm", action="store_true"); run.add_argument("--max-credits", type=int, required=True); run.add_argument("--retry-of-run-id"); common(run)
    for name in ("status", "events", "result"):
        item = sub.add_parser(name); item.add_argument("--run-id", required=True); common(item)
    for name in ("export-status", "export-retry", "download-ticket"):
        item = sub.add_parser(name); item.add_argument("--export-id", required=True); item.add_argument("--payload"); common(item)
    return root


def main() -> int:
    try:
        result = run_command(parser().parse_args())
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
