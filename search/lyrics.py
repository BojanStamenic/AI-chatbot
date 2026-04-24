import re
import html
import unicodedata
import httpx


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


def _tokens(s: str) -> set:
    return {t for t in _norm(s).split() if len(t) > 1}


def _matches(text: str, artist: str, title: str) -> bool:
    """Require that *all* artist tokens AND all title tokens appear in text."""
    ntext = _norm(text)
    a = _tokens(artist)
    t = _tokens(title)
    if not a or not t:
        return False
    return all(tok in ntext for tok in a) and all(tok in ntext for tok in t)

try:
    from duckduckgo_search import DDGS
except Exception:
    DDGS = None

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_0) AppleWebKit/605.1.15 "\
     "(KHTML, like Gecko) Version/16.0 Safari/605.1.15"


def _from_lyrics_ovh(artist: str, title: str) -> str:
    url = f"https://api.lyrics.ovh/v1/{artist}/{title}"
    try:
        r = httpx.get(url, timeout=8.0)
        if r.status_code == 200:
            data = r.json()
            lyrics = (data.get("lyrics") or "").strip()
            if lyrics and len(lyrics) > 40:
                return lyrics
    except Exception:
        pass
    return ""


def _strip_html(raw: str) -> str:
    raw = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", raw, flags=re.DOTALL | re.IGNORECASE)
    raw = re.sub(r"<br\s*/?>", "\n", raw, flags=re.IGNORECASE)
    raw = re.sub(r"</p>", "\n\n", raw, flags=re.IGNORECASE)
    raw = re.sub(r"<[^>]+>", "", raw)
    raw = html.unescape(raw)
    raw = re.sub(r"\n{3,}", "\n\n", raw)
    return raw.strip()


NAV_PHRASES = (
    "opcije", "pomoć", "pomoc", "izvođač", "izvodjac", "ime pjesme",
    "ime pesme", "tekst pjesme", "tekst pesme", "tekstova/lyrics",
    "lyrics)", "Тekstovi.net", "tekstovi.net", "prijava", "registracija",
    "copyright", "kategorije", "najnoviji",
)


def _extract_lyrics_block(text: str) -> str:
    """Pick the block that most looks like song lyrics — preferring long,
    dense blocks and rejecting navigation/listing snippets."""
    # First, try to slice text between "tekst pjesme" (or similar) markers
    # and the footer — tekstovi.net layouts usually sandwich lyrics there.
    blocks = re.split(r"\n{2,}", text)
    scored = []
    for b in blocks:
        lines = [ln.strip() for ln in b.splitlines() if ln.strip()]
        if len(lines) < 6:
            continue
        low = b.lower()
        if any(p in low for p in NAV_PHRASES):
            continue
        # Reject blocks dominated by very short lines (alphabet / nav)
        very_short = sum(1 for ln in lines if len(ln) <= 3)
        if very_short > len(lines) * 0.3:
            continue
        avg = sum(len(ln) for ln in lines) / len(lines)
        if avg < 10 or avg > 110:
            continue
        lyric_like = sum(1 for ln in lines if 6 <= len(ln) <= 120)
        if lyric_like < len(lines) * 0.7:
            continue
        # Penalize blocks that look like a list of song titles (lots of " - ")
        dashes = sum(1 for ln in lines if " - " in ln or " – " in ln)
        if dashes > len(lines) * 0.4:
            continue
        score = len(b) * 2 + lyric_like * 5
        scored.append((score, "\n".join(lines)))
    if not scored:
        print("[LYRICS] extract: no qualifying block", flush=True)
        return ""
    scored.sort(key=lambda x: x[0], reverse=True)
    best_score, best = scored[0]
    print(f"[LYRICS] extract best block score={best_score} len={len(best)} (of {len(scored)} candidates)", flush=True)
    # Require a real lyric-length block — short "blocks" are almost always
    # sidebar snippets, not a full song.
    if len(best) < 300:
        print("[LYRICS] best block too short — reject", flush=True)
        return ""
    return best


def _search_tekstovi_direct(artist: str, title: str) -> list:
    """Use tekstovi.net's own search form — no dependency on DDG."""
    candidates = []
    try:
        resp = httpx.post(
            "https://tekstovi.net/8,0,0.html",
            data={"fraza": f"{artist} {title}", "ch_izv": "on", "ch_ime": "on", "ch_tek": "on"},
            timeout=8.0,
            headers={"User-Agent": UA},
            follow_redirects=True,
        )
        print(f"[LYRICS] direct search status={resp.status_code} size={len(resp.text)}", flush=True)
        if resp.status_code != 200:
            return []
        # Song pages: href="2,<artist_id>,<song_id>.html" where song_id > 0
        for m in re.finditer(r'href="(2,\d+,[1-9]\d*\.html)"[^>]*>([^<]+(?:<[^/][^>]*>[^<]*)*)', resp.text):
            href = "https://tekstovi.net/" + m.group(1)
            link_text = re.sub(r"<[^>]+>", " ", m.group(2))
            if _matches(href + " " + link_text, artist, title):
                if href not in candidates:
                    candidates.append(href)
    except Exception as e:
        print(f"[LYRICS] direct search exception: {e!r}", flush=True)
    print(f"[LYRICS] direct search found {len(candidates)} candidates", flush=True)
    return candidates


def _scrape_tekstovi(artist: str, title: str) -> str:
    candidates = []
    if DDGS is not None:
        query = f"site:tekstovi.net {artist} {title}"
        try:
            with DDGS() as ddgs:
                results = list(ddgs.text(query, max_results=8))
                print(f"[LYRICS] DDG returned {len(results)} results for {query!r}", flush=True)
                for r in results:
                    href = r.get("href") or r.get("link") or ""
                    rtitle = r.get("title") or ""
                    rbody = r.get("body") or ""
                    print(f"[LYRICS]   href: {href} | title: {rtitle!r}", flush=True)
                    if "tekstovi.net" not in href:
                        continue
                    combined = f"{href} {rtitle} {rbody}"
                    if _matches(combined, artist, title):
                        candidates.append(href)
        except Exception as e:
            print(f"[LYRICS] DDG exception: {e!r} — falling back to direct search", flush=True)

    # Fallback: query tekstovi.net directly (works when DDG rate-limits)
    if not candidates:
        candidates = _search_tekstovi_direct(artist, title)
    if not candidates:
        print("[LYRICS] no matching tekstovi.net URL (artist+title filter)", flush=True)
        return ""
    for url in candidates:
        try:
            resp = httpx.get(url, timeout=8.0, headers={"User-Agent": UA}, follow_redirects=True)
            print(f"[LYRICS] fetched {url} status={resp.status_code} len={len(resp.text)}", flush=True)
            if resp.status_code != 200:
                continue
            # Verify the page itself references both artist and title.
            page_head = resp.text[:4000]
            head_match = re.search(r"<title[^>]*>(.*?)</title>", page_head, re.IGNORECASE | re.DOTALL)
            head_text = (head_match.group(1) if head_match else "") + " " + page_head
            if not _matches(head_text, artist, title):
                print(f"[LYRICS] page head does not reference {artist}/{title} — skip", flush=True)
                continue
            # Prefer the site's explicit lyric container: <p class="lyric">...</p>
            lm = re.search(r'<p[^>]*class="[^"]*\blyric\b[^"]*"[^>]*>(.*?)</p>',
                           resp.text, re.DOTALL | re.IGNORECASE)
            if lm:
                block = _strip_html(lm.group(1)).strip()
                print(f"[LYRICS] <p class=lyric> extracted len={len(block)}", flush=True)
                if block and len(block) > 80:
                    return f"{block}\n\nSource: {url}"
            # Fallback: heuristic block selection on full page text
            text = _strip_html(resp.text)
            block = _extract_lyrics_block(text)
            if block and len(block) > 80:
                return f"{block}\n\nSource: {url}"
        except Exception as e:
            print(f"[LYRICS] fetch exception: {e!r}", flush=True)
    return ""


def get_lyrics(artist: str, title: str) -> str:
    artist = (artist or "").strip()
    title = (title or "").strip()
    print(f"[LYRICS] request: artist={artist!r} title={title!r}", flush=True)
    if not artist or not title:
        return ""
    hit = _from_lyrics_ovh(artist, title)
    print(f"[LYRICS] lyrics.ovh: {'hit ('+str(len(hit))+' chars)' if hit else 'miss'}", flush=True)
    if hit:
        return f"{hit}\n\nSource: lyrics.ovh"
    hit = _scrape_tekstovi(artist, title)
    print(f"[LYRICS] tekstovi.net: {'hit ('+str(len(hit))+' chars)' if hit else 'miss'}", flush=True)
    if hit:
        return hit
    return ""
