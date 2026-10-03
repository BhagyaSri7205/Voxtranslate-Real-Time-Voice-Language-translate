"""Run:  python check_translation.py   -> shows which translation service works on YOUR network."""
import sys
from backend import translation as T

TESTS = [("Hello, how are you?", "en", "hi"), ("अब कैसे है?", "hi", "en"),
         ("Good morning", "auto", "te"), ("beautiful", "en", "ta")]
print("\n=== each provider ===")
for label, fn in T._PROVIDERS:
    if label == "Google Cloud API":
        continue
    for text, src, dst in TESTS:
        try:
            print(f"[{label}] {src}->{dst}: {text!r} => {fn(text, src, dst)!r}")
        except Exception as e:
            print(f"[{label}] {src}->{dst}: FAILED ({type(e).__name__}: {str(e)[:80]})")
print("\n=== final app result (what the website shows) ===")
for text, src, dst in TESTS:
    print(f"{src}->{dst}: {text!r} => {T.translate_text(text, src, dst)!r}")
