# 计划与提示词字段

## BeautyVideoPlan 最小形状

~~~json
{
  "schemaVersion": 1,
  "name": "daily-beauty-demo",
  "workflowProfile": "ugc-commerce-v1",
  "promptProfile": null,
  "profileVersion": "draft-0",
  "rulesHash": "draft:ugc-commerce-v1-rules-pending",
  "source": {
    "scriptText": "...",
    "referenceVideoAssetId": "asset-id"
  },
  "continuityBible": {},
  "assetMap": [
    {
      "assetId": "asset-id",
      "role": "user-confirmed-role",
      "collectionId": "existing-collection-id",
      "confirmed": true
    }
  ],
  "shots": [
    {
      "shotId": "shot-01",
      "startSec": 0,
      "endSec": 3.2,
      "durationSec": 3.2,
      "actions": [
        {"id": "a1", "text": "raise eyes toward lens", "startSec": 0, "endSec": 1.4}
      ],
      "inputAssetIds": ["asset-id"],
      "productAngleRefIds": [],
      "promptFacts": {
        "startState": "approved_current_makeup_state_before_action",
        "durationSeconds": 3.2,
        "identityAnchors": ["approved visible face shape", "natural eye asymmetry"],
        "referenceAssetIds": ["person-approved-closeup", "scene-window"],
        "personVisible": true,
        "makeupState": {"base": "current light base", "skinFinish": "visible pores and natural sheen"},
        "camera": {"shotSize": "head_and_shoulders", "gazeAtT0": "camera", "movement": "locked with subtle handheld breath"},
        "lighting": {"keyDirection": "front_left_45_degrees", "quality": "soft window daylight", "whiteBalance": "neutral slightly warm"},
        "productState": {"visible": false},
        "primaryAction": {"name": "single gaze shift", "actionWindowSeconds": [0.4, 1.4], "start": "eyes at camera", "path": "short gaze shift", "end": "gaze holds", "pace": "normal everyday speed"},
        "expressionArc": {"baseline": "relaxed closed mouth", "trigger": "seeing makeup result", "reaction": "small eye and mouth-corner change", "recovery": "soft exhale"},
        "audioMode": "post_tts_visual"
      },
      "firstFramePrompt": "...",
      "videoPrompt": "...",
      "imageModel": {"scenarioModelId": "resolved-by-server"},
      "videoModel": {"scenarioModelId": "resolved-by-server"}
    }
  ],
  "modelStrategy": {
    "confirmed": true,
    "image": {"scenarioModelId": "...", "capability": "image2image"},
    "video": {"scenarioModelId": "...", "capability": "image2video"}
  },
  "outputCollections": {
    "firstFrame": "confirmed-collection-id",
    "clip": "confirmed-collection-id",
    "reference": "confirmed-collection-id",
    "final": "confirmed-collection-id"
  },
  "assetGeneration": [
    {
      "assetId": "product-angle-01",
      "kind": "image",
      "prompt": "...",
      "collectionId": "confirmed-collection-id",
      "targetShotIds": ["shot-01"]
    }
  ],
  "constraints": {
    "aspectRatio": "9:16",
    "maxCredits": null
  }
}
~~~

`workflowProfile` 是视频工作流方法论，`promptProfile` 是可选的细分提示词规则，
二者都不是模型 ID。`profileVersion` 与 `rulesHash` 固化本次规则快照。`draft:`
hash 只表示规则尚未确定，可用于结构预演，但不得据此编写最终提示词、发起付费
运行或发布 schedule；批准后的规则文件使用其原始字节 SHA-256，格式为
`sha256:<64-hex>`。

firstFramePrompt 是静态画面约束，videoPrompt 是动作和摄影时序约束。
两者都应引用连续性圣经中的确认事实。imageModel 和 videoModel 只能填入
模型查询接口返回并被用户确认的 scenarioModelId，不要把供应商名称当作
稳定 ID。

## 镜头提示词编译

下面的字段顺序只是中立的数据组织方式，不是最终生成规则。具体动作数量、写法、
质检和重试策略必须来自用户批准且 hash 已固定的 profile。

首帧提示词按这个顺序组织：主体身份 -> 产品状态/角度 -> 场景和光线 ->
构图/镜头 -> 妆容和材质 -> 风格与负面约束。

视频提示词按这个顺序组织：首帧承接 -> 已批准动作序列 -> 镜头运动 -> 节奏/时长
-> 结束状态 -> 不改变锚点的负面约束。避免写“换一个人”“包装变成”“改变
妆容”等会破坏连续性的指令；需要改变视觉状态时重新生成下一镜头首帧。

只有显式选择 `id_tiktok_beauty_ugc_real_person_v1` 时，才加载其专用
`promptFacts` 校验；不要把该市场规则套用到其他 workflow profile。
