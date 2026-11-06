#!/usr/bin/env python3
"""AboAI CLI — one entry point for chat / image / edit / tts / embed.

Pure stdlib. Base URL: https://api.aboai.ai/v1 (OpenAI-compatible).
Key lookup order: $ABOAI_API_KEY -> ~/.aboai/key -> <skill dir>/.env
"""
import argparse, base64, json, mimetypes, os, re, sys, time, urllib.error, urllib.request, uuid
from datetime import datetime
from pathlib import Path

BASE = os.environ.get("ABOAI_BASE_URL", "https://api.aboai.ai/v1")
RETRIES = 4          # the gateway throws sporadic 500 "Internal server error"
BACKOFF = 2.0


def api_key() -> str:
    k = os.environ.get("ABOAI_API_KEY")
    if k:
        return k.strip()
    for p in (Path.home() / ".aboai" / "key", Path(__file__).resolve().parent.parent / ".env"):
        if p.exists():
            txt = p.read_text().strip()
            if "=" in txt and txt.split("=", 1)[0].isupper():
                txt = txt.split("=", 1)[1].strip().strip('"').strip("'")
            if txt:
                return txt
    sys.exit("No API key. Set ABOAI_API_KEY or write it to ~/.aboai/key")


def request(path, body=None, headers=None, method="POST", raw=False, stream=False, timeout=600):
    url = f"{BASE}{path}"
    hdrs = {"Authorization": f"Bearer {api_key()}"}
    hdrs.update(headers or {})
    data = None
    if body is not None:
        if isinstance(body, (bytes, bytearray)):
            data = bytes(body)
        else:
            data = json.dumps(body).encode()
            hdrs.setdefault("Content-Type", "application/json")
    last = None
    for attempt in range(RETRIES):
        req = urllib.request.Request(url, data=data, headers=hdrs, method=method)
        try:
            resp = urllib.request.urlopen(req, timeout=timeout)
            if stream:
                return resp
            payload = resp.read()
            return payload if raw else json.loads(payload)
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "replace")
            last = f"HTTP {e.code}: {detail[:400]}"
            # 500 from this gateway is usually transient, or a missing required param
            if e.code in (429, 500, 502, 503, 504) and attempt < RETRIES - 1:
                time.sleep(BACKOFF * (attempt + 1))
                continue
            sys.exit(f"[abo] request failed -> {last}")
        except urllib.error.URLError as e:
            last = str(e)
            if attempt < RETRIES - 1:
                time.sleep(BACKOFF * (attempt + 1))
                continue
            sys.exit(f"[abo] network error -> {last}")
    sys.exit(f"[abo] failed -> {last}")


def multipart(fields, files):
    """fields: list[(name, value)]; files: list[(name, path)] -> (body, content_type)"""
    boundary = "----abo" + uuid.uuid4().hex
    buf = bytearray()
    for name, value in fields:
        buf += f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"\r\n\r\n{value}\r\n".encode()
    for name, path in files:
        p = Path(path).expanduser()
        ctype = mimetypes.guess_type(p.name)[0] or "application/octet-stream"
        buf += f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"; filename=\"{p.name}\"\r\nContent-Type: {ctype}\r\n\r\n".encode()
        buf += p.read_bytes() + b"\r\n"
    buf += f"--{boundary}--\r\n".encode()
    return bytes(buf), f"multipart/form-data; boundary={boundary}"


def out_path(explicit, prefix, ext, index=0):
    if explicit:
        p = Path(explicit).expanduser()
        if index:
            p = p.with_name(f"{p.stem}_{index+1}{p.suffix}")
    else:
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        suffix = f"_{index+1}" if index else ""
        p = Path.cwd() / f"{prefix}-{stamp}{suffix}.{ext}"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def save_images(resp, args, prefix):
    items = resp.get("data") or []
    if not items:
        sys.exit(f"[abo] no image in response: {json.dumps(resp)[:300]}")
    paths = []
    for i, item in enumerate(items):
        if item.get("b64_json"):
            blob = base64.b64decode(item["b64_json"])
        elif item.get("url"):
            blob = urllib.request.urlopen(item["url"], timeout=120).read()
        else:
            continue
        p = out_path(args.out, prefix, "png", i)
        p.write_bytes(blob)
        paths.append(p)
    usage = resp.get("usage") or {}
    for p in paths:
        print(p)
    if usage:
        print(f"[tokens] {json.dumps(usage)}", file=sys.stderr)
    return paths


# ---------------------------------------------------------------- commands
def cmd_models(args):
    resp = request("/models", method="GET", body=None)
    groups = {}
    for m in resp.get("data", []):
        groups.setdefault(m.get("owned_by", "?"), []).append(m["id"])
    for owner in sorted(groups):
        print(f"{owner}:")
        for mid in sorted(groups[owner]):
            print(f"  {mid}")


def cmd_chat(args):
    content = args.prompt or ""
    if args.file:
        extra = "\n\n".join(Path(f).expanduser().read_text() for f in args.file)
        content = f"{content}\n\n{extra}".strip()
    if not content and not sys.stdin.isatty():
        content = sys.stdin.read()
    if not content:
        sys.exit("[abo] nothing to send")
    messages = []
    if args.system:
        messages.append({"role": "system", "content": args.system})
    parts = [{"type": "text", "text": content}]
    for img in args.image or []:
        p = Path(img).expanduser()
        mime = mimetypes.guess_type(p.name)[0] or "image/png"
        b64 = base64.b64encode(p.read_bytes()).decode()
        parts.append({"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}})
    messages.append({"role": "user", "content": parts if len(parts) > 1 else content})

    body = {"model": args.model, "messages": messages}
    if args.max_tokens:
        body["max_tokens"] = args.max_tokens
    if args.temperature is not None:
        body["temperature"] = args.temperature
    if args.json_mode:
        body["response_format"] = {"type": "json_object"}

    if args.stream:
        body["stream"] = True
        resp = request("/chat/completions", body, stream=True)
        for line in resp:
            line = line.decode("utf-8", "replace").strip()
            if not line.startswith("data:"):
                continue
            payload = line[5:].strip()
            if payload == "[DONE]":
                break
            try:
                chunk = json.loads(payload)
            except json.JSONDecodeError:
                continue
            delta = (chunk.get("choices") or [{}])[0].get("delta", {})
            piece = delta.get("content") or ""
            if piece:
                sys.stdout.write(piece)
                sys.stdout.flush()
        print()
        return

    resp = request("/chat/completions", body)
    msg = (resp.get("choices") or [{}])[0].get("message", {}) or {}
    text = msg.get("content")
    if not text:
        text = msg.get("reasoning_content") or ""
    if args.out:
        p = Path(args.out).expanduser()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
        print(p)
    else:
        print(text)
    u = resp.get("usage")
    if u:
        print(f"[tokens] {json.dumps(u)}", file=sys.stderr)


FALLBACK_IMAGE_MODEL = "gpt-image-2.5-flare"


def latest_image_model() -> str:
    """Newest gpt-image-* on the gateway, so new releases are picked up automatically.

    Override with $ABOAI_IMAGE_MODEL or -m. Ranking: highest version number
    (2.5 > 2), ties broken by name. Falls back to FALLBACK_IMAGE_MODEL.
    """
    env = os.environ.get("ABOAI_IMAGE_MODEL")
    if env:
        return env
    try:
        ids = [m["id"] for m in request("/models", method="GET").get("data", [])]
    except SystemExit:
        return FALLBACK_IMAGE_MODEL
    cands = []
    for mid in ids:
        mt = re.match(r"gpt-image-(\d+(?:\.\d+)*)", mid, re.I)
        if mt:
            cands.append((tuple(int(x) for x in mt.group(1).split(".")), mid))
    if not cands:
        return FALLBACK_IMAGE_MODEL
    best = max(v for v, _ in cands)
    chosen = sorted(mid for v, mid in cands if v == best)[0]
    print(f"[abo] image model: {chosen}", file=sys.stderr)
    return chosen


def cmd_image(args):
    args.model = args.model or latest_image_model()
    body = {"model": args.model, "prompt": args.prompt}
    if args.model.lower().startswith("gpt-image"):
        # gpt-image-* 500s unless size + quality + n are all present
        body["size"] = args.size or "1024x1024"
        body["quality"] = args.quality or "high"
        body["n"] = args.n
    else:
        if args.size:
            body["size"] = args.size          # gemini-3-pro-image: 1K / 2K / 4K
        if args.n != 1:
            body["n"] = args.n
    resp = request("/images/generations", body)
    save_images(resp, args, "image")


def cmd_edit(args):
    args.model = args.model or latest_image_model()
    fields = [("model", args.model), ("prompt", args.prompt),
              ("size", args.size or "1024x1024"),
              ("quality", args.quality or "high"),
              ("n", str(args.n))]
    name = "image[]" if len(args.image) > 1 else "image"
    files = [(name, p) for p in args.image]
    if args.mask:
        files.append(("mask", args.mask))
    body, ctype = multipart(fields, files)
    resp = request("/images/edits", body, headers={"Content-Type": ctype})
    save_images(resp, args, "edit")


def cmd_tts(args):
    text = args.text
    if not text and not sys.stdin.isatty():
        text = sys.stdin.read()
    if not text:
        sys.exit("[abo] no text")
    body = {"model": args.model, "input": text, "voice": args.voice}
    if args.format:
        body["response_format"] = args.format
    audio = request("/audio/speech", body, raw=True)
    p = out_path(args.out, "speech", args.format or "wav")
    p.write_bytes(audio)
    print(p)


def cmd_embed(args):
    texts = args.text or ([sys.stdin.read()] if not sys.stdin.isatty() else [])
    if not texts:
        sys.exit("[abo] no input")
    resp = request("/embeddings", {"model": args.model, "input": texts, "encoding_format": "float"})
    vectors = [d["embedding"] for d in resp.get("data", [])]
    if args.out:
        p = Path(args.out).expanduser()
        p.write_text(json.dumps(vectors))
        print(p)
    else:
        print(json.dumps(vectors))


def cmd_raw(args):
    body = json.loads(Path(args.body).read_text()) if Path(args.body).exists() else json.loads(args.body)
    print(json.dumps(request(args.path, body), ensure_ascii=False, indent=2)[:20000])


def main():
    ap = argparse.ArgumentParser(prog="abo", description="AboAI multi-model CLI")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("models", help="list available models")
    p.set_defaults(func=cmd_models)

    p = sub.add_parser("chat", help="text / vision chat completion")
    p.add_argument("prompt", nargs="?", default="")
    p.add_argument("-m", "--model", default="deepseek-v4-pro")
    p.add_argument("-s", "--system")
    p.add_argument("-f", "--file", action="append", help="attach a text file to the prompt")
    p.add_argument("-i", "--image", action="append", help="attach an image (vision models)")
    p.add_argument("--max-tokens", type=int)
    p.add_argument("--temperature", type=float)
    p.add_argument("--json", dest="json_mode", action="store_true", help="force JSON object output")
    p.add_argument("--stream", action="store_true")
    p.add_argument("-o", "--out")
    p.set_defaults(func=cmd_chat)

    p = sub.add_parser("image", help="text-to-image")
    p.add_argument("prompt")
    p.add_argument("-m", "--model", default=None, help="default: newest gpt-image-* on the gateway (currently 2.5 series)")
    p.add_argument("--size", help="gpt-image-*: WxH e.g. 1024x1024|1536x1024|2048x2048|3840x2160|auto ; gemini-3-pro-image: 1K|2K|4K")
    p.add_argument("--quality", choices=["low", "medium", "high"], help="gpt-image-* only")
    p.add_argument("-n", type=int, default=1)
    p.add_argument("-o", "--out")
    p.set_defaults(func=cmd_image)

    p = sub.add_parser("edit", help="image editing / composition (gpt-image-*)")
    p.add_argument("prompt")
    p.add_argument("-i", "--image", action="append", required=True, help="input image; repeat for multi-image")
    p.add_argument("--mask")
    p.add_argument("-m", "--model", default=None, help="default: newest gpt-image-* on the gateway")
    p.add_argument("--size")
    p.add_argument("--quality", choices=["low", "medium", "high"])
    p.add_argument("-n", type=int, default=1)
    p.add_argument("-o", "--out")
    p.set_defaults(func=cmd_edit)

    p = sub.add_parser("tts", help="text to speech")
    p.add_argument("text", nargs="?")
    p.add_argument("-m", "--model", default="gemini-2.5-flash-tts")
    p.add_argument("-v", "--voice", default="Kore")
    p.add_argument("--format", help="wav (default) / mp3 if upstream supports it")
    p.add_argument("-o", "--out")
    p.set_defaults(func=cmd_tts)

    p = sub.add_parser("embed", help="text embeddings")
    p.add_argument("text", nargs="*")
    p.add_argument("-m", "--model", default="text-embedding-3-large")
    p.add_argument("-o", "--out")
    p.set_defaults(func=cmd_embed)

    p = sub.add_parser("raw", help="POST an arbitrary path with a JSON body/file")
    p.add_argument("path", help="e.g. /chat/completions")
    p.add_argument("body", help="JSON string or path to a .json file")
    p.set_defaults(func=cmd_raw)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
