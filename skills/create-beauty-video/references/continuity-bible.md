# Continuity Bible 字段

以下是建议的 JSON 形状。字段可以为空或 unknown，但不能凭空补写。

~~~json
{
  "version": 1,
  "confirmed": false,
  "person": {
    "facts": [],
    "sourceAssetIds": [],
    "confidence": "unknown"
  },
  "product": {
    "facts": [],
    "sourceAssetIds": [],
    "angleRefs": [],
    "confidence": "unknown"
  },
  "scene": {
    "facts": [],
    "sourceAssetIds": [],
    "confidence": "unknown"
  },
  "style": {
    "facts": [],
    "sourceAssetIds": [],
    "confidence": "unknown"
  },
  "openQuestions": []
}
~~~

印尼真人 UGC 镜头可在 shots[].promptFacts 保存以下结构化事实。它们是
编译首帧和视频提示词的输入，不是自动生成的人物设定：

~~~json
{
  "startState": "approved_current_makeup_state_before_action",
  "durationSeconds": 3,
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
}
~~~

每个事实可使用以下结构：

~~~json
{
  "value": "neutral warm key light from camera left",
  "source": "reference_frame",
  "sourceRef": "shot-02@4.20s",
  "confidence": "inferred",
  "userConfirmed": false
}
~~~

source 建议取 user_asset、reference_frame、user_confirmation 或 inferred。
提交工作流前，inferred 且会影响身份、产品、场景或风格的事实必须转成
用户确认，或在计划里明确保留为未知。

角色标签不要映射成固定数据库枚举。若用户已有“产品正面”“手部素材”或
其他自定义文件夹，直接使用其 collection ID；建议角色只作为镜头依赖和
审计记录。

promptFacts 中的 identityAnchors、referenceAssetIds、妆态、光线、产品角度/
开合、主动作和表情因果链都必须能回指已批准资产或参考帧；未知项显式写
unknown 并在提交前确认。
