# Host adapters

These adapters all use the same public Vaxor Automation API and the shared
`core/` contract. They are intentionally thin: the host owns natural-language
intent, creative analysis and plan authoring; Vaxor owns authorization, asset
ownership, models, billing, workflow execution and exports.

## Status policy

- `stable`: verified native host package and the existing Codex regression.
- `verification`: the host has no verified native Skill protocol yet; use the
  provided Portable Markdown/OpenAPI/CLI instructions only.
- `beta`: the generic Portable adapter and offline contract are usable, but a
  host-specific runtime contract is not claimed.

Do not label an adapter Stable without real installation, authorization,
Preview, Run, persisted-result and error-boundary verification.
