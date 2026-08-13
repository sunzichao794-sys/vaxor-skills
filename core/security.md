# Public Skill security contract

This contract applies to Codex, all Portable host adapters, and any future
native adapter.

## Authorization

- Start device authorization at `/v1/auth/device/code` with the smallest
  scopes needed for the requested action.
- Open only the `verificationUri` or `verificationUriComplete` returned by
  Vaxor. Never construct an approval URL or append a token to a URL.
- Poll `/v1/auth/device/token`, then store rotating access/refresh tokens only
  in the host's protected credential store.
- Send access tokens only in the `Authorization: Bearer` header.
- Revoke with `/v1/auth/token/revoke` and delete the local credential record
  when the user disconnects the host.

## Instance and asset ownership

The Vaxor backend is the authority for current-user and current-instance
ownership. A host may send an instance ID and public `resourceId` references,
but it must never send or trust `objectKey`, signed delivery URLs, provider
IDs, or a URL supplied by a user as proof of ownership. On a 403/404, stop and
surface a safe access error; do not retry with another user's resource.

## Preview and Run

`POST /v2/studio/plans/preview` and workflow compile are planning/validation
operations. Preview must not create a run, reserve credits, call a provider,
or write a final asset. Show the returned plan to the user and wait for an
explicit approval before Compile/Run. A queued or running run is not complete;
read the persisted result and export record before reporting success.

## Public boundary

Never include private Vaxor rule hashes, prompt artifacts, private profiles,
provider credentials, internal workflow origins, or hidden model parameters in
the Skill package, plan JSON, logs, URLs, or chat output. The public API and the
server-side policy remain the source of truth.
