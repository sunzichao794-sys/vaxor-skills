"""Provider-neutral public Vaxor Automation connector primitives."""

from .vaxor_automation import (
    API_ROOT_SUFFIX,
    HOST_ADAPTERS,
    PUBLIC_SCOPES,
    build_preview_request,
    redact_secrets,
    validate_external_plan,
)

__all__ = [
    "API_ROOT_SUFFIX",
    "HOST_ADAPTERS",
    "PUBLIC_SCOPES",
    "build_preview_request",
    "redact_secrets",
    "validate_external_plan",
]
