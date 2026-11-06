---
name: aboai
description: 通过 AboAI 聚合网关调用 gpt-image 2.5 系列（自动选最新）生图/改图、nano banana (gemini image) 生图、DeepSeek / GPT / Claude / Gemini / GLM / Kimi 文本与视觉对话、TTS 语音合成、文本向量，以及 Seedance 2.0 视频生成（文生视频/图生视频，走独立域名 vipapi.aboai.ai）。用户说「生成一张图」「用 gpt image 画」「用 nanobanana 生图」「改这张图」「用 deepseek 跑一下」「换个模型问」「文字转语音」「seedance 生成视频」「abo」时使用。Call AboAI gateway for image generation/editing (gpt-image-2.5 series, always the newest; nano banana), multi-model chat (DeepSeek, GPT, Claude, Gemini, GLM, Kimi), TTS, embeddings, and Seedance 2.0 video generation.
---

# AboAI 多模型网关

一个 OpenAI 兼容网关，一个 key 调所有模型。所有能力通过 `scripts/abo.py` 调用。

```bash
python3 scripts/abo.py <command> [...]
```

Key 读取顺序：`$ABOAI_API_KEY` → `~/.aboai/key` → 本 skill 目录下的 `.env`。已写入 `~/.aboai/key`（权限 600），无需再配置。

从其他目录调用时用绝对路径：`python3 ~/.claude/skills/aboai/scripts/abo.py ...`

## 生图 image

**模型策略：永远用网关上最新的 gpt-image 系列。** 目前是 2.5 系列（`gpt-image-2.5-flare`、`gpt-image-2.5-sunburst`，实测两者参数和画幅规则一致）。不传 `-m` 时 `abo.py` 会实时查 `/models`，自动选版本号最高的 `gpt-image-*`（同版本取名字排序第一个），有新模型上线后无需改任何代码。想固定模型：`-m xxx` 或环境变量 `ABOAI_IMAGE_MODEL`。

```bash
python3 scripts/abo.py image "描述" -o out.png                          # 默认：最新 gpt-image（当前 2.5 系列）
python3 scripts/abo.py image "描述" -m gpt-image-2.5-sunburst -o o.png   # 指定 2.5 系列另一个
python3 scripts/abo.py image "描述" --size 3840x2160 -o 4k.png           # 2.5 支持到 4K
python3 scripts/abo.py image "描述" -m gemini-3.1-flash-image -o o.png   # nano banana（固定 1408×768）
python3 scripts/abo.py image "描述" -m gemini-3-pro-image --size 2K -o o.png  # nano banana pro
```

- `--size`：gpt-image 2.5 任意 `宽x高`，实测通过 `1024x1024`(默认) / `1024x1536` 竖 / `1536x1024` 横 / `2048x2048` / `3840x2160`，`auto`（出 1254×1254）；gemini-3-pro-image 用 `1K` / `2K` / `4K`。
- `--quality low|medium|high`（默认 high，仅 gpt-image）。low 出图快、便宜，适合先看构图。
- `-n 2` 出多张，文件名自动加 `_2`。
- 不指定 `-o` 时输出到当前目录 `image-<时间戳>.png`，脚本把最终路径打到 stdout。

**画幅注意**：gemini 系列忽略 `--size` 像素值和宽高比参数，要竖图横图请写进 prompt（"vertical 9:16 poster composition"），或改用 gpt-image。`gemini-2.5-flash-image` 已从网关下架。

## 改图 edit（仅 gpt-image 系列）

```bash
python3 scripts/abo.py edit "把苹果换成青梨，保持背景" -i in.png -o out.png        # 默认最新 gpt-image
python3 scripts/abo.py edit "把这两个产品放在同一张桌上" -i a.jpg -i b.jpg -o out.png   # 多图合成
python3 scripts/abo.py edit "只替换蒙版区域为蓝天" -i in.png --mask mask.png -o out.png
```

2.5 系列的 flare / sunburst 改图均实测可用。nano banana 系列在这个网关上**只能文生图**，`/images/edits` 走它会 500；需要参考图 / 改图一律用 gpt-image。

## 对话 chat

```bash
python3 scripts/abo.py chat "问题" -m deepseek-v4-pro
python3 scripts/abo.py chat "总结这个文件" -m Claude-Sonnet-5 -f notes.md
python3 scripts/abo.py chat "这张图里有什么" -m GPT-5.2 -i photo.png      # 视觉
python3 scripts/abo.py chat "写一段长文" -m glm-5.2 --stream            # 流式输出
python3 scripts/abo.py chat "抽取字段" -m GPT-5.5 --json                # 强制 JSON
```

`-s/--system` 系统提示，`--max-tokens`，`--temperature`，`-o` 存文件，也支持管道输入（`cat x.md | ... chat "总结"`）。

**推理模型注意**：DeepSeek 会先输出思维链，`--max-tokens` 给太小（<200）会导致 content 为空、finish_reason=length。留够预算。

## 语音 tts

```bash
python3 scripts/abo.py tts "你好，世界" -o hello.wav
python3 scripts/abo.py tts "文本" -m gemini-2.5-pro-tts -v Kore -o out.wav
```

输出 WAV（24kHz 单声道）。可用模型：`gemini-2.5-flash-tts`、`gemini-2.5-pro-tts`、`gemini-2.5-flash-lite-preview-tts`、`Chirp3-HD`。

## 向量 embed

```bash
python3 scripts/abo.py embed "文本1" "文本2" -o vecs.json      # text-embedding-3-large
```

## 视频 video（Seedance 2.0，实验性，无 CLI 封装）

`abo.py` 目前没有视频子命令，且视频接口的域名跟其他接口**不一样**，要自己 curl：

```bash
# 文生视频
curl -s -X POST https://vipapi.aboai.ai/v1/video/generations \
  -H "Authorization: Bearer $(cat ~/.aboai/key)" -H "Content-Type: application/json" \
  -d '{"model":"seedance-2-0-fast","prompt":"a cat walking on grass, cinematic","duration":5,"resolution":"480p","ratio":"16:9","generate_audio":false}'
# 返回 {task_id,...}，轮询：
curl -s https://vipapi.aboai.ai/v1/video/generations/<task_id> -H "Authorization: Bearer $(cat ~/.aboai/key)"
```

- `model`：`seedance-2-0` / `seedance-2-0-fast`（fast 不支持 1080p）。`generate_audio` 不传等于 `true`，容易被判"疑似版权音频"而失败，没需求就传 `false`。
- **图生视频**：把 `prompt` 换成 `content:[{"type":"text","text":"..."},{"type":"image_url","image_url":{"url":"data:image/jpeg;base64,..."}}]`，只放一张图，实测跑通。
- **首尾帧 / 全能参考（多张参考图）：实测不支持**，`content` 里放第二张图稳定 400。
- 连续提交容易触发上游 429，两次请求间隔建议 ≥20 秒。

详见 [references/models.md](references/models.md) 的「视频 Video」节。

## 其他

**网关有新模型时（尤其是图像模型），先跑 `models` 看一眼，优先用最新的。**

```bash
python3 scripts/abo.py models                                  # 查当前可用模型（会变，以此为准）
python3 scripts/abo.py raw /chat/completions body.json         # 直接打任意端点
```

## 选型速查

| 需求 | 用 |
|---|---|
| 高质量生图、要控画幅 | 最新 `gpt-image-*`（当前 `gpt-image-2.5-flare` / `-sunburst`）|
| 改图 / 多图合成 / 蒙版 | 最新 `gpt-image-*` 的 `edit` |
| 快速便宜生图 | `gemini-3.1-flash-image` (nano banana) |
| 高分辨率生图 (2K/4K) | 最新 `gpt-image-*`（`--size 3840x2160`）或 `gemini-3-pro-image` |
| 中文推理、性价比 | `deepseek-v4-pro` / `deepseek-v4-flash-0731` |
| 长文写作 / 代码 | `Claude-Opus-5` / `Claude-Sonnet-5` |
| 通用 + 视觉 | `GPT-5.5` / `GPT-5.2` / `gemini-3.1-pro-preview` |

完整模型清单与实测到的接口怪癖见 [references/models.md](references/models.md)。

## 故障处理

- `Internal server error` (HTTP 500)：网关偶发抖动，脚本已自动重试 4 次（退避 2/4/6 秒）。仍失败多为参数不被上游接受——换模型或去掉可选参数再试。
- gpt-image-*（含 2.5 系列）必须同时带 `size` + `quality` + `n`，缺一个就 500；脚本已自动补齐，手写 curl 时要注意。
- `Model not found: xxx`：模型 ID 大小写敏感（`Claude-Opus-5` 大写、`deepseek-v4-pro` 小写），先跑 `models` 确认。
