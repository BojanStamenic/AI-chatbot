# BojanBot

Personal AI chatbot with web search, image generation, voice transcription, lyrics fetching, and live control of an AngryLynx landing page. Powered by Groq-hosted Llama models with an OpenAI-compatible API and served from a small Python `http.server`.

## Features

- **Agentic chat loop** — the bot autonomously calls tools (multi-step), processes results, and continues until it has a final answer (capped at 4 iterations to prevent runaway token use).
- **Web search** ([search/web_search.py](search/web_search.py)) via DuckDuckGo. Results are treated as authoritative and override the model's stale training data. Includes a query-augmenter for "latest" sport-event queries that injects the correct year based on whether this year's edition has already happened.
- **Lyrics fetching** ([search/lyrics.py](search/lyrics.py)) — pulls verbatim lyrics from lyrics.ovh (English) and Tekstovi.net (ex-YU). Lyrics are returned directly to the user without going back through the LLM, to prevent paraphrasing or refusals.
- **Image generation** ([image/image_gen.py](image/image_gen.py)) via Pollinations (`image.pollinations.ai`). Triggered by either an explicit tool call or natural-language detection (`needs_image`).
- **Voice transcription** ([voice/transcribe.py](voice/transcribe.py)) — the UI uploads audio to `/transcribe`, which forwards it to Groq's Whisper endpoint via the OpenAI client.
- **File loading** — `load_file` tool reads files from disk so the user can ask questions about their content.
- **Self-learning** ([core/knowledge.py](core/knowledge.py)) — when the user corrects a fact, the bot extracts the correction, verifies it via web search, and persists it to [knowledge.json](knowledge.json). On every turn, relevant learned facts are injected into the system prompt.
- **Multi-chat manager** ([core/chat_manager.py](core/chat_manager.py)) — stores conversations in [chats.json](chats.json), auto-titles new chats, supports rename/delete/switch.
- **Live website control** — the model can emit `<site-action>` tags in its replies; the frontend strips them and applies them live (theme, hero text, features, sections, etc.). See `SYSTEM_PROMPT` in [core/config.py](core/config.py) for the full action list.
- **Token tracking + automatic fallback** — usage per turn and per day is tracked. On Groq 429 TPD (tokens-per-day) errors, the bot automatically falls back from `llama-3.3-70b-versatile` to `llama-3.1-8b-instant`.
- **Clarification short-circuit** — if the model calls `ask_clarification`, the question is surfaced directly to the user instead of running another tool round.
- **Failure escalation** — repeated failures of the same tool trigger system nudges telling the model to try a different approach or stop.

## Architecture

```
chatbot_ui.py          # Entry point — boots HTTP server on 127.0.0.1:8080
core/
  bot.py               # BojanBot — the agentic LLM loop, tool dispatch, learning
  chat_manager.py      # Multi-chat storage and titling
  config.py            # MODEL, HOST/PORT, full SYSTEM_PROMPT, env loading
  knowledge.py         # Persistent learned-facts store
search/
  web_search.py        # DuckDuckGo search wrapper
  lyrics.py            # lyrics.ovh + Tekstovi.net fetchers
image/image_gen.py     # Pollinations image URL generator + prompt detection
voice/transcribe.py    # multipart parsing + Groq Whisper transcription
server/handler.py      # HTTP routes (REST API + static files)
static/                # Frontend (index.html + CSS/JS for chat UI and AngryLynx site)
chats.json             # Persisted chat history
knowledge.json         # Persisted learned facts
```

## Tools available to the model

| Tool | Purpose |
| --- | --- |
| `web_search` | Live web lookup; required for any time-sensitive or verbatim-fact question |
| `get_lyrics` | Authoritative lyrics fetch (always tried before web search for lyrics) |
| `load_file` | Read a local file the user wants to discuss |
| `generate_image` | Create an image from a prompt |
| `ask_clarification` | Ask the user a question instead of guessing |

## HTTP API

| Method | Path | Purpose |
| --- | --- | --- |
| GET  | `/` | Serves the chat UI |
| GET  | `/api/chats` | List chats |
| GET  | `/api/chats/history?id=…` | Filtered message history for a chat |
| GET  | `/api/image?prompt=…` | Proxy to Pollinations image generation |
| POST | `/chat` | Send a user message, get a reply |
| POST | `/transcribe` | Audio → text (multipart upload) |
| POST | `/reset` | Clear current chat history |
| POST | `/load` | Pre-load a file into the conversation |
| POST | `/api/chats/new` \| `/switch` \| `/delete` \| `/rename` | Chat management |

## Setup

Requires Python 3.9+ and a Groq API key.

```bash
pip install -r requirements.txt
echo "GROQ_API_KEY=your_key_here" > .env
python chatbot_ui.py
```

Then open <http://127.0.0.1:8080>.

## Configuration

All in [core/config.py](core/config.py):
- `MODEL` — primary Groq model (default `llama-3.3-70b-versatile`)
- `HOST` / `PORT` — bind address (default `127.0.0.1:8080`)
- `SYSTEM_PROMPT` — bot persona, tool-usage rules, temporal-reasoning guide, anti-hallucination rules, lyrics rules, and the full `<site-action>` action vocabulary

The fallback model and the small "learning/extraction" model are set on `BojanBot` in [core/bot.py](core/bot.py) (currently both `llama-3.1-8b-instant`).

## Notable design choices

- **Lyrics bypass the LLM** — once `get_lyrics` returns text, it's sent straight to the user. The model is unreliable about reproducing copyrighted lyrics verbatim, so we don't ask it to.
- **Search-then-extract** — after each `web_search`, a cheap small-model pass extracts a single literal answer from the snippets, which is then prepended to the results so the main model can quote it directly. Reduces fabrication.
- **History trimming** — keeps system prompt + last 12 messages, with care to not orphan a `tool` message from its `assistant` `tool_calls` parent.
- **Tool-call parsing** — supports both native OpenAI `tool_calls` and Groq's occasional XML-style `<function=name>{...}</function>` or bare `name{json}` text emissions.
