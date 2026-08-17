---
name: create-beauty-video
description: "Use when a user wants to create or manage an authenticated Vaxor image or video workflow from Codex, ZCode, ChatGPT Work, WorkBuddy, Claude Code, or another supported host. This public connector uses device authorization, opaque model references, user-approved quote confirmations, and Vaxor-managed execution."
---

# Vaxor Public Media Connector

Use this Skill as an authenticated Vaxor control plane. The user and their
agent own creative analysis, shot planning, and prompts. Vaxor owns identity,
membership, published public model labels, billing, asset persistence, workflow
execution, and export records.

## Boundaries

- Use only `/api/automation/v1/auth` for device authorization and
  `/api/automation/v2/studio` for production operations.
- Submit only the user's own generic plan and prompt text. Do not request or
  infer private profiles, private artifacts, hidden implementation details, or
  protected execution metadata.
- Query models immediately before preview. Choose only from returned
  `modelRef`, public label, capability, and public parameter options.
- A plan uses `modelRef`, never a model identity. A confirmation uses
  `quoteConfirmation`, never a price implementation detail.
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
   Select an opaque `modelRef` from the current result.
5. Write a generic `ExternalWorkflowPlan`: one or more user-authored `image`
   or `video` steps. Each step supplies `id`, `kind`, `title`, `prompt`,
   `modelRef`, `capability`, and `collectionId`; video steps also supply
   `durationSec`. `parameters` may only use `aspectRatio`, `resolution`,
   `durationSec`, and `quantity` when listed by the selected capability.
6. Call `preview`, show its public prices and `quoteConfirmation` values, then
   ask the user to confirm the preview. The `compile` command requires the full
   step-to-confirmation list. Compilation does not generate media.
7. `compile` returns a new set of run confirmations. Call `run` only after the
   user confirms those values. Poll `status`, `events`, and `result`. Use the
   recorded `retryOfRunId` only for a known failed run.
8. Read `exports` and request a `download-ticket` only after the export record
   is ready. Request `ui-links` whenever the user wants to continue in Vaxor.

## Helpers

- `scripts/studio_api.py`: standard-library Vaxor API client. It validates the
  public plan contract and projects command output before printing. Use
  `--dry-run` to inspect a public request shape. Credentials are saved with mode
  `0600` in `~/.config/vaxor/automation-credentials.json`.
- `scripts/analyze_reference_video.py`: local technical frame extraction only.
  It does not create prompts or submit data.
- `references/automation-api.md`: scopes, V2 payload shape, state semantics,
  and endpoint contract.
- `references/automation-openapi.json`: OpenAPI description for hosts that can
  use an API contract directly.

Do not place bearer tokens in URLs, plans, asset metadata, prompts, browser
links, or chat output. Open only links returned by `ui-links`; never construct
website paths or append a token.
