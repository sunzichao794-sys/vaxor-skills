# Vaxor Automation Core

`core/` contains the host-neutral public contract helpers for Vaxor Skills.
It does not contain a provider client, provider credential, billing logic, or
private Vaxor prompt/rule data. The Vaxor server remains the source of truth
for authorization, instance/resource ownership, model availability, billing,
workflow execution, and export records.

The core exposes:

- `HOST_ADAPTERS`: verified status and public auth mapping for each host.
- `validate_external_plan()`: early validation for a user-authored plan.
- `build_preview_request()`: a side-effect-free Preview request descriptor.
- `redact_secrets()`: safe logging projection.

See [`security.md`](security.md) for the authorization, ownership, Preview and
public-boundary invariants shared by every adapter.

Preview is not generation. A host must show the returned plan to the user and
obtain explicit approval before calling compile/run through the public API.
