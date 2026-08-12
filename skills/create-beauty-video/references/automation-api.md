# Vaxor Automation API

Set `VAXOR_AUTOMATION_BASE_URL` to the Vaxor API root, for example
`https://studio.example/api/automation`. The client uses `/v1/auth` for device
authorization and `/v2/studio` for all public production operations.

## Authorization

Use device authorization before any instance, asset, workflow, run, or export
request. The client stores rotating tokens only in its local restricted
credential file. A browser session confirms the device code; a browser JWT,
provider key, or payment credential is never passed to the Skill.

Suggested minimum scopes: `studio:instances:read`, `studio:instances:write`,
`studio:assets:read`, `studio:assets:write`, `studio:models:read`,
`studio:workflows:write`, `studio:runs:read`, `studio:runs:write`,
`studio:exports:read`, `studio:exports:write`.

## Public V2 operations

~~~text
GET    /v2/studio/models?assetType=image|video
POST   /v2/studio/models/resolve
POST   /v2/studio/plans/preview
POST   /v2/studio/instances
GET    /v2/studio/instances/:instanceId
PATCH  /v2/studio/instances/:instanceId
POST   /v2/studio/instances/:instanceId/folders/ensure
GET    /v2/studio/instances/:instanceId/folders
GET    /v2/studio/instances/:instanceId/assets
POST   /v2/studio/instances/:instanceId/assets/uploads
POST   /v2/studio/instances/:instanceId/assets/uploads/:uploadId/complete
POST   /v2/studio/instances/:instanceId/assets/import
PATCH  /v2/studio/instances/:instanceId/assets/placements
POST   /v2/studio/instances/:instanceId/workflows/compile
POST   /v2/studio/workflows/:workflowInstanceId/runs
GET    /v2/studio/runs/:runId
GET    /v2/studio/runs/:runId/events
GET    /v2/studio/runs/:runId/result
GET    /v2/studio/instances/:instanceId/exports
GET    /v2/studio/exports/:exportId
POST   /v2/studio/exports/:exportId/retry
POST   /v2/studio/exports/:exportId/download-ticket
GET    /v2/studio/instances/:instanceId/ui-links
~~~

`ExternalWorkflowPlan` has `{ schemaVersion, name, steps, output? }`. It has
no Vaxor profile, rule hash, private artifact, private fact, or origin field.
The server rejects those fields even if a caller bypasses local validation.

An image/video step holds user-authored prompt text. Vaxor returns current model
capabilities; server-side compilation validates capability, asset ownership,
collections, maximum credits, and billing again before a run. `finalCollectionId`
is optional and requests final composition only when the plan contains video.

Use the existing folder/placement endpoints for asset classification. Folder
names and categories are user-controlled. The API never creates a parallel
classification store.

## Completion semantics

`preview` and `compile` do not generate media. `queued` or `running` is not
completion. Confirm the run result, then the export record. A download ticket
is short-lived delivery data and must not be persisted by the Skill.
