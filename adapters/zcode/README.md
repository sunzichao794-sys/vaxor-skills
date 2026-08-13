# ZCode adapter (Verification)

ZCode has no verified native Skill installation contract in this release. Use
the Portable Markdown/OpenAPI/CLI adapter and keep this package marked
`Verification` until a real ZCode installation, device authorization, Preview,
Run, persisted-result and error-boundary smoke passes.

Use `clientType=zcode` for device authorization. Do not claim that this
directory is a native ZCode plugin. The public API contract is at:
`../../skills/create-beauty-video/references/automation-openapi.json`.

After installation, the host must show its own user-authored plan, call Preview,
wait for approval, and only then call Compile/Run.
