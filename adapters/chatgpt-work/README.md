# ChatGPT Work adapter (Verification)

ChatGPT Work has no verified native Skill installation contract in this
release. Use the Portable Markdown/OpenAPI/CLI adapter. This package remains
`Verification` until a real Work tool invocation is tested end to end.

Use `clientType=chatgpt_work` for device authorization. The host must keep the
token in its protected credential store and send it only as an Authorization
header. It must call public Vaxor endpoints only and must not add Provider
credentials or private Vaxor prompt fields.
