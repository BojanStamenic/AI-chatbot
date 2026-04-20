import re as _re
import time as _time
import random as _random
from typing import Optional as _Optional

# Simple in-memory cache to avoid redundant searches
_search_cache = {}
_cache_ttl = 300  # 5 minutes

# User agents to rotate through - helps avoid rate limiting
_USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
]

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
    """
    Search the web using DuckDuckGo with caching and retry logic.
    Returns formatted search results or an empty string on failure.
    """
    from duckduckgo_search import DDGS
    
    # Check cache first
    cache_key = query.lower().strip()
    if cache_key in _search_cache:
        cached_result, timestamp = _search_cache[cache_key]
        if _time.time() - timestamp < _cache_ttl:
            print(f"[Web search] Using cached results for: {query}")
            return cached_result
    
    # Try search with exponential backoff
    max_retries = 3
    base_delay = 2.0  # Increased from 1.0 to 2.0 seconds
    
    for attempt in range(max_retries):
        try:
            # Rotate user agent to avoid detection
            user_agent = _random.choice(_USER_AGENTS)
            
            # Create DDGS instance with custom headers
            ddgs = DDGS(headers={'User-Agent': user_agent})
            hits = []
            
            # Try different timelimits
            for tl in (None, "m", "y"):  # Any, month, year (skip week - often fails)
                try:
                    kw = {"max_results": 5}
                    if tl:
                        kw["timelimit"] = tl
                    
                    # Add small random delay to avoid pattern detection
                    if attempt > 0 or tl != None:
                        _time.sleep(0.5 + _random.random())
                    
                    hits = list(ddgs.text(query, **kw))
                    if hits:
                        break
                except Exception as e:
                    error_msg = str(e).lower()
                    if "ratelimit" in error_msg or "403" in error_msg or "202" in error_msg:
                        print(f"[Web search] Rate limited (timelimit={tl})")
                        break  # Exit timelimit loop to retry entire search
                    continue
            
            if hits:
                snippets = "\n\n".join(
                    f"{i+1}. {h['title']}\n{h['body']}" for i, h in enumerate(hits)
                )
                result = f"[Web search results]\n{snippets}"
                
                # Cache successful result
                _search_cache[cache_key] = (result, _time.time())
                print(f"[Web search] Found {len(hits)} results for: {query}")
                return result
            
            # If we got here and no hits, retry with backoff
            if attempt < max_retries - 1:
                delay = base_delay * (2 ** attempt) + _random.uniform(0, 1)
                print(f"[Web search] No results, attempt {attempt + 1}/{max_retries}, waiting {delay:.1f}s...")
                _time.sleep(delay)
            
        except Exception as e:
            error_msg = str(e).lower()
            if "ratelimit" in error_msg or "403" in error_msg:
                if attempt < max_retries - 1:
                    delay = base_delay * (2 ** attempt) + _random.uniform(1, 2)
                    print(f"[Web search] Rate limited, waiting {delay:.1f}s... ({attempt + 1}/{max_retries})")
                    _time.sleep(delay)
                else:
                    print(f"[Web search] Rate limit persists after {max_retries} attempts")
                    return "[Search temporarily unavailable. The information I have may be outdated - please verify with a live source.]"
            else:
                print(f"[Web search] Error: {e}")
                if attempt < max_retries - 1:
                    _time.sleep(base_delay + _random.random())
    
    print(f"[Web search] No results found after {max_retries} attempts for: {query}")
    return "[Could not retrieve search results. My knowledge cutoff may limit my ability to answer this - please check a current source.]"


def _clear_search_cache():
    """Clear the search result cache. Useful for testing or forcing fresh results."""
    global _search_cache
    _search_cache.clear()
    print("[Web search] Cache cleared")
