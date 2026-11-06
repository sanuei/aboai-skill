# aboai-skill

Claude Code skill for the [AboAI](https://aboai.ai) gateway: image generation/editing (gpt-image 2.5 series, auto-latest), multi-model chat, TTS, embeddings, and Seedance 2.0 video generation.

## Install

```bash
git clone https://github.com/<you>/aboai-skill.git
cp -R aboai-skill/aboai ~/.claude/skills/aboai
```

## API key

Never committed to this repo. Provide it via one of (in order):

1. `$ABOAI_API_KEY`
2. `~/.aboai/key` (`chmod 600`)
3. `.env` inside the skill directory

## Usage

See [aboai/SKILL.md](aboai/SKILL.md).
