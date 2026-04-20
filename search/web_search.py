import re as _re

# Srpske filler reci koje bune DuckDuckGo (npr. "kako" → Princess Kako)
_FILLER = _re.compile(
    r'\b(kako|je\b|su\b|ko\b|da\b|li\b|koji|koja|koje|šta|sta\b|gde|gdje|'
    r'kada|zašto|bio|bila|bilo|nije|nisu|'
    r'u\b|na\b|za\b|sa\b|od\b|do\b|po\b|iz\b|i\b|a\b|ili|'
    r'taj|ta\b|to\b|ovo|ono)\b',
    _re.IGNORECASE
)

# Kljucne reci koje trigeruju web pretragu (EN + SR)
SEARCH_TRIGGERS = [
    "latest", "current", "today", "tonight", "this week", "this year",
    "right now", "news", "recently", "who won", "score", "what happened",
    "result", "match", "game", "league", "champions", "tournament",
    "transfer", "standings", "playoff", "price of",
    "when did", "when was", "when were", "when is",
    "koji datum", "kada je", "kada su",
    "najnovije", "danas", "vesti", "trenutno", "ove godine", "ove nedelje",
    "liga", "utakmica", "rezultat", "prošao", "prosao", "pobedio",
    "izgubio", "kako je", "kako su", "ko je", "koji je", "koja je",
    "šampionat", "sampionat", "kup", "turnir", "tabela", "finale",
    "polufinale", "četvrtfinale", "cetvrfinale", "gol", "bod", "remi",
]

# Ako poruka sadrzi ove reci → NE trigeruj pretragu (kodiranje pitanje)
CODE_SKIP = [
    "function", "class", "variable", "array", "loop", "import", "export",
    "def ", "bug", "debug", "refactor", "python", "javascript",
    "typescript", "sql", "database", "algorithm", "regex",
]

# Reci kojima pocinje follow-up pitanje posle pretrage
_FOLLOWUP_STARTERS = {
    "what", "when", "where", "who", "how", "which", "why", "and", "did",
    "does", "is", "are", "was", "were", "can", "could", "will", "would",
    "šta", "kada", "gde", "gdje", "ko", "koji", "koja", "kako", "i", "a",
    "zašto", "da li", "koliko",
}


def _needs_search(text: str) -> bool:
    low = text.lower()
    if any(k in low for k in CODE_SKIP):
        return False
    return any(k in low for k in SEARCH_TRIGGERS)


def _build_search_query(text: str) -> str:
    from datetime import datetime
    cleaned = _FILLER.sub(" ", text)
    cleaned = _re.sub(r"\s+", " ", cleaned).strip()
    now = datetime.now()
    return f"{cleaned} {now.strftime('%B %Y')}"


def _is_search_followup(text: str) -> bool:
    stripped = text.strip()
    if "?" in stripped:
        return True
    if len(stripped.split()) > 6:
        return False
    first = stripped.split()[0].lower().rstrip("?!.,") if stripped else ""
    return first in _FOLLOWUP_STARTERS


def _web_search(query: str) -> str:
    from duckduckgo_search import DDGS
    try:
        ddgs = DDGS()
        hits = []
        for tl in ("w", "m", None):
            try:
                kw = {"max_results": 5}
                if tl:
                    kw["timelimit"] = tl
                hits = list(ddgs.text(query, **kw))
            except Exception as e:
                print(f"[Web search] timelimit={tl} failed: {e}")
                continue
            if hits:
                break
        if not hits:
            print(f"[Web search] No results found for: {query}")
            return ""
        snippets = "\n\n".join(
            f"{i+1}. {h['title']}\n{h['body']}" for i, h in enumerate(hits)
        )
        print(f"[Web search] Found {len(hits)} results for: {query}")
        return f"[Web search results]\n{snippets}"
    except Exception as e:
        print(f"[Web search] Fatal error: {e}")
        return ""
