---
name: create-beauty-video
description: "Use when a user wants to use Vaxor from Codex or a verified/Portable adapter for ChatGPT Work, ZCode, WorkBuddy, Claude Code, or another host to create and name an authenticated video-production instance, manage existing asset folders, upload or import assets, query live model capabilities, submit the user's own generic image/video workflow, run it, and retrieve exports. This is an API connector only: it never supplies Vaxor private prompting, orchestration, provider credentials, fixed model choices, or creative rules."
---

# Vaxor Video Connector

Use this Skill as an authenticated Vaxor control plane. The user and their
agent own creative analysis, shot planning, and prompts. Vaxor owns identity,
membership, models, billing, asset persistence, workflow execution, and export
records.

## Boundaries

- Use only `/api/automation/v1/auth` for device authorization and
  `/api/automation/v2/studio` for production operations.
- Submit only the user's own generic plan and prompt text. Never request,
  name, emulate, infer, or expose a Vaxor private profile, rule hash, prompt
  artifact, private fact, or any internal-only workflow origin.
- Query models immediately before compiling. Do not hard-code providers, model
  IDs, availability, price, or credit estimates.
- Reuse the instance's existing collections/folders for classification. Ask the
  user where assets belong; do not impose a taxonomy.
- Use a new explicit idempotency key for a new logical action, and reuse the
  same key only to retry that exact action.
- Do not treat an HTTP success, queue ID, or run ID as generated media. Verify
  the persisted run result and export status.

## Workflow

1. Run `scripts/studio_api.py auth-start` with the smallest scopes required,
   then direct the user to confirm in Vaxor and use `auth-poll`.
2. Create an instance with `instance`, or open an existing one using the
   server-returned `ui-links`.
3. Call `folders` and `assets`. Confirm folder/collection placement with the
   user before `ensure-folders`, `upload-init`/`upload-complete`,
   `asset-import`, or `asset-place`.
4. Call `models` or `resolve-models` for every required image/video capability.
   Choose only from the returned availability projection.
5. Write a generic `ExternalWorkflowPlan`: one or more user-authored `image`
   or `video` steps. Each step supplies `id`, `kind`, `title`, `prompt`,
   `scenarioModelId`, `capability`, `collectionId`; video steps also supply
   `durationSec`. Use `inputAssetIds` and prior `inputStepIds` for image
   references when the selected model supports them.
6. Call `preview` and show the validation output. Then call `compile` with the
   user-approved credit cap. Compilation has no provider generation side
   effect.
7. Call `run` only after the user confirms. Poll `status`, `events`, and
   `result`. Use the recorded `retryOfRunId` only for a known failed run.
8. Read `exports` and request a `download-ticket` only after the export record
   is ready. Request `ui-links` whenever the user wants to continue in Vaxor.

## Helpers

- `scripts/studio_api.py`: standard-library Vaxor API client. Use `--dry-run`
  to inspect mutating requests before execution. Credentials are saved with
  mode `0600` in `~/.config/vaxor/automation-credentials.json`.
- `scripts/analyze_reference_video.py`: local technical frame extraction only.
  It does not create prompts or submit data.
- `references/automation-api.md`: scopes, V2 payload shape, state semantics,
  and endpoint contract.
- `references/automation-openapi.json`: OpenAPI description for hosts that can
  use an API contract directly.

Do not place bearer tokens in URLs, plans, asset metadata, prompts, browser
links, or chat output. Open only links returned by `ui-links`; never construct
website paths or append a token.
