import os
import re
import json
from datetime import datetime
from typing import List, Dict, Any

from openai import OpenAI

from core.config import MODEL, SYSTEM_PROMPT
from core import knowledge
from search.web_search import _web_search
from search.lyrics import get_lyrics


def _parse_xml_tool_calls(content: str) -> List[Dict[str, Any]]:
    """Parse XML-style tool calls from Groq models (e.g., <function=tool_name>{"arg": "value"}</function>)"""
    if not content:
        return []
    
    KNOWN_TOOLS = {"web_search", "get_lyrics", "load_file", "generate_image", "ask_clarification"}
    tool_calls = []

    # Pattern 1: <function=tool_name>{json}</function> or <tool_name>{json}</function>
    pattern = r'<(?:function=)?(\w+)>\s*(\{[^}]+\})\s*</(?:function|/\1)>'
    for i, (tool_name, args_json) in enumerate(re.findall(pattern, content, re.DOTALL)):
        try:
            arguments = json.loads(args_json.strip())
            tool_calls.append({
                "id": f"xml_call_{i}",
                "type": "function",
                "function": {"name": tool_name, "arguments": arguments}
            })
        except json.JSONDecodeError:
            continue

    # Pattern 2: bare `tool_name{json}` pseudo-call (llama sometimes emits this
    # instead of using the tool_calls mechanism).
    bare = r'\b(' + "|".join(KNOWN_TOOLS) + r')\s*(\{[^{}]*\})'
    for i, (tool_name, args_json) in enumerate(re.findall(bare, content)):
        try:
            arguments = json.loads(args_json)
            tool_calls.append({
                "id": f"bare_call_{i}",
                "type": "function",
                "function": {"name": tool_name, "arguments": arguments}
            })
        except json.JSONDecodeError:
            continue

    return tool_calls


# Tool definitions for OpenAI function calling
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": """Search the web for current information, news, scores, events, prices, or any real-time data.

ALSO REQUIRED for factual content where fabrication would mislead the user:
- Song lyrics, poems, or any verbatim text by a real author/artist
- Discographies, filmographies, book lists, album tracklists
- Direct quotes attributed to real people
- Biographical facts (birth dates, awards, specific events)
If you do not have the exact text/fact memorized with high confidence, you MUST search instead of generating plausible-sounding content. Never invent lyrics or quotes.

IMPORTANT for "latest" or "most recent" event queries:
1. Check if the event typically happens BEFORE the current date in the year
   - Example: Super Bowl (February) - if current date is April, search for current year's Super Bowl
   - Example: Champions League final (May/June) - if current date is April, search for PREVIOUS year
2. Only search for previous year if the current year's event hasn't happened yet
3. For sports results, ALWAYS include: year + event name + "result" + "score" or "winner"
4. Example queries:
   - Current date April 2026, "latest Super Bowl" → "2026 Super Bowl result score" (February already passed)
   - Current date April 2026, "latest Champions League" → "2025 Champions League final result" (May hasn't happened)""",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The search query. Be specific with years based on event timing, include 'result', 'winner', 'score'. Think: has this year's event already happened?"
                    }
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_lyrics",
            "description": "Fetch authoritative lyrics of a song from lyrics.ovh (English) or Tekstovi.net (ex-YU). ALWAYS try this FIRST for any lyrics request. Returns verbatim lyrics with a source. If it returns empty, you MAY fall back to web_search to locate a page that contains the lyrics, then reproduce them verbatim from that page with its URL. Never fabricate lyrics from memory.",
            "parameters": {
                "type": "object",
                "properties": {
                    "artist": {"type": "string", "description": "Artist name, e.g. 'Ceca', 'Adele'"},
                    "title":  {"type": "string", "description": "Song title, e.g. 'Nagovori', 'Hello'"}
                },
                "required": ["artist", "title"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "load_file",
            "description": "Load and read a file from the filesystem. Use this when the user asks you to read, analyze, or reference a specific file.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "The file path to load (can use ~ for home directory)"
                    }
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "generate_image",
            "description": "Generate an image based on a text description. Use this when the user asks to create, generate, or draw an image.",
            "parameters": {
                "type": "object",
                "properties": {
                    "prompt": {
                        "type": "string",
                        "description": "A detailed description of the image to generate"
                    }
                },
                "required": ["prompt"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "ask_clarification",
            "description": """Ask the user a clarifying question BEFORE taking action when their request is ambiguous, under-specified, or could be interpreted multiple ways. Use this instead of guessing. Examples of when to use:
- User says "read the file" but doesn't specify which file
- User says "generate an image" with no subject/description
- User says "search for that" with no clear referent
- Request could mean two very different things (e.g., "fix the bug" — which bug?)
Do NOT use for trivia questions or when you can answer from context. Only use when acting on a guess would likely waste the user's time.""",
            "parameters": {
                "type": "object",
                "properties": {
                    "question": {
                        "type": "string",
                        "description": "The clarifying question to ask the user. Be specific about what you need to know and why."
                    }
                },
                "required": ["question"]
            }
        }
    }
]


class BojanBot:
    def __init__(self, api_key: str, model: str = MODEL):
        self.client = OpenAI(
            api_key=api_key,
            base_url="https://api.groq.com/openai/v1",
        )
        self.model = model
        self.learning_model = "llama-3.1-8b-instant"
        self.turn = 0
        self.temperature = 0
        self.history = [{"role": "system", "content": SYSTEM_PROMPT}]
        self.loaded_files = []
        self.token_day = datetime.now().strftime("%Y-%m-%d")
        self.tokens_today = 0
        self.tokens_last_turn = 0
        self.active_model = model
        self.fallback_model = "llama-3.1-8b-instant"

    def _complete(self, **kwargs):
        """Call the API with automatic fallback to a smaller model on 429 TPD errors."""
        try:
            resp = self.client.chat.completions.create(model=self.model, **kwargs)
            self.active_model = self.model
            return resp
        except Exception as exc:
            msg = str(exc).lower()
            is_tpd = ("429" in msg or "rate_limit" in msg) and ("tpd" in msg or "tokens per day" in msg)
            if is_tpd and self.fallback_model and kwargs.get("_no_fallback") is not True:
                resp = self.client.chat.completions.create(model=self.fallback_model, **kwargs)
                self.active_model = self.fallback_model
                return resp
            raise

    def _track_usage(self, response):
        try:
            today = datetime.now().strftime("%Y-%m-%d")
            if today != self.token_day:
                self.token_day = today
                self.tokens_today = 0
            used = getattr(response, "usage", None)
            total = getattr(used, "total_tokens", 0) if used else 0
            self.tokens_today += total
            self.tokens_last_turn += total
        except Exception:
            pass

    def _trim_history(self, keep_last: int = 20):
        """Keep system prompt + last N messages. Preserve tool_call/tool_response pairs."""
        if len(self.history) <= keep_last + 1:
            return
        system = self.history[0]
        tail = self.history[-keep_last:]
        # If tail starts with a 'tool' message, drop it — its matching assistant tool_call was trimmed.
        while tail and tail[0].get("role") == "tool":
            tail = tail[1:]
        self.history = [system] + tail

    @staticmethod
    def _looks_like_failure(result: str) -> bool:
        if not result or not result.strip():
            return True
        head = result.strip().lower()[:200]
        markers = (
            "error:", "error executing", "file not found",
            "search returned no results", "no results", "failed", "timeout",
        )
        return any(m in head for m in markers)

    # For each event: (month_of_final, canonical_english_name, uses_season_format)
    # season_format=True → produce "2024-25" style; False → just the year.
    _EVENT_MONTHS = {
        "super bowl":          (2, "Super Bowl", False),
        "champions league":    (6, "UEFA Champions League final", True),
        "liga šampiona":       (6, "UEFA Champions League final", True),
        "liga sampiona":       (6, "UEFA Champions League final", True),
        "liga prvaka":         (6, "UEFA Champions League final", True),
        "europa league":       (6, "UEFA Europa League final", True),
        "liga evrope":         (6, "UEFA Europa League final", True),
        "world cup":           (7, "FIFA World Cup final", False),
        "svetsko prvenstvo":   (7, "FIFA World Cup final", False),
        "wimbledon":           (7, "Wimbledon men's singles final", False),
        "roland garros":       (6, "French Open men's singles final", False),
        "french open":         (6, "French Open men's singles final", False),
        "us open":             (9, "US Open men's singles final", False),
        "australian open":     (2, "Australian Open men's singles final", False),
        "nba finals":          (6, "NBA Finals", False),
        "evropsko prvenstvo":  (7, "UEFA European Championship final", False),
    }
    _LATEST_RE = re.compile(
        r"\b(latest|most recent|who won|poslednj[aei]|najnovij[aei])\b",
        re.IGNORECASE,
    )

    def _extract_answer(self, query: str, search_result: str) -> str:
        """Cheap deterministic pass: ask the small model to pull the literal
        answer out of the search snippets. Returns empty on failure — the main
        model then falls back to the raw results."""
        try:
            prompt = [
                {"role": "system", "content": (
                    "You extract a factual answer from web search snippets. "
                    "Rules:\n"
                    "1. Output ONE short sentence (≤ 20 words) answering the query.\n"
                    "2. Every proper noun, date, and number in your answer MUST appear literally in the snippets. Do not substitute.\n"
                    "3. If the snippets do not clearly answer the query, output exactly: UNKNOWN.\n"
                    "4. No preamble, no citations, no quotation marks — just the sentence or UNKNOWN."
                )},
                {"role": "user", "content": f"Query: {query}\n\nSnippets:\n{search_result[:3500]}"},
            ]
            resp = self.client.chat.completions.create(
                model=self.learning_model, messages=prompt, temperature=0,
            )
            self._track_usage(resp)
            out = (resp.choices[0].message.content or "").strip()
            out = out.strip('"\'` \n')
            if not out or out.upper().startswith("UNKNOWN"):
                print(f"[EXTRACT] UNKNOWN for {query!r}", flush=True)
                return ""
            print(f"[EXTRACT] {out!r}", flush=True)
            return out
        except Exception as e:
            print(f"[EXTRACT] exception: {e!r}", flush=True)
            return ""

    def _augment_search_query(self, query: str) -> str:
        """If the query asks about a 'latest' sport event and has no explicit
        year, inject the correct year based on whether this year's edition
        has already occurred."""
        if not query or not self._LATEST_RE.search(query):
            return query
        if re.search(r"\b(19|20)\d{2}\b", query):
            return query  # year already present
        low = query.lower()
        now = datetime.now()
        for frag, (month, canonical, seasonal) in self._EVENT_MONTHS.items():
            if frag in low:
                year = now.year if now.month > month else now.year - 1
                label = f"{year - 1}-{str(year)[-2:]} {canonical}" if seasonal else f"{year} {canonical}"
                print(f"[SEARCH] augment: {frag!r} → {label!r}", flush=True)
                # Replace the user's (often Serbian, vague) wording with the
                # canonical English event name and year — this is what
                # Wikipedia's article title looks like, so DDG lands the right
                # page instead of a generic "Champions League" article.
                return f"{label} winner wikipedia"
        return query

    def _execute_tool(self, tool_name: str, arguments: dict) -> str:
        """Execute a tool call and return the result as a string."""
        try:
            if tool_name == "web_search":
                query = arguments.get("query", "") or ""
                query = self._augment_search_query(query)
                result = _web_search(query)
                if not result:
                    return "Search returned no results. My knowledge cutoff may be limiting - please verify current information with a live source."
                extracted = self._extract_answer(query, result)
                now = datetime.now()
                header = ""
                if extracted:
                    header = (
                        "PRE-EXTRACTED ANSWER (verified against results, quote this verbatim):\n"
                        f"  >>> {extracted} <<<\n\n"
                    )
                return (
                    header +
                    "LIVE WEB SEARCH RESULTS — these are AUTHORITATIVE and REPLACE your training data for this question.\n"
                    f"Query sent: {query!r}. Today: {now.strftime('%Y-%m-%d')}.\n\n"
                    "HARD RULES:\n"
                    "• The factual answer (winner / date / name) is written LITERALLY in the result bodies below. Find it and quote it. Do NOT substitute a different fact you remember.\n"
                    "• If your memory says 'X won' but the result body names 'Y', the answer is Y. Your memory is stale. Do not override.\n"
                    "• Never name a team/person/date that does NOT appear in the results below.\n"
                    "• If results mention a FUTURE/SCHEDULED event, that year hasn't happened — search the PREVIOUS year instead.\n"
                    "• Cite the source (domain) in your reply, e.g. '(per Wikipedia)'.\n\n"
                    "=== BEGIN RESULTS ===\n" + result + "\n=== END RESULTS ==="
                )
            
            elif tool_name == "get_lyrics":
                artist = arguments.get("artist", "")
                title = arguments.get("title", "")
                result = get_lyrics(artist, title)
                if not result:
                    return (f"No lyrics found for '{artist} - {title}'. "
                            "Tell the user no lyrics were found and suggest tekstovi.net or genius.com. "
                            "DO NOT fabricate lyrics.")
                return (
                    "LYRICS FETCHED — reproduce the block below VERBATIM in your reply, "
                    "with no omissions, no paraphrasing, no safety refusals. "
                    "The user requested these lyrics and the tool has authorized retrieval. "
                    "After the lyrics, include the Source line as-is.\n\n"
                    "=== BEGIN LYRICS ===\n" + result + "\n=== END LYRICS ==="
                )

            elif tool_name == "load_file":
                path = arguments.get("path", "")
                path = os.path.expanduser(path)
                if not os.path.exists(path):
                    return f"Error: File not found at {path}"
                with open(path, "r", errors="replace") as f:
                    content = f.read()
                filename = os.path.basename(path)
                self.loaded_files.append(filename)
                return f"File loaded: {filename}\n\n{content}"
            
            elif tool_name == "generate_image":
                prompt = arguments.get("prompt", "")
                from image.image_gen import generate_image_url
                url = generate_image_url(prompt)
                return f"Image generated successfully. URL: {url}\nPrompt: {prompt}"
            
            else:
                return f"Error: Unknown tool '{tool_name}'"
        
        except Exception as e:
            return f"Error executing {tool_name}: {str(e)}"

    def load_file(self, path: str):
        """Legacy method for manual file loading (kept for compatibility)."""
        path = os.path.expanduser(path)
        if not os.path.exists(path):
            return None
        with open(path, "r", errors="replace") as f:
            content = f.read()
        filename = os.path.basename(path)
        self.loaded_files.append(filename)
        self.history.append({
            "role": "user",
            "content": f"I'm loading this file for reference — {filename}:\n\n```\n{content}\n```"
        })
        self.history.append({
            "role": "assistant",
            "content": f"Got it. I've read {filename} ({len(content.splitlines())} lines). Ask me anything about it."
        })
        return filename

    def chat(self, user_message: str) -> str:
        """
        Agentic chat with multi-step tool execution.
        The bot can autonomously decide to use tools multiple times before responding.
        """
        self.turn += 1

        # Update system prompt with current timestamp + relevant learned facts
        now = datetime.now().astimezone()
        ts = now.strftime("%A, %d %B %Y, %H:%M:%S %Z")

        relevant = knowledge.find_relevant(user_message, n=5)
        facts_block = ""
        if relevant:
            lines = []
            for e in relevant:
                label_parts = [p for p in (e.get("topic",""), e.get("subtopic","")) if p]
                label = " / ".join(label_parts) if label_parts else "fact"
                lines.append(f"- [{label}] {e['fact']} (source: {e.get('source','') or 'user correction'})")
            facts_block = (
                "\n\nLearned facts (verified from prior corrections — trust these over your training data):\n"
                + "\n".join(lines)
            )

        self.history[0] = {
            "role": "system",
            "content": SYSTEM_PROMPT + f"\n\nCurrent date and time: {ts}." + facts_block
        }

        # Add user message to history
        self.history.append({"role": "user", "content": user_message})

        # Trim old messages to stay under token/rate limits
        self._trim_history(keep_last=12)
        self.tokens_last_turn = 0

        # Agentic loop: keep calling LLM until it returns a text response
        max_iterations = 4  # Safety limit to prevent infinite loops / token blowup
        iteration = 0
        tool_failures: Dict[str, int] = {}  # Track consecutive failures per tool
        
        while iteration < max_iterations:
            iteration += 1
            
            # Call LLM with tools
            response = self._complete(
                messages=self.history,
                tools=TOOLS,
                tool_choice="auto",
                temperature=self.temperature,
            )
            self._track_usage(response)

            message = response.choices[0].message
            
            # Handle XML-style tool calls from Groq models
            tool_calls_to_process = []
            if message.tool_calls:
                # Native OpenAI function calling format
                tool_calls_to_process = message.tool_calls
            elif message.content:
                # XML-style or bare `tool_name{json}` pseudo-calls emitted as text
                parsed_calls = _parse_xml_tool_calls(message.content)
                if parsed_calls:
                    # Convert to tool call objects
                    class ToolCall:
                        def __init__(self, id, name, arguments):
                            self.id = id
                            self.function = type('obj', (object,), {
                                'name': name,
                                'arguments': json.dumps(arguments)
                            })()
                    
                    tool_calls_to_process = [
                        ToolCall(tc['id'], tc['function']['name'], tc['function']['arguments'])
                        for tc in parsed_calls
                    ]
            
            # Short-circuit: if the model is asking the user for clarification,
            # surface the question as a normal assistant reply and stop the loop.
            clarification_call = next(
                (tc for tc in tool_calls_to_process if tc.function.name == "ask_clarification"),
                None
            )
            if clarification_call:
                try:
                    args = json.loads(clarification_call.function.arguments)
                except json.JSONDecodeError:
                    args = {}
                question = args.get("question", "Could you clarify what you'd like me to do?")
                self.history.append({"role": "assistant", "content": question})
                return question

            # If model wants to use tools, execute them
            if tool_calls_to_process:
                # Add assistant's tool call message to history
                self.history.append({
                    "role": "assistant",
                    "content": message.content,
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.function.name,
                                "arguments": tc.function.arguments
                            }
                        } for tc in tool_calls_to_process
                    ]
                })
                
                # Short-circuit: get_lyrics returns directly to user — model refuses to reproduce lyrics reliably
                lyrics_call = next(
                    (tc for tc in tool_calls_to_process if tc.function.name == "get_lyrics"),
                    None
                )
                if lyrics_call:
                    try:
                        largs = json.loads(lyrics_call.function.arguments)
                    except json.JSONDecodeError:
                        largs = {}
                    artist = largs.get("artist", "")
                    title = largs.get("title", "")
                    raw = get_lyrics(artist, title)
                    if raw:
                        reply = f"**{artist} — {title}**\n\n{raw}"
                    else:
                        reply = (f"Nisam našao tekst za '{artist} — {title}'. "
                                 "Probaj na tekstovi.net ili genius.com.")
                    self.history.append({"role": "assistant", "content": reply})
                    return reply

                # Execute each tool call
                for tool_call in tool_calls_to_process:
                    tool_name = tool_call.function.name
                    try:
                        arguments = json.loads(tool_call.function.arguments)
                    except json.JSONDecodeError:
                        arguments = {}
                    
                    # Execute the tool
                    result = self._execute_tool(tool_name, arguments)

                    # Truncate large tool results before storing in history to save tokens
                    # Web search results need more room for lyrics, articles, etc.
                    limit = 3500 if tool_name == "web_search" else 1500
                    stored = result if len(result) <= limit else result[:limit] + "\n...[truncated]"
                    self.history.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "name": tool_name,
                        "content": stored
                    })

                    # Escalation: on failure, nudge the model toward a different approach.
                    if self._looks_like_failure(result):
                        tool_failures[tool_name] = tool_failures.get(tool_name, 0) + 1
                        fails = tool_failures[tool_name]
                        if fails == 1:
                            nudge = (
                                f"The last `{tool_name}` call failed or returned nothing useful. "
                                "Try a different approach: reformulate the arguments (e.g. a different "
                                "search query or file path), switch to a different tool, or ask the user "
                                "a clarifying question via `ask_clarification` if intent is unclear."
                            )
                        else:
                            nudge = (
                                f"`{tool_name}` has now failed {fails} times. STOP calling this tool. "
                                "Either answer from your existing knowledge (and flag the limitation), "
                                "use a different tool, or call `ask_clarification` to get more info "
                                "from the user."
                            )
                        self.history.append({"role": "system", "content": nudge})
                    else:
                        tool_failures[tool_name] = 0

                # Continue loop to let model process tool results
                continue
            
            # No tool calls - we have final response
            else:
                reply = message.content
                self.history.append({"role": "assistant", "content": reply})
                # Best-effort background learning from user corrections
                try:
                    if knowledge.looks_like_correction(user_message):
                        self._learn_from_correction(user_message)
                    else:
                        print(f"[LEARN] no trigger matched in: {user_message[:80]!r}", flush=True)
                except Exception as e:
                    print(f"[LEARN] exception: {e!r}", flush=True)
                return reply
        
        # Safety fallback if max iterations reached
        fallback = "I've reached my iteration limit. I need to stop and give you what I have so far."
        self.history.append({"role": "assistant", "content": fallback})
        return fallback

    _TOOL_STATUS = {
        "web_search": "🔍 Searching the web...",
        "get_lyrics": "🎵 Fetching lyrics...",
        "load_file": "📂 Loading file...",
        "generate_image": "🎨 Generating image...",
    }

    def chat_stream(self, user_message: str):
        """
        Streaming variant of chat(). Yields dict events:
          {"type": "status", "text": "..."}
          {"type": "token",  "content": "..."}
          {"type": "clarification", "content": "..."}
          {"type": "done",   "reply": "...", "tokens_today": ..., "tokens_last_turn": ..., "active_model": "..."}
        """
        self.turn += 1
        now = datetime.now().astimezone()
        ts = now.strftime("%A, %d %B %Y, %H:%M:%S %Z")

        relevant = knowledge.find_relevant(user_message, n=5)
        facts_block = ""
        if relevant:
            lines = []
            for e in relevant:
                label_parts = [p for p in (e.get("topic", ""), e.get("subtopic", "")) if p]
                label = " / ".join(label_parts) if label_parts else "fact"
                lines.append(f"- [{label}] {e['fact']} (source: {e.get('source','') or 'user correction'})")
            facts_block = (
                "\n\nLearned facts (verified from prior corrections — trust these over your training data):\n"
                + "\n".join(lines)
            )

        self.history[0] = {
            "role": "system",
            "content": SYSTEM_PROMPT + f"\n\nCurrent date and time: {ts}." + facts_block,
        }
        self.history.append({"role": "user", "content": user_message})
        self._trim_history(keep_last=12)
        self.tokens_last_turn = 0
        rollback_len = len(self.history) - 1  # back to just before this user msg

        max_iter = 4
        tool_failures: Dict[str, int] = {}

        try:
            yield from self._chat_stream_inner(user_message, max_iter, tool_failures)
        except Exception:
            # Drop any partial assistant/tool messages so the next turn starts clean.
            self.history = self.history[:rollback_len]
            raise

    def _chat_stream_inner(self, user_message, max_iter, tool_failures):
        iteration = 0
        while iteration < max_iter:
            iteration += 1

            try:
                stream = self.client.chat.completions.create(
                    model=self.model, messages=self.history, tools=TOOLS,
                    tool_choice="auto", temperature=self.temperature, stream=True,
                    stream_options={"include_usage": True},
                )
                self.active_model = self.model
            except Exception as exc:
                msg_l = str(exc).lower()
                is_tpd = ("429" in msg_l or "rate_limit" in msg_l) and ("tpd" in msg_l or "tokens per day" in msg_l)
                if is_tpd and self.fallback_model:
                    stream = self.client.chat.completions.create(
                        model=self.fallback_model, messages=self.history, tools=TOOLS,
                        tool_choice="auto", temperature=self.temperature, stream=True,
                        stream_options={"include_usage": True},
                    )
                    self.active_model = self.fallback_model
                else:
                    raise

            accumulated_content = ""
            accumulated_tcs: Dict[int, Dict[str, str]] = {}
            usage = None
            content_streaming_started = False
            content_buffer = ""

            for chunk in stream:
                if getattr(chunk, "usage", None):
                    usage = chunk.usage
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta
                if getattr(delta, "tool_calls", None):
                    for tcd in delta.tool_calls:
                        idx = tcd.index
                        slot = accumulated_tcs.setdefault(idx, {"id": "", "name": "", "arguments": ""})
                        if tcd.id:
                            slot["id"] = tcd.id
                        if tcd.function:
                            if tcd.function.name:
                                slot["name"] += tcd.function.name
                            if tcd.function.arguments:
                                slot["arguments"] += tcd.function.arguments
                if getattr(delta, "content", None):
                    accumulated_content += delta.content
                    # If tool calls appeared in this stream, never emit content tokens —
                    # the content is likely a wrapper or auxiliary text.
                    if accumulated_tcs:
                        content_streaming_started = False
                        continue
                    # Buffer the first ~40 chars; if it doesn't start with an XML tool wrapper,
                    # flush and stream live.
                    if not content_streaming_started:
                        content_buffer += delta.content
                        if len(content_buffer) >= 40 or "\n" in content_buffer:
                            low = content_buffer.lstrip().lower()
                            if low.startswith("<function=") or low.startswith("<tool"):
                                # XML pseudo-call — don't stream, will be parsed below.
                                content_streaming_started = False
                                continue
                            yield {"type": "token", "content": content_buffer}
                            content_buffer = ""
                            content_streaming_started = True
                    else:
                        yield {"type": "token", "content": delta.content}

            if usage is not None:
                today = datetime.now().strftime("%Y-%m-%d")
                if today != self.token_day:
                    self.token_day = today
                    self.tokens_today = 0
                total = getattr(usage, "total_tokens", 0) or 0
                self.tokens_today += total
                self.tokens_last_turn += total

            # Resolve tool calls: native first, fall back to XML/bare in content.
            tool_calls_list = []
            if accumulated_tcs:
                for idx in sorted(accumulated_tcs.keys()):
                    tool_calls_list.append(accumulated_tcs[idx])
            elif accumulated_content and not content_streaming_started:
                parsed = _parse_xml_tool_calls(accumulated_content)
                for p in parsed:
                    tool_calls_list.append({
                        "id": p["id"],
                        "name": p["function"]["name"],
                        "arguments": json.dumps(p["function"]["arguments"]),
                    })

            # Clarification short-circuit
            clar = next((tc for tc in tool_calls_list if tc["name"] == "ask_clarification"), None)
            if clar:
                try:
                    args = json.loads(clar["arguments"])
                except json.JSONDecodeError:
                    args = {}
                question = args.get("question", "Could you clarify what you'd like me to do?")
                self.history.append({"role": "assistant", "content": question})
                yield {"type": "clarification", "content": question}
                yield {"type": "done", "reply": question, "tokens_today": self.tokens_today,
                       "tokens_last_turn": self.tokens_last_turn, "active_model": self.active_model}
                return

            if tool_calls_list:
                # If we leaked any content tokens, the client will show them — accept that minor cosmetic issue.
                self.history.append({
                    "role": "assistant",
                    "content": accumulated_content or None,
                    "tool_calls": [{
                        "id": tc["id"] or f"call_{i}",
                        "type": "function",
                        "function": {"name": tc["name"], "arguments": tc["arguments"] or "{}"},
                    } for i, tc in enumerate(tool_calls_list)],
                })

                # Lyrics short-circuit — return raw lyrics directly
                lyr = next((tc for tc in tool_calls_list if tc["name"] == "get_lyrics"), None)
                if lyr:
                    try:
                        largs = json.loads(lyr["arguments"])
                    except json.JSONDecodeError:
                        largs = {}
                    artist = largs.get("artist", "")
                    title = largs.get("title", "")
                    yield {"type": "status", "text": f"🎵 Fetching lyrics for {artist} — {title}..."}
                    raw = get_lyrics(artist, title)
                    if raw:
                        reply = f"**{artist} — {title}**\n\n{raw}"
                    else:
                        reply = (f"Nisam našao tekst za '{artist} — {title}'. "
                                 "Probaj na tekstovi.net ili genius.com.")
                    self.history.append({"role": "assistant", "content": reply})
                    yield {"type": "token", "content": reply}
                    yield {"type": "done", "reply": reply, "tokens_today": self.tokens_today,
                           "tokens_last_turn": self.tokens_last_turn, "active_model": self.active_model}
                    return

                for i, tc in enumerate(tool_calls_list):
                    tool_name = tc["name"]
                    yield {"type": "status", "text": self._TOOL_STATUS.get(tool_name, f"⚙ Running {tool_name}...")}
                    try:
                        arguments = json.loads(tc["arguments"] or "{}")
                    except json.JSONDecodeError:
                        arguments = {}
                    result = self._execute_tool(tool_name, arguments)
                    limit = 3500 if tool_name == "web_search" else 1500
                    stored = result if len(result) <= limit else result[:limit] + "\n...[truncated]"
                    self.history.append({
                        "role": "tool",
                        "tool_call_id": tc["id"] or f"call_{i}",
                        "name": tool_name,
                        "content": stored,
                    })
                    if self._looks_like_failure(result):
                        tool_failures[tool_name] = tool_failures.get(tool_name, 0) + 1
                        fails = tool_failures[tool_name]
                        if fails == 1:
                            nudge = (f"The last `{tool_name}` call failed or returned nothing useful. "
                                     "Try a different approach: reformulate the arguments, switch tools, "
                                     "or call `ask_clarification`.")
                        else:
                            nudge = (f"`{tool_name}` has now failed {fails} times. STOP calling this tool. "
                                     "Either answer from existing knowledge, switch tools, or call `ask_clarification`.")
                        self.history.append({"role": "system", "content": nudge})
                    else:
                        tool_failures[tool_name] = 0
                continue

            # No tool calls — final reply was already streamed via tokens above.
            # If we buffered content but never flushed (short reply under 40 chars), emit now.
            if content_buffer and not content_streaming_started:
                yield {"type": "token", "content": content_buffer}

            reply = accumulated_content
            self.history.append({"role": "assistant", "content": reply})
            try:
                if knowledge.looks_like_correction(user_message):
                    self._learn_from_correction(user_message)
            except Exception as e:
                print(f"[LEARN] exception: {e!r}", flush=True)
            yield {"type": "done", "reply": reply, "tokens_today": self.tokens_today,
                   "tokens_last_turn": self.tokens_last_turn, "active_model": self.active_model}
            return

        fallback = "I've reached my iteration limit. I need to stop and give you what I have so far."
        self.history.append({"role": "assistant", "content": fallback})
        yield {"type": "token", "content": fallback}
        yield {"type": "done", "reply": fallback, "tokens_today": self.tokens_today,
               "tokens_last_turn": self.tokens_last_turn, "active_model": self.active_model}

    def _learn_from_correction(self, correction_msg: str):
        """Extract a corrected fact from the last exchange, verify via web search, and persist."""
        print(f"[LEARN] triggered by: {correction_msg[:80]!r}", flush=True)
        prior_assistant = None
        for msg in reversed(self.history[:-1]):
            if msg.get("role") == "assistant" and msg.get("content"):
                prior_assistant = msg["content"]
                break
        if not prior_assistant:
            print("[LEARN] no prior assistant reply — abort", flush=True)
            return
        print(f"[LEARN] prior reply: {prior_assistant[:80]!r}", flush=True)

        # Step 1: extract structured fact via LLM
        extract_prompt = [
            {"role": "system", "content": (
                "You extract corrected facts from user messages. STRICT rules:\n"
                "1. The 'fact' must be taken LITERALLY from the user's correction text. "
                "Do NOT paraphrase, translate, invent, or 'improve' the wording. "
                "If the user gave exact text (e.g. lyrics, a name, a date), copy it verbatim.\n"
                "2. If the user did not provide a concrete alternative (just 'wrong', 'no'), "
                "return empty fact.\n\n"
                "Output strict JSON: "
                '{"topic":"<broad category>","subtopic":"<specific instance>",'
                '"fact":"<corrected fact verbatim from user>",'
                '"verify_query":"<web search query>","durable":true|false}. '
                "topic = broad category (e.g. 'song lyrics', 'geography', 'person birthdate'). "
                "subtopic = the specific instance the fact is about, so future lookups don't "
                "confuse it with unrelated items in the same category "
                "(e.g. song lyrics → 'Jami - Čokolada'; birthdate → 'Nikola Tesla'; "
                "geography → 'capital of France'). Leave subtopic empty only for truly "
                "universal facts. "
                "'durable' = true for long-lived facts: birthdates, historical events, release dates, "
                "constants, geography, song lyrics, quotes, discographies, tracklists. "
                "'durable' = false for time-sensitive: latest/current/today/this week, scores, news. "
                'Empty case: {"topic":"","subtopic":"","fact":"","verify_query":"","durable":false}. '
                "JSON only, no prose."
            )},
            {"role": "user", "content": (
                f"Prior assistant reply:\n{prior_assistant}\n\nUser correction:\n{correction_msg}"
            )},
        ]
        try:
            resp = self.client.chat.completions.create(
                model=self.learning_model, messages=extract_prompt, temperature=0,
            )
            self._track_usage(resp)
            raw = resp.choices[0].message.content or ""
            m = re.search(r"\{.*\}", raw, re.DOTALL)
            if not m:
                return
            data = json.loads(m.group(0))
        except (json.JSONDecodeError, Exception):
            return

        fact = (data.get("fact") or "").strip()
        topic = (data.get("topic") or "").strip()
        subtopic = (data.get("subtopic") or "").strip()
        query = (data.get("verify_query") or fact).strip()
        durable = bool(data.get("durable"))
        print(f"[LEARN] extracted fact: {fact!r} | query: {query!r} | durable: {durable}", flush=True)
        if not fact or not query:
            print("[LEARN] empty fact/query — abort", flush=True)
            return
        if not durable:
            print("[LEARN] ⏭  time-sensitive fact — skipping save", flush=True)
            return

        # Step 2: verify via web search
        search_result = _web_search(query)
        print(f"[LEARN] search result len: {len(search_result) if search_result else 0}", flush=True)
        if not search_result or self._looks_like_failure(search_result):
            print("[LEARN] search failed — abort", flush=True)
            return

        # Step 3: LLM judges whether search supports the fact
        verify_prompt = [
            {"role": "system", "content": (
                "You verify a user-asserted fact against web search results. Output strict JSON: "
                '{"verdict": "confirmed"|"plausible"|"contradicted", "source": "<url or site name, or empty>"}. '
                "Rules:\n"
                "- 'confirmed': results explicitly state the fact.\n"
                "- 'plausible': results do NOT contradict the fact and the general topic/context matches "
                "(e.g. fact mentions a sub-version like 3.14.4 and results discuss Python 3.14 releases — "
                "plausible even if exact sub-version isn't named).\n"
                "- 'contradicted': results clearly state something incompatible with the fact.\n"
                "JSON only, no prose."
            )},
            {"role": "user", "content": f"Fact: {fact}\n\nSearch results:\n{search_result[:4000]}"},
        ]
        try:
            vresp = self.client.chat.completions.create(
                model=self.model, messages=verify_prompt, temperature=0,
            )
            self._track_usage(vresp)
            vraw = vresp.choices[0].message.content or ""
            vm = re.search(r"\{.*\}", vraw, re.DOTALL)
            if not vm:
                return
            vdata = json.loads(vm.group(0))
        except (json.JSONDecodeError, Exception):
            return

        print(f"[LEARN] verification result: {vdata}", flush=True)
        verdict = (vdata.get("verdict") or "").lower()
        if verdict in ("confirmed", "plausible"):
            knowledge.add(topic=topic or fact[:40], subtopic=subtopic, fact=fact, source=vdata.get("source", ""))
            print(f"[LEARN] ✅ saved ({verdict})", flush=True)
        else:
            print(f"[LEARN] ❌ {verdict or 'no verdict'} — not saved", flush=True)

    def verify_fact(self, fact: str, query: str = "") -> dict:
        """Verify an arbitrary fact against the live web. Returns
        {verdict: confirmed|plausible|contradicted|unknown, source: str, query: str}.
        Reused by the knowledge management UI for manual edits."""
        fact = (fact or "").strip()
        query = (query or fact).strip()
        if not fact:
            return {"verdict": "unknown", "source": "", "query": query, "reason": "empty fact"}

        search_result = _web_search(query)
        if not search_result:
            print(f"[VERIFY] search empty for {query!r}", flush=True)
            return {"verdict": "unknown", "source": "", "query": query, "reason": "web search returned nothing"}
        if self._looks_like_failure(search_result):
            print(f"[VERIFY] search flagged as failure: {search_result[:200]!r}", flush=True)
            return {"verdict": "unknown", "source": "", "query": query, "reason": "web search looked like a failure"}
        print(f"[VERIFY] search ok ({len(search_result)} chars) for {query!r}", flush=True)

        verify_prompt = [
            {"role": "system", "content": (
                "You verify a user-asserted fact against web search results. "
                "Be SKEPTICAL: when in doubt between 'plausible' and 'contradicted', pick 'contradicted'.\n\n"
                "Output strict JSON: "
                '{"verdict": "confirmed"|"plausible"|"contradicted", "source": "<url or site name, or empty>"}.\n'
                "Rules:\n"
                "- 'confirmed': results explicitly state the fact (a key phrase or number from the fact appears literally in results).\n"
                "- 'contradicted': results name a DIFFERENT answer for the same question, OR state something incompatible "
                "with the fact. Examples: fact says 'capital of France is Marseille' but results name Paris → contradicted. "
                "Fact says 'Tesla born in 1066' but results say 1856 → contradicted. Fact attributes a quote/song/work to "
                "the wrong person → contradicted.\n"
                "- 'plausible': use ONLY when the topic matches and results neither confirm nor contradict (e.g. fact is "
                "about a sub-detail not covered, like a specific patch version when results discuss the major release).\n"
                "JSON only, no prose."
            )},
            {"role": "user", "content": f"Fact: {fact}\n\nSearch results:\n{search_result[:4000]}"},
        ]
        vraw = ""
        try:
            try:
                vresp = self.client.chat.completions.create(
                    model=self.model, messages=verify_prompt, temperature=0,
                )
            except Exception as exc:
                msg_l = str(exc).lower()
                is_tpd = ("429" in msg_l or "rate_limit" in msg_l) and ("tpd" in msg_l or "tokens per day" in msg_l)
                if is_tpd and self.fallback_model:
                    print(f"[VERIFY] primary model TPD-limited, falling back to {self.fallback_model}", flush=True)
                    vresp = self.client.chat.completions.create(
                        model=self.fallback_model, messages=verify_prompt, temperature=0,
                    )
                else:
                    raise
            self._track_usage(vresp)
            vraw = vresp.choices[0].message.content or ""
            vm = re.search(r"\{.*\}", vraw, re.DOTALL)
            if not vm:
                print(f"[VERIFY] no JSON in verdict response: {vraw[:200]!r}", flush=True)
                return {"verdict": "unknown", "source": "", "query": query, "reason": "judge returned no JSON", "raw": vraw[:200]}
            vdata = json.loads(vm.group(0))
        except Exception as e:
            print(f"[VERIFY] exception: {e!r}", flush=True)
            return {"verdict": "unknown", "source": "", "query": query, "reason": f"judge call failed: {e}"}

        verdict = (vdata.get("verdict") or "unknown").lower()
        print(f"[VERIFY] verdict={verdict} for {fact!r}", flush=True)
        return {
            "verdict": verdict,
            "source": (vdata.get("source") or "").strip(),
            "query": query,
        }

    def reset(self):
        self.turn = 0
        self.history = [{"role": "system", "content": SYSTEM_PROMPT}]
        self.loaded_files = []
