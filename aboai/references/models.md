# AboAI 模型与接口实测记录

Base URL：`https://api.aboai.ai/v1`（`api.aboai.com` 不可达，文档里那个地址是旧的）
鉴权：`Authorization: Bearer <key>`

实测时间：2026-08-20；图像模型 2026-11-06 更新（2.5 系列）。模型清单会变，以 `abo.py models` 的实时输出为准。

## 可用端点

| 端点 | 状态 | 说明 |
|---|---|---|
| `POST /v1/chat/completions` | ✅ | OpenAI 格式，支持 `stream`、视觉 `image_url`、`response_format` |
| `POST /v1/images/generations` | ✅ | 返回 `data[].b64_json`（无 url 模式） |
| `POST /v1/images/edits` | ✅ 仅 gpt-image 系列 | multipart，多图用 `image[]` |
| `POST /v1/audio/speech` | ✅ | 直接返回 `audio/wav` 二进制 |
| `POST /v1/embeddings` | ✅ | 默认 base64，传 `encoding_format:"float"` 得数组 |
| `POST /v1/messages` | ✅ | Anthropic 原生格式（Claude 模型） |
| `POST /v1/responses` | ✅ | OpenAI Responses 格式（GPT 模型） |
| `GET /v1/models` | ✅ | |
| Gemini 原生 `:generateContent` | ❌ | 不支持 |
| `/v1/videos`、`/v1/videos/generations`（复数 videos）、billing 端点 | ❌ | 404，路由不存在 |
| `POST https://vipapi.aboai.ai/v1/video/generations`（注意换了域名，且是单数 video） | ✅ 视频生成见下方专节 | 在主域名 `api.aboai.ai` 上这条路由也存在但永远 404/model not found —— **视频走的是完全独立的域名 `vipapi.aboai.ai`**，跟 `/v1/models` 里能查到的 41 个 chat/image 模型是两套不同的目录，不在里面查不到很正常。 |

## 视频 Video（Seedance 2.0）—— 实测 2026-09-17

文档：https://docs.aboai.ai/api-458350675（创建）、https://docs.aboai.ai/api-458420832（查询）。**注意这两条文档给的示例 base URL 就是 `vipapi.aboai.ai`，跟其他所有接口用的 `api.aboai.ai` 不是同一个域名**，`abo.py` 目前没有 video 子命令，要调只能自己拼 `https://vipapi.aboai.ai/v1/video/generations`，鉴权头一样 `Authorization: Bearer <key>`。

- **创建**：`POST https://vipapi.aboai.ai/v1/video/generations`，`model` 必须是 `seedance-2-0` 或 `seedance-2-0-fast`（fast 不支持 1080p）。成功返回 `{id, task_id, status:"queued", pre_deduct_mount, ...}`，是异步任务，先扣一部分预估费用，完成后多退少补。
- **查询**：`GET https://vipapi.aboai.ai/v1/video/generations/{task_id}`，轮询 `status`：`queued` → `in_progress`(`progress` 卡在 50 很正常) → `completed`/`failed`。成功后 `video_url`/`url`/`metadata.video_url` 是一个带签名、24小时过期的火山引擎 TOS 直链 mp4，要下载/转存的话尽快处理。
- **文生视频**：`{"model":"seedance-2-0-fast","prompt":"...","duration":5,"resolution":"480p","ratio":"16:9","generate_audio":false}` —— 实测跑通，完整生成过一条 5 秒 480p mp4。
- **图生视频**：不要用顶层 `prompt`，改用 OpenAI 视觉格式的 `content` 数组，**只放一张图**：
  ```json
  {"model":"seedance-2-0-fast","content":[{"type":"text","text":"..."},{"type":"image_url","image_url":{"url":"data:image/jpeg;base64,..."}}],"duration":5,"resolution":"720p","ratio":"16:9","generate_audio":false}
  ```
  实测跑通两次，输出视频首帧 = 传入的图片，确认生效。
  **2026-10-19 更新**：base64 data URI 的图片稳定返回网关 `500 Internal server error`（不论图片大小、带不带 role），文生视频同时正常；把图片放到公网 https URL 后同样的 body 立即成功。图生视频优先用 https 图片 URL。`ratio` 文档建议图生视频用 `adaptive`，但 `16:9` 也测试成功过。
- **首尾帧 / 全能参考（多图）**：**实测不支持，别在这上面浪费时间**。往 `content` 数组里塞第二张 `image_url`（不管加不加 `role:"first_frame"/"last_frame"` 猜测字段）稳定触发 `Upstream error: 400`（真实校验拒绝，不是限流的 429，8 次重试全部同样报错）。文档本身也完全没提首尾帧或多参考图的字段名，大概率这个网关的转发层目前只透传单图给上游火山引擎的 Seedance 2.0，没有把 Doubao 原生支持的首尾帧/参考图参数开放出来。如果客户明确需要这两个功能，建议直接找 AboAI 官方确认或考虑用火山引擎 Ark 原生 API。
- **`generate_audio` 是个坑**：默认行为等同 `true`（哪怕不传），会自动配自动生成的音频，实测第一次就因为 `OutputAudioSensitiveContentDetected.PolicyViolation`（输出音频疑似版权问题，误判概率不低）导致 `status:"failed"`。**没有明确需要配音就传 `"generate_audio": false`**，能稳定跑通。
- **限流很敏感**：短时间内连续提交多个视频任务会持续吃上游 `429`（网关包装成 `HTTP 400 {"error":{"message":"Upstream error: 429",...}}`，不是网关自己限流，是透传的上游状态码，所以字段里 `code` 永远是 400，得看 `message` 里的数字）。两次成功请求之间建议至少间隔 20-30 秒。
- **计费**：响应里 `pre_deduct_mount` 是创建时预扣的费用（美元），实测 480p/5s ≈ 0.29，720p/5s（图生视频）≈ 0.62，完成后按实际用量多退少补，`usage.total_tokens` 是内部计费单位不是钱。

## 模型清单（2026-08-20 快照，已过时部分见 `models` 实时输出）

**Claude**：Claude-Opus-5, Claude-Sonnet-5, Claude-Fable-5, Claude-Opus-4.8, Claude-Opus-4.7, Claude-Opus-4.6, Claude-Opus-4.5, Claude-Sonnet-4.6, Claude-Sonnet-4.5, Claude-Haiku-4.5

**GPT**：GPT-5.4, GPT-5.5, GPT-5.6-Luna/Sol/Terra, GPT-6-Astra, Gpt-6-Luna/Sol, Gpt-6.1-Sol/Terra, **gpt-image-2.5-flare, gpt-image-2.5-sunburst**, gpt-image-2, text-embedding-3-large

**Gemini**：gemini-3.5-flash, gemini-3.7-flash, gemini-3.1-pro-preview, gemini-3.1-flash-lite, gemini-3-flash-preview, gemini-2.5-pro, gemini-2.5-flash, gemini-2.5-flash-lite, gemini-3-pro-image, gemini-3.1-flash-image, gemini-2.5-pro-tts, gemini-2.5-flash-tts, gemini-2.5-flash-lite-preview-tts, gemini-live-2.5-flash-native-audio, Chirp3-HD, cloud-translate-text

**DeepSeek**：deepseek-v4-pro, deepseek-v4-pro-0813, deepseek-v4-flash-0731

**GLM**：glm-5.2, glm-5.1, GLM-5V-Turbo

**Kimi**：kimi-k3, kimi-k2.7-code, kimi-k2.6

模型 ID 大小写敏感：Claude 系列首字母大写，其余小写。

## 实测怪癖

### gpt-image-2.5 系列（gpt-image-2.5-flare / gpt-image-2.5-sunburst，2026-11-06 实测）
- 默认图像模型，`abo.py` 自动选最新 gpt-image。flare 与 sunburst 实测参数规则、token 用量、画幅完全一致，仅画面随机性不同。
- 同样**必须同时传 `size` + `quality` + `n`**，只传 `{model,prompt}` → 500。
- size 支持任意 `宽x高`：实测 `1536x1024`、`1024x1536`、`2048x2048`、`3840x2160` 输出尺寸与请求一致；`auto` → 1254×1254。
- `/images/edits` 可用（单图/多图/mask 规则同 gpt-image-2）。
- `gemini-2.5-flash-image` 已下架（404 Model not found）；`gemini-3.1-flash-image` 固定出 1408×768。

### gpt-image-2（旧）
- **必须同时传 `size` + `quality` + `n`**，少任何一个 → `HTTP 500 Internal server error`（不是参数校验错，看不出原因）。
- `response_format` 参数不被支持，传了就 500。永远返回 b64。
- 支持 size：`1024x1024`、`1024x1536`、`1536x1024`、`auto`（auto 实测出 1254×1254）。
- `quality`：`low` / `medium` / `high`。
- `/images/edits` 可用：单图 `image`，多图 `image[]`，支持 `mask`。实测多图合成与"改颜色保背景"都正常。
- 输出 PNG 带 C2PA 元数据。

### nano banana（gemini-3-pro-image / gemini-3.1-flash-image；2.5-flash-image 已下架）
- 只走 `/images/generations`，最简 body `{model, prompt}` 即可。
- **`/images/edits` 一律 500**，chat/completions 传图也 500 → 这个网关上不能改图、不能吃参考图。
- 在 generations 里传 `image: [...]` 参数**会被静默忽略**（实测：给参考图要求灰度复刻，输出的是完全无关的图）。别以为它生效了。
- `gemini-2.5-flash-image`：固定输出 1024×1024，`aspect_ratio`、`size:"2K"` 都被忽略；传像素尺寸如 `1024x1536` 会报 `400 invalid argument`。
- `gemini-3-pro-image`：`size:"2K"` → 2816×1536；不传或 `1K` → 1408×768。`aspect_ratio` 无效（传 9:16 仍出横图）。要竖图请写进 prompt。

### DeepSeek
- 推理型输出：`max_tokens` 太小时全部预算被思维链吃掉，返回的 message 里没有 `content`、`finish_reason: "length"`。给到 ≥500 才稳。
- `usage.completion_tokens` 包含推理 token。

### 通用
- 网关有**偶发 500**（同一个 body 前一秒失败、后一秒成功）。`abo.py` 内置 4 次重试 + 递增退避。
- 错误体两种格式：OpenAI 风格 `{"error":{"message":...}}`，和网关自身的 `{"code":404,"msg":"请求的资源不存在"}`。
- 流式返回是 `data:{...}`（冒号后无空格），解析时别按 `data: ` 切。
- TTS 输出为 24kHz 单声道 16bit WAV，`voice` 用 Gemini 音色名（如 `Kore`）。
