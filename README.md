# DocumentEveryday

A personal, agentic short-form clip pipeline. I upload an evening of footage from my iPhone; my MacBook
transcribes it, picks moments using **my own written rule**, cuts captioned 9:16 clips, writes copy **in my
voice**, and runs a QA agent over every clip. My phone buzzes, and I swipe through the results.

**How it differs from OpusClip:** clips are picked by an editable rule (`rules/good_clip_rule.md`) rather
than a virality score. Copy is written from a style profile learned from my own transcripts. Every AI
decision (tag, score, reason, QA verdict, tokens, cost) is logged and shown on the clip's card. It runs on
hardware I already own: **$0 infrastructure, about $0.02 of Claude Haiku per evening.**

## How a batch flows

```
iPhone upload ──► transcribe (faster-whisper, local, free) ──► segment at pauses
   ──► tag segments (SegmentClassifier seam → Claude)  ──► score moments against MY rule (Claude)
   ──► select 15-60s word-boundary clips ──► [post-selection seam] ──► refresh voice/my_voice.md
   ──► per clip: copy in my voice → captions (+ English for Arabic) → render 9:16 → QA
   ──► ntfy push ──► swipe: → save (share sheet + caption copied) · ← reject · ↑ review + voice note
```

**QA agent:** plain-code checks run first (mid-word cut, unfinished sentence, dead air, 15-60s, caption
overflow, untranslated Arabic, frame size, black frames). If everything passes, no Claude call is made. If
something fails, Claude runs a tool loop (`retrim_clip`, `rewrite_caption`, `flag_for_review`). The clip
is re-rendered and re-checked after each fix. After at most 2 fixes it either passes or is flagged with
the reason.

**Budget:** each Claude call is checked against the batch's $0.50 limit *before* it is sent, using a
deliberately pessimistic estimate. Failure behaviour depends on where the limit is hit:
- During analysis (tagging or scoring): the batch fails cleanly and nothing is spent.
- Mid-clip: that clip ships with plain fallback copy and is flagged.

## Mac setup (once)

1. **Tools:** `brew install python@3.12 ffmpeg`
2. **App:**
   ```bash
   git clone https://github.com/timZelik/DocumentEveryDay && cd DocumentEveryDay
   python3.12 -m venv .venv && .venv/bin/pip install -e ".[development]"
   cp .env.example .env   # fill in all four values; .env explains how to generate each
   ```
3. **HTTPS to your iPhone (free): Tailscale.**
   - Install Tailscale on the Mac and the iPhone, signed in to the same account.
   - In the Tailscale admin console, turn on **MagicDNS** and **HTTPS certificates**.
   - On the Mac, run `tailscale serve --bg 8000`. It prints `https://<mac>.<tailnet>.ts.net`.
   - Put that URL in `DOCUMENTEVERYDAY_PUBLIC_BASE_URL`.

   The app only listens on `127.0.0.1`, so only your own Tailscale devices can reach it, and the token is
   still required. Unlike a Cloudflare quick tunnel, Tailscale has no 100 MB upload cap, which matters for
   GB-sized footage.
4. **Push notifications:** install the **ntfy** iPhone app and subscribe to your `DOCUMENTEVERYDAY_NTFY_TOPIC`.
5. **Run:** `./scripts/run_on_mac.sh`. It keeps the Mac awake while serving; leave the lid open during a
   batch.
6. On the iPhone, open the Tailscale URL, paste the token once, and add the page to the Home Screen.

## Verify each stage on real footage

Replace `IMG_0042.MOV` with one of your own videos.

```bash
source .venv/bin/activate && set -a && source .env && set +a

# Tests (no network, no AI spend)
pytest -q && ruff check .

# 1. Cutter: a hand-picked window as a 9:16 clip with a hook
python -m documenteveryday cut IMG_0042.MOV --start 30 --end 55 --hook "Day 1" --output clip.mp4

# 3a. Transcription (free; downloads the Whisper model on first run). Check the Arabic word count it prints.
python -m documenteveryday transcribe IMG_0042.MOV --output transcript.json

# 1 + 3a. Snap that window to word boundaries and burn captions
python -m documenteveryday cut IMG_0042.MOV --start 30 --end 55 --transcript transcript.json --output snapped.mp4

# 2. Review page with plain cuts (no AI), then open $DOCUMENTEVERYDAY_PUBLIC_BASE_URL/review on the phone
python -m documenteveryday seed-review IMG_0042.MOV --clips 5
./scripts/run_on_mac.sh

# 3-4. The whole pipeline on local files (prints batch status and AI cost; your originals are never deleted)
python -m documenteveryday process IMG_0042.MOV IMG_0043.MOV

# 5. The real flow: open /upload on the iPhone, pick tonight's videos, wait for the push, swipe
```

`voice/my_voice.md` is regenerated each batch and git-ignored because it is built from your transcripts.
Raw uploads are deleted after 5 days (`python -m documenteveryday cleanup` runs that by hand). Clips, the
AI log and voice notes are kept.

## Layout

| Path | One job |
|---|---|
| `documenteveryday/domain.py` | The data every stage passes along |
| `transcription/`, `segmentation/` | Speech to timed words; words to segments |
| `classification/segment_classifier.py` | Tagging behind the `SegmentClassifier` seam (benchmark Jev here later) |
| `selection/` | Rule-based scoring, 15-60s word-boundary windows, selection, post-selection seam |
| `voice/`, `copywriting/` | Voice profile; hook, title, caption, hashtags |
| `captions/` | Caption cues, Arabic translation, ASS subtitle file |
| `media/`, `production/` | ffmpeg wrappers; render one clip |
| `qa/` | Deterministic checks, the agent's tools (workbench), the agent loop |
| `llm/` | Pricing, budget ledger, the single Claude gateway that logs every decision |
| `voiceover/` | Audio-source seam (mode A natural narration today; B and C later) |
| `pipeline/` | Batch orchestration, per-clip workflow, background runner |
| `storage/`, `web/`, `notifications/`, `maintenance/` | SQLite, pages and API, ntfy, raw-footage retention |

## Known limits (honest list)

- Clip selection uses the transcript only. Nothing looks at the video frames, so "action on screen" and
  personal info on screen are judged from what I *say*. Mentions of personal info flag the clip for review.
- Whisper's Egyptian Arabic is imperfect. The translator is told the Arabic may be misheard, but check those
  captions.
- iOS may compress videos picked from the Photos library. If clips look soft, pick the files through
  **Files** instead and compare sizes on the upload page.
- The Mac must be awake with the lid open while a batch runs.
