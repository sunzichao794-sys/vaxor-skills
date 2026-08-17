# Vaxor Automation API v0.4

Set `VAXOR_AUTOMATION_BASE_URL` to the Vaxor API root, for example
`https://studio.example/api/automation`. The client uses `/v1/auth` for device
authorization and `/v2/studio` for all public media operations.

## Authorization

Use device authorization before any instance, asset, workflow, run, or export
request. The client stores rotating tokens only in its local restricted
credential file. A browser session confirms the device code; a browser JWT,
payment credential, or service credential is never passed to the Skill.

Suggested minimum scopes: `studio:instances:read`, `studio:instances:write`,
`studio:assets:read`, `studio:assets:write`, `studio:models:read`,
`studio:workflows:write`, `studio:runs:read`, `studio:runs:write`,
`studio:exports:read`, `studio:exports:write`.

## Public Model Contract

`GET /v2/studio/models?assetType=image|video` and
`POST /v2/studio/models/resolve` return public labels, capabilities, public
parameter options, and short-lived opaque `modelRef` values. A caller must use
the returned `modelRef` exactly as received.

`POST /v2/studio/models/quote` accepts:

```json
{
  "modelRef": "mr_example",
  "capability": "image2video",
  "parameters": {
    "aspectRatio": "9:16",
    "resolution": "720p",
    "durationSec": 5
  },
  "quantity": 1
}
```

The response provides a public label, normalized public parameters, cost,
expiry, and opaque `quoteConfirmation`. A public plan and confirmation may not
be reused by another authorization connection, after expiry, or after a
consuming compile/run action.

## Public Workflow Contract

`ExternalWorkflowPlan` has `{ schemaVersion, name, steps, output? }`. Each
image or video step uses `{ id, kind, title, prompt, modelRef, capability,
collectionId }`; video steps also use `durationSec`. Optional parameters are
only `aspectRatio`, `resolution`, `durationSec`, and `quantity` when the
selected capability listed them. Use `inputAssetIds` and earlier
`inputStepIds` only for image references supported by the selected capability.

The plan and confirmation formats deliberately do not include an internal model
identity, provider, binding, route, channel, SKU, revision, contract, raw
schema, runtime input contract, or workflow definition.

## Confirmation Flow

1. Call `POST /v2/studio/plans/preview` with a public plan and optional
   `maxCredits`.
2. Show the returned public step prices and `quoteConfirmation` values to the
   user. Do not compile until the user confirms them.
3. Call `POST /v2/studio/instances/:instanceId/workflows/compile` with:

```json
{
  "plan": { "schemaVersion": 1, "name": "example", "steps": [] },
  "confirm": true,
  "maxCredits": 100,
  "quoteConfirmations": [
    { "stepId": "step-1", "quoteConfirmation": "qc_from_preview" }
  ]
}
```

4. Compile returns a new step-to-confirmation list for the Run stage. Show that
   list and its price to the user again.
5. Call `POST /v2/studio/workflows/:workflowInstanceId/runs` only after that
   second confirmation. Submit `{ planHash, confirm: true, maxCredits,
   quoteConfirmations }`.
6. If Run reports `PRICE_CHANGED_RECONFIRM_REQUIRED`, discard the old
   confirmations and ask the user to approve its replacement confirmations.

## Public V2 Operations

```text
GET    /v2/studio/models?assetType=image|video
POST   /v2/studio/models/resolve
POST   /v2/studio/models/quote
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
```

## Completion Semantics

`preview` and `compile` do not generate media. `queued` or `running` is not
completion. Confirm the persisted run result, then the export record. A
download ticket is short-lived delivery data and must not be persisted by the
Skill.
