"""Shared, provider-neutral contract helpers for Vaxor host adapters.

This module deliberately does not make network requests. Host integrations use
the public Automation API and may use the Codex reference client for transport.
Keeping the contract helpers side-effect free makes them safe to reuse from
portable Markdown/OpenAPI adapters and from local host runtimes.
"""

from __future__ import annotations

import copy
import hashlib
import json
from typing import Any, Mapping


API_ROOT_SUFFIX = "/api/automation"
PUBLIC_SCOPES = (
    "studio:instances:read",
    "studio:instances:write",
    "studio:assets:read",
    "studio:assets:write",
    "studio:models:read",
    "studio:workflows:write",
    "studio:runs:read",
    "studio:runs:write",
    "studio:exports:read",
    "studio:exports:write",
)

# These are contract descriptions, not claims that a host has a native Skill
# protocol. The four non-Codex hosts are intentionally Verification/Portable.
HOST_ADAPTERS: dict[str, dict[str, Any]] = {
    "codex": {
        "clientType": "codex",
        "status": "stable",
        "adapter": "native_skill",
        "installType": "codex_skill",
        "authMode": "device_code",
    },
    "zcode": {
        "clientType": "zcode",
        "status": "verification",
        "adapter": "portable",
        "installType": "markdown_openapi_cli",
        "authMode": "device_code",
    },
    "chatgpt_work": {
        "clientType": "chatgpt_work",
        "status": "verification",
        "adapter": "portable",
        "installType": "markdown_openapi_cli",
        "authMode": "device_code",
    },
    "workbuddy": {
        "clientType": "workbuddy",
        "status": "verification",
        "adapter": "portable",
        "installType": "markdown_openapi_cli",
        "authMode": "device_code",
    },
    "claude_code": {
        # The public auth DTO currently accepts `custom`, not `claude_code`.
        # Keep this mapping explicit until a native Claude Code contract exists.
        "clientType": "custom",
        "status": "verification",
        "adapter": "portable",
        "installType": "markdown_openapi_cli",
        "authMode": "device_code",
    },
    "portable": {
        "clientType": "custom",
        "status": "beta",
        "adapter": "portable",
        "installType": "markdown_openapi_cli",
        "authMode": "device_code",
    },
}

_SECRET_NAMES = {
    "authorization",
    "access_token",
    "accesstoken",
    "refresh_token",
    "refreshtoken",
    "device_code",
    "devicecode",
    "client_secret",
    "secret",
    "provider_token",
    "private_prompt_artifact",
    "object_key",
    "objectkey",
    "signed_url",
    "signedurl",
}
_FORBIDDEN_PLAN_KEYS = {
    "ruleshash",
    "rulehash",
    "privateprofile",
    "private_profile",
    "privatefact",
    "private_fact",
    "origin",
    "providercredential",
    "provider_credentials",
    "promptartifact",
    "prompt_artifact",
}


def _normalized_key(key: str) -> str:
    return "".join(character for character in key.lower() if character.isalnum())


def redact_secrets(value: Any) -> Any:
    """Return a printable copy without credentials or storage delivery data."""

    if isinstance(value, Mapping):
        result: dict[str, Any] = {}
        for key, item in value.items():
            normalized = _normalized_key(str(key))
            if normalized in {_normalized_key(name) for name in _SECRET_NAMES}:
                result[str(key)] = "[REDACTED]"
            else:
                result[str(key)] = redact_secrets(item)
        return result
    if isinstance(value, list):
        return [redact_secrets(item) for item in value]
    if isinstance(value, tuple):
        return tuple(redact_secrets(item) for item in value)
    return value


def _find_forbidden_keys(value: Any, path: str = "$") -> list[str]:
    found: list[str] = []
    if isinstance(value, Mapping):
        for key, item in value.items():
            normalized = _normalized_key(str(key))
            if normalized in {_normalized_key(name) for name in _FORBIDDEN_PLAN_KEYS}:
                found.append(f"{path}.{key}")
            found.extend(_find_forbidden_keys(item, f"{path}.{key}"))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            found.extend(_find_forbidden_keys(item, f"{path}[{index}]"))
    return found


def validate_external_plan(plan: Mapping[str, Any]) -> list[str]:
    """Validate public plan shape and reject private/internal fields.

    The server remains the source of truth. This helper only provides an early,
    host-neutral validation message and must never be treated as authorization.
    """

    errors: list[str] = []
    if not isinstance(plan, Mapping):
        return ["plan must be an object"]
    if plan.get("schemaVersion") != 1:
        errors.append("schemaVersion must be 1")
    if not isinstance(plan.get("name"), str) or not plan.get("name", "").strip():
        errors.append("name must be a non-empty string")
    steps = plan.get("steps")
    if not isinstance(steps, list) or not steps:
        errors.append("steps must be a non-empty array")
    else:
        seen: set[str] = set()
        for index, step in enumerate(steps):
            if not isinstance(step, Mapping):
                errors.append(f"steps[{index}] must be an object")
                continue
            step_id = step.get("id")
            if not isinstance(step_id, str) or not step_id.strip():
                errors.append(f"steps[{index}].id must be a non-empty string")
            elif step_id in seen:
                errors.append(f"steps[{index}].id must be unique")
            else:
                seen.add(step_id)
            if step.get("kind") not in {"image", "video"}:
                errors.append(f"steps[{index}].kind must be image or video")
            if not isinstance(step.get("prompt"), str) or not step.get("prompt", "").strip():
                errors.append(f"steps[{index}].prompt must be a non-empty string")
            if step.get("kind") == "video" and (
                not isinstance(step.get("durationSec"), (int, float))
                or step.get("durationSec", 0) <= 0
            ):
                errors.append(f"steps[{index}].durationSec must be positive for video")
    errors.extend(f"private field is not allowed: {path}" for path in _find_forbidden_keys(plan))
    return errors


def build_preview_request(
    *,
    instance_id: str,
    plan: Mapping[str, Any],
    idempotency_key: str | None = None,
) -> dict[str, Any]:
    """Build the public Preview request; no network or billing side effect."""

    if not isinstance(instance_id, str) or not instance_id.strip():
        raise ValueError("instance_id must be a non-empty string")
    errors = validate_external_plan(plan)
    if errors:
        raise ValueError("invalid external plan: " + "; ".join(errors))
    request: dict[str, Any] = {
        "path": "/v2/studio/plans/preview",
        "method": "POST",
        # The public V2 endpoint accepts the plan body. The instance is kept as
        # adapter metadata for ownership/UI routing; it is not invented as a
        # new public endpoint field.
        "instanceId": instance_id,
        "body": {"plan": copy.deepcopy(dict(plan))},
        "sideEffect": "preview_only",
    }
    if idempotency_key:
        request["idempotencyKey"] = idempotency_key
    else:
        request["idempotencyKey"] = hashlib.sha256(
            json.dumps(request["body"], ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest()[:32]
    return request
