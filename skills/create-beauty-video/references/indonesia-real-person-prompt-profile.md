# 印尼 TikTok 美妆真人 Prompt Profile

profile id：id_tiktok_beauty_ugc_real_person_v1

这是一套提示词编译方法，不是人物国籍模板，也不是固定资产分类。人物外貌、
肤色、头部包裹、服装和妆容只从用户批准的参考图或参考视频可见事实读取；
不能因为“印尼”或“东南亚”标签自动改写五官。

## 编译顺序

画面事实 -> t=0 -> 唯一主动作 -> 眼神/微表情因果 -> 手机镜头/光线/环境 -> 声音 -> 少量护栏

## promptFacts 最小字段

- startState：动作前当前妆态和人物状态。
- durationSeconds：必须等于镜头 durationSec，来自真实 PTS 或用户确认的自然表演时长。
- identityAnchors、referenceAssetIds：只列实际可见、已批准的身份锚点和最少必要参考图顺序。
- makeupState：底妆、眉、眼、腮红、唇色、肤质等当前状态，不能同时写素颜和最终定妆。
- camera：景别、t=0 视线、头部角度/机位和相机行为。默认脸部特写/头肩近景，不默认全身参考。
- lighting：主光方向、软硬度、白平衡、脸部受光和背景亮度/景深。
- productState：visible 必须明确；可见时提供同角度产品资产、开合、主手和握持点。
- primaryAction：一个主动作的 start -> path -> contact/completion -> end 和 [startSec,endSec]。
- expressionArc：baseline -> trigger -> reaction -> recovery。
- audioMode：post_tts_visual 或 visible_speech；后者必须提供准确 dialogue。

## 首帧 Prompt

首帧是精确 t=0，不是海报或动作中间帧。提示词顺序：当前人物与妆态、真实
环境/景别/机位、主光与曝光、动作前主手/产品状态、视线/自然基线/呼吸、少量
护栏。保留毛孔、自然肤色过渡和轻微不对称；不自动注入棚拍、玻璃肌、尖下巴、
大眼、最终妆效、字幕或包装小字。

## 视频 Prompt

第一张输入固定为已批准首帧。提示词只描述该首帧如何动起来：

1. 承接 t=0。
2. 写计划时长、相机行为和唯一主动作的时间窗。
3. 写产品路径、接触/完成点和结束位置。
4. 写视线、眼睑/眉毛、眨眼、嘴角和呼吸的因果变化。
5. 写 audioMode 与台词（如有）。
6. 只保留少量高风险护栏。

避免“慢慢地、全程稳定、一直微笑、持续直视镜头”等模糊默认值。

## 质量门

按原速 1.0x 检查：人物身份、肤质和妆态、眼神因果、手部/产品一致性、跳光、
口型冲突、表情冻结和真实手机质感。失败时回到首帧或产品角度资产，不用后期
加速或更多负面词掩盖。
