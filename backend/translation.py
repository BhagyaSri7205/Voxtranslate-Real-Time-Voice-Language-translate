import os
import re
import time
import threading
import requests
from deep_translator import GoogleTranslator

LANGUAGES = {
    "English": "en",
    "Telugu": "te",
    "Hindi": "hi",
    "Tamil": "ta",
    "Kannada": "kn",
    "Malayalam": "ml",
    "Bengali": "bn",
    "Marathi": "mr",
    "Gujarati": "gu",
    "Punjabi": "pa",
    "Urdu": "ur",
    "Korean": "ko",
    "Japanese": "ja",
    "Chinese": "zh-CN",
    "French": "fr",
    "German": "de",
    "Spanish": "es",
    "Russian": "ru",
    "Arabic": "ar",
    "Portuguese": "pt",
    "Italian": "it",
}

# Flag/locale icons shown next to each language name in dropdowns.
LANGUAGE_ICONS = {
    "English": "🇬🇧",
    "Telugu": "🇮🇳",
    "Hindi": "🇮🇳",
    "Tamil": "🇮🇳",
    "Kannada": "🇮🇳",
    "Malayalam": "🇮🇳",
    "Bengali": "🇮🇳",
    "Marathi": "🇮🇳",
    "Gujarati": "🇮🇳",
    "Punjabi": "🇮🇳",
    "Urdu": "🇵🇰",
    "Korean": "🇰🇷",
    "Japanese": "🇯🇵",
    "Chinese": "🇨🇳",
    "French": "🇫🇷",
    "German": "🇩🇪",
    "Spanish": "🇪🇸",
    "Russian": "🇷🇺",
    "Arabic": "🇸🇦",
    "Portuguese": "🇵🇹",
    "Italian": "🇮🇹",
}

AUTO_DETECT_LABEL = "🌐 Auto Detect (any language)"


def display_languages():
    """Returns ['🇬🇧 English', '🇮🇳 Telugu', ...] for use in dropdown widgets."""
    return [f"{LANGUAGE_ICONS[name]} {name}" for name in LANGUAGES]


def strip_icon(display_value):
    """Converts '🇮🇳 Telugu' back into 'Telugu'. Safe to call on a plain name too."""
    parts = display_value.strip().split(" ", 1)
    return parts[1].strip() if len(parts) == 2 and parts[0] in LANGUAGE_ICONS.values() else display_value.strip()


# ---------------- providers ----------------
# WHY THE "TooManyRequests" ERROR HAPPENS
# The free Google endpoint that deep-translator scrapes (and MyMemory's free
# tier) rate-limit by IP address. On shared / mobile / ISP networks that limit
# can already be used up by *other people*, so even a single click gets HTTP
# 429. Retrying the same endpoint just makes it worse.
#
# Fix: try several independent providers, remember which ones just returned
# 429 and skip them for a while, cache results, and (optionally) use a real
# Google Cloud API key which has no such limit.
#
# Optional settings (put in the .env file next to main.py):
#   GOOGLE_TRANSLATE_API_KEY=...   official Google Cloud Translation key (best)
#   MYMEMORY_EMAIL=you@example.com raises MyMemory's free quota a lot

_TIMEOUT = 10
_HEADERS = {"User-Agent": "Mozilla/5.0 (VoxTranslate)"}


class _RateLimited(Exception):
    """Provider answered HTTP 429 / quota exceeded."""


def _check(resp):
    if resp.status_code == 429:
        raise _RateLimited("HTTP 429")
    resp.raise_for_status()


def _chunks(text, limit):
    """Split text into pieces <= limit chars, preferring sentence boundaries."""
    if len(text) <= limit:
        return [text]
    parts, cur = [], ""
    for sent in re.split(r"(?<=[.!?\u0964\u3002\n])\s*", text):
        while len(sent) > limit:
            if cur:
                parts.append(cur); cur = ""
            parts.append(sent[:limit]); sent = sent[limit:]
        if len(cur) + len(sent) + 1 > limit:
            parts.append(cur); cur = sent
        else:
            cur = f"{cur} {sent}".strip()
    if cur:
        parts.append(cur)
    return parts


def _google_cloud(text, src, dst):
    key = os.getenv("GOOGLE_TRANSLATE_API_KEY", "").strip()
    if not key:
        raise RuntimeError("no GOOGLE_TRANSLATE_API_KEY set")
    data = {"q": text, "target": dst, "format": "text", "key": key}
    if src != "auto":
        data["source"] = src
    r = requests.post("https://translation.googleapis.com/language/translate/v2",
                      data=data, timeout=_TIMEOUT)
    _check(r)
    import html
    return html.unescape(r.json()["data"]["translations"][0]["translatedText"])


def _google_gtx(text, src, dst):
    """Google's public 'gtx' endpoint (different from the one deep-translator uses)."""
    out = []
    for piece in _chunks(text, 4000):
        r = requests.get(
            "https://translate.googleapis.com/translate_a/single",
            params={"client": "gtx", "sl": src, "tl": dst, "dt": "t", "q": piece},
            headers=_HEADERS, timeout=_TIMEOUT)
        _check(r)
        out.append("".join(seg[0] for seg in r.json()[0] if seg and seg[0]))
    return " ".join(out)


def _google_deeptranslator(text, src, dst):
    try:
        return GoogleTranslator(source=src, target=dst).translate(text)
    except Exception as e:
        if "TooManyRequests" in type(e).__name__ or "too many requests" in str(e).lower():
            raise _RateLimited(str(e))
        raise


def _mymemory(text, src, dst):
    email = os.getenv("MYMEMORY_EMAIL", "").strip()
    out = []
    for piece in _chunks(text, 450):  # MyMemory limit is ~500 bytes per request
        params = {"q": piece, "langpair": f"{'Autodetect' if src == 'auto' else src}|{dst}"}
        if email:
            params["de"] = email
        r = requests.get("https://api.mymemory.translated.net/get",
                         params=params, headers=_HEADERS, timeout=_TIMEOUT)
        _check(r)
        j = r.json()
        if str(j.get("responseStatus")) == "429":
            raise _RateLimited("MyMemory quota")
        out.append(j["responseData"]["translatedText"])
    return " ".join(out)


_LINGVA_HOSTS = ["https://lingva.ml", "https://lingva.thedaviddelta.com"]


def _lingva(text, src, dst):
    fix = lambda c: "zh" if c.lower().startswith("zh") else c
    last = None
    for host in _LINGVA_HOSTS:
        try:
            r = requests.get(f"{host}/api/v1/{fix(src)}/{fix(dst)}/{requests.utils.quote(text[:1500], safe='')}",
                             headers=_HEADERS, timeout=_TIMEOUT)
            _check(r)
            return r.json()["translation"]
        except Exception as e:
            last = e
    raise last


_PROVIDERS = [
    ("Google Cloud API", _google_cloud),
    ("Google", _google_gtx),
    ("Google (deep-translator)", _google_deeptranslator),
    ("MyMemory", _mymemory),
    ("Lingva", _lingva),
]

# ---------------- state: throttle, cooldowns, cache ----------------
_lock = threading.Lock()
_last_call_time = 0.0
_MIN_GAP_SECONDS = 0.3
_cooldown_until = {}          # provider name -> unix time it may be tried again
_COOLDOWN_SECONDS = 60
_cache = {}
_CACHE_MAX = 500


def _throttle():
    global _last_call_time
    with _lock:
        wait = _MIN_GAP_SECONDS - (time.time() - _last_call_time)
        if wait > 0:
            time.sleep(wait)
        _last_call_time = time.time()


# ---------------- response validation ----------------
# Some backends return an HTML error page or a warning as if it were a real
# translation. Reject those so they never reach the UI or history.
_ERROR_SIGNATURES = [
    "error 500", "error 404", "error 502", "error 503",
    "that's an error", "that\u2019s an error",
    "that's all we know", "that\u2019s all we know",
    "please try again later",
    "<html", "<!doctype",
    "query length limit exceeded",
    "invalid target language", "invalid source language",
    "amount of words limit exceeded",
    "mymemory warning", "no translation found",
    "is not supported",
    "you used all available free translations",
]


def _looks_like_error(result):
    if not result or not result.strip():
        return True
    lowered = result.lower()
    return any(sig in lowered for sig in _ERROR_SIGNATURES)


TRANSLATION_FAILURE_PREFIX = "\u26a0\ufe0f"


def _norm(t):
    return re.sub(r"\W+", "", t or "").lower()


_LATIN_TARGETS = {"en", "fr", "de", "es", "pt", "it"}


def _script_mismatch(text, target):
    """True when an unchanged result is certainly wrong (e.g. English text 'translated' into Hindi)."""
    has_latin = any(c.isascii() and c.isalpha() for c in text)
    has_other = any((not c.isascii()) and c.isalpha() for c in text)
    if target in _LATIN_TARGETS:
        return has_other and not has_latin
    return has_latin and not has_other


def is_translation_error(result):
    """True if `result` is our own failure message rather than a real translation."""
    return bool(result) and result.startswith(TRANSLATION_FAILURE_PREFIX)


def translate_text(text, source, target):
    """
    Translate `text` from `source` to `target` (language codes; source may be 'auto').
    Tries several providers in turn, skipping any that recently rate-limited us,
    and caches results. Returns the translation, or a string starting with
    TRANSLATION_FAILURE_PREFIX if every provider failed.
    """
    if not text or not text.strip():
        return ""
    if source == target:
        return text

    text = text.strip()
    key = (text, source, target)
    if key in _cache:
        return _cache[key]

    problems = []
    rate_limited = 0
    tried = 0
    unchanged = None  # a provider that just echoed the input back

    for round_no in range(2):  # a second pass gives short-lived limits time to clear
        for label, fn in _PROVIDERS:
            if time.time() < _cooldown_until.get(label, 0):
                continue
            if label == "Google Cloud API" and not os.getenv("GOOGLE_TRANSLATE_API_KEY", "").strip():
                continue
            tried += 1
            try:
                _throttle()
                result = fn(text, source, target)
                if _looks_like_error(result):
                    raise RuntimeError(f"error-like response: {str(result)[:60]!r}")
                if (source != "auto" and len(text) > 2 and any(c.isalpha() for c in text)
                        and _norm(result) == _norm(text)):
                    # Some providers echo the text back for an explicit source language.
                    # Retry this provider in auto-detect mode before trusting the echo.
                    try:
                        alt = fn(text, "auto", target)
                        if not _looks_like_error(alt) and _norm(alt) != _norm(text):
                            result = alt
                    except _RateLimited:
                        raise
                    except Exception:
                        pass
                    if _norm(result) == _norm(text):
                        unchanged = result
                        raise RuntimeError("provider returned the text unchanged")
                if len(_cache) >= _CACHE_MAX:
                    _cache.pop(next(iter(_cache)))
                _cache[key] = result
                return result
            except _RateLimited as e:
                rate_limited += 1
                _cooldown_until[label] = time.time() + _COOLDOWN_SECONDS
                problems.append(f"{label}: rate limited")
                print(f"[{label}] rate limited:", e)
            except Exception as e:
                problems.append(f"{label}: {type(e).__name__}")
                print(f"[{label}] failed:", e)
        if unchanged is not None:
            if not _script_mismatch(text, target):
                return unchanged      # plausible (e.g. a name), accept it
            break                      # impossible echo: the servers are not really translating
        if round_no == 0:
            time.sleep(1.5)

    if unchanged is not None:
        hint = ("The free translation servers returned your text unchanged (this often happens on "
                "hosting servers whose IP is limited). Set GOOGLE_TRANSLATE_API_KEY to fix it.")
    elif rate_limited > 0 and rate_limited >= len(problems) // 2:
        hint = ("The free translation servers are rate-limiting your network right now. "
                "Wait about a minute and try again, or add GOOGLE_TRANSLATE_API_KEY to .env.")
    else:
        hint = "Check your internet connection, then try again."
    detail = "; ".join(problems[-4:]) or "no provider available"
    print("Translation Error (all providers failed):", detail)
    return (f"{TRANSLATION_FAILURE_PREFIX} Translation service is temporarily unavailable.\n"
            f"Reason: {detail[:200]}\n{hint}")
