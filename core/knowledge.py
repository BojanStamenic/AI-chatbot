import json
import os
import re
from datetime import datetime
from typing import List, Dict

from core.config import BASE_DIR

KNOWLEDGE_PATH = os.path.join(BASE_DIR, "knowledge.json")

CORRECTION_TRIGGERS_RE = re.compile(
    r"\b(ne|nije|nego|pogre[sš]no|neta[cč]no|u stvari|ustvari|zapravo|"
    r"izmislio|izmi[sš]lja[sš]|la[zž]e[sš]|gre[sš]i[sš]|zapamti|"
    r"wrong|incorrect|actually|not true|false|thats? not)\b",
    re.IGNORECASE,
)


def load() -> List[Dict]:
    if not os.path.exists(KNOWLEDGE_PATH):
        return []
    try:
        with open(KNOWLEDGE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return []


def save(entries: List[Dict]):
    with open(KNOWLEDGE_PATH, "w", encoding="utf-8") as f:
        json.dump(entries, f, ensure_ascii=False, indent=2)


def add(topic: str, fact: str, source: str = "", subtopic: str = ""):
    entries = load()
    # Avoid exact duplicate facts
    for e in entries:
        if e.get("fact", "").strip().lower() == fact.strip().lower():
            return
    entries.append({
        "topic": topic.strip(),
        "subtopic": subtopic.strip(),
        "fact": fact.strip(),
        "source": source.strip(),
        "verified_at": datetime.now().isoformat(timespec="seconds"),
    })
    save(entries)


def delete(idx: int) -> bool:
    entries = load()
    if 0 <= idx < len(entries):
        entries.pop(idx)
        save(entries)
        return True
    return False


def update(idx: int, **fields) -> bool:
    entries = load()
    if not (0 <= idx < len(entries)):
        return False
    allowed = ("topic", "subtopic", "fact", "source")
    for k, v in fields.items():
        if k in allowed and isinstance(v, str):
            entries[idx][k] = v.strip()
    entries[idx]["verified_at"] = datetime.now().isoformat(timespec="seconds")
    save(entries)
    return True


def find_relevant(query: str, n: int = 5) -> List[Dict]:
    """Keyword overlap between query and each entry's topic+subtopic+fact.
    Subtopic matches are weighted highest so specific entries (e.g. a particular
    song) don't get pulled in for unrelated queries sharing only the broad topic.
    """
    entries = load()
    if not entries:
        return []
    tokens = set(re.findall(r"\w+", query.lower()))
    if not tokens:
        return []

    def toks(s: str) -> set:
        return set(re.findall(r"\w+", (s or "").lower()))

    def score(e: Dict) -> int:
        sub = toks(e.get("subtopic", ""))
        top = toks(e.get("topic", ""))
        fact = toks(e.get("fact", ""))
        s = 3 * len(tokens & sub) + 2 * len(tokens & top) + len(tokens & fact)
        # If entry has a subtopic but query matches none of its subtopic tokens,
        # it is almost certainly about a different specific instance — suppress.
        if sub and not (tokens & sub) and not (tokens & fact):
            return 0
        return s

    scored = [(score(e), e) for e in entries]
    scored = [(s, e) for s, e in scored if s > 0]
    scored.sort(key=lambda x: x[0], reverse=True)
    return [e for _, e in scored[:n]]


def looks_like_correction(user_message: str) -> bool:
    if not user_message:
        return False
    return bool(CORRECTION_TRIGGERS_RE.search(user_message))
