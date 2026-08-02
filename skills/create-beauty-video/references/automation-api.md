# Automation API 客户端约定

`TIANZUO_AUTOMATION_BASE_URL` 必须指向 Tianzuo 后端的
`/api/automation/v1` 根路径，例如 `https://studio.example/api/automation/v1`。
Skill 不保存浏览器 JWT、供应商密钥、支付凭据或持久化的临时下载地址。

## 设备授权

所有创建实例、上传资产、编译工作流、运行、定时和导出操作都必须先经过设备授权。

1. `POST /auth/device/code`，提交 `clientType`、稳定的 `clientInstanceId`、显示名和最小 scope 集合。
2. 向用户展示服务端返回的 `verificationUriComplete` 和 `userCode`。用户必须在已登录的网站账户中确认或拒绝该请求。
3. 按服务端返回的 `interval` 调用 `POST /auth/device/token`。仅在授权完成时才会返回短期 Access Token 和可轮换 Refresh Token。
4. 用 `POST /auth/token/refresh` 轮换；用 `POST /auth/token/revoke` 撤销当前连接；用 `GET /auth/session` 获取会员、积分和 scope 的服务端预检。

Access/Refresh Token 只保存在宿主的受限凭据存储中。Python client 使用
`~/.config/tianzuo/automation-credentials.json` 且权限为 `0600`。兼容环境变量
`TIANZUO_AUTOMATION_TOKEN` 仅用于受控开发或服务账号，不能作为普通用户登录方案。

## 生产资源

~~~text
GET    /studio/models?assetType=image|video
POST   /studio/models/resolve
POST   /studio/plans
POST   /studio/instances
GET    /studio/instances/:instanceId
PATCH  /studio/instances/:instanceId
POST   /studio/instances/:instanceId/folders/ensure
GET    /studio/instances/:instanceId/folders
GET    /studio/instances/:instanceId/assets
POST   /studio/instances/:instanceId/assets/uploads
POST   /studio/instances/:instanceId/assets/uploads/:uploadId/complete
POST   /studio/instances/:instanceId/assets/import
PATCH  /studio/instances/:instanceId/assets/placements
POST   /studio/instances/:instanceId/workflows/compile
POST   /studio/workflows/:workflowInstanceId/runs
GET    /studio/runs/:runId
GET    /studio/runs/:runId/events
GET    /studio/runs/:runId/result
GET    /studio/instances/:instanceId/exports
GET    /studio/exports/:exportId
POST   /studio/exports/:exportId/retry
POST   /studio/exports/:exportId/download-ticket
GET    /studio/instances/:instanceId/ui-links
GET    /studio/requests/:idempotencyKey
GET    /studio/schedules
POST   /studio/workflows/:workflowInstanceId/schedules
GET    /studio/schedules/:scheduleId
PATCH  /studio/schedules/:scheduleId
DELETE /studio/schedules/:scheduleId
POST   /studio/schedules/:scheduleId/trigger
~~~

模型、会员资格、实际价格、可用积分、输入端口和所有权都是服务器真值。Skill 每次
都查询模型投影；不得写死供应商、模型名、价格或可用性。

## 实例资产和分类

分类继续使用实例现有的文件夹能力，不创建独立的资产分类表。`产品图 / 人物 /
场景 / 首帧 / 片段` 只能作为建议角色；Skill 先提出，用户确认后才调用现有
folder/collection placement API。用户可以改名、合并、省略或增加分类。

上传是两步服务器代理会话：

1. `POST .../assets/uploads` 发送 `fileName`、`mimeType`、`sizeBytes`，可选
   `title`、`collectionId`、`folderId`。
2. 用返回 `upload.url` 对应的 `POST .../complete` 发送唯一的 multipart 字段
   `file`。会话会绑定用户、实例、文件名、MIME、长度和过期时间。

`POST .../assets/import` 只接受 HTTP(S) 远程图片。服务端完成 URL 安全校验、图片
导入和存储；脚本或参考视频必须走上传会话。`PATCH .../assets/placements` 使用
`operation`（`assign`、`remove`、`restore_default`）、`assetKeys`、可选 `folderId`
和 `expectedVersion`，以复用现有文件夹并发控制。

## 计划、规则与付费确认

每个新计划记录 `workflowProfile`、`promptProfile`、`profileVersion`、`rulesHash`。
没有用户交付并批准的规则文件时使用 `draft:` hash，只能做结构预演、建实例、传素材、
查模型和回链网站；不能编写最终提示词、发起付费运行或发布 schedule。

`POST /studio/plans` 是预演和确认门。工作流编译不产生付费任务。真实运行必须经过
已确认的预演，并提供 `planHash`、`confirm: true`、`maxCredits` 和稳定的
`Idempotency-Key`。服务端在入队前重新校验模型、资产、权限和账本。

首跑成功后才能创建 schedule。schedule 只重放已经确认并保存的计划与
`runtimeInputs`；发现素材、连续性、模型能力或规则 hash 漂移时必须停止并要求新的
用户确认。

## 状态、导出与网站回链

`queued`、`running` 或 HTTP 2xx 不代表视频完成。使用运行事件和
`GET /studio/runs/:runId/result` 判断节点结果，再使用 exports 接口确认合成和导出
记录。失败时携带 `retryOfRunId`，默认复用已经锁定且成功的上游结果。

下载 ticket 是短期、一次性用途的浏览器 URL，不能写进计划、资产 metadata 或长期
凭据。`GET .../ui-links` 返回无 bearer token 的网站地址：实例、资产、工作流、
时间线和导出。Skill 只能打开服务端返回的链接，不能自行拼接路由或把 token 加到 URL。

## Scope 和幂等

- 计划和编译使用 `studio:workflows:write`；真实运行使用 `studio:runs:write`。
- 资产读写分别使用 `studio:assets:read` 与 `studio:assets:write`。
- 导出读写分别使用 `studio:exports:read` 与 `studio:exports:write`。
- schedule 触发同时需要 `studio:schedules:write` 和 `studio:runs:write`。
- 所有改变状态的请求使用相同逻辑操作的显式 `Idempotency-Key` 重试，不能用新时间戳
  重放可能扣费的任务。

错误报告必须保留阶段、计划 hash、幂等键、runId（若存在）和是否安全重试。成功必须以
持久化实例、资产、工作流运行、时间线和导出记录为准。
