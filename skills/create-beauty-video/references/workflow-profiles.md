# 视频规则 profile 框架

## 选择规则

每个新计划必须保存以下字段：

~~~json
{
  "workflowProfile": "ugc-commerce-v1",
  "promptProfile": null,
  "profileVersion": "draft-0",
  "rulesHash": "draft:ugc-commerce-v1-rules-pending"
}
~~~

- `workflowProfile` 选择视频类型方法论。
- `promptProfile` 可选择市场、真人感或镜头提示词细分规则；没有批准规则时为
  `null`，不得由 Codex 自行补一个名称。
- `profileVersion` 是人类可读版本。
- `rulesHash` 是批准规则文件原始字节的 `sha256:<64-hex>`。规则未交付时只可
  使用 `draft:<reason>` 做结构预演。

`draft:` profile 不允许生成最终提示词、发起付费 run 或发布 schedule。Codex
必须列出缺失规则并停在确认门；登录、实例、资产上传/分类、动态模型查询、工作流
结构预演和网站回链仍可执行。

## 规则优先级

按以下顺序合并，越靠后优先级越高：

1. `workflowProfile`
2. `promptProfile`
3. `projectFacts`
4. `shotOverrides`

任何 profile 都不能覆盖用户确认的人物、产品、场景、品牌或包装事实。profile
名称不能用于推断五官、肤色、服装、宗教元素、产品外观或模型供应商。

## 当前 registry

| ID | 状态 | 用途 |
| --- | --- | --- |
| `ugc-commerce-v1` | scaffold | UGC 带货视频；等待用户提供最终规则 |
| `id_tiktok_beauty_ugc_real_person_v1` | optional prompt profile | 仅在用户显式选择时加载现有印尼真人提示词约束 |

真人短剧、AI 动漫等后续 profile 使用相同 API，仅增加独立 reference、fixture 和
hash，不复制登录、实例、资产、工作流、计费或导出逻辑。
