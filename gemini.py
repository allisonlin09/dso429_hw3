"""Fallback for questions solver.py can't answer: ask Gemini (free tier).

Needs GEMINI_API_KEY in the environment (a GitHub Actions secret). Returns
None on any failure so the caller can fall back to a placeholder.
"""
import json
import os
import re
import time
import urllib.error
import urllib.request

MODELS = os.environ.get("GEMINI_MODELS", "gemini-3.8-flash,gemini-3.5-flash-lite").split(",")
URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

PROMPT = """You are answering a multiple-choice business arithmetic question.
Work it out step by step, computing exact values, then compare with the options.
Finish with a final line of the form: ANSWER: X   (X is A, B, C or D)

Question: {q}
A) {a}
B) {b}
C) {c}
D) {d}"""


def _call(model, prompt, key):
    body = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0},
    }).encode()
    req = urllib.request.Request(URL.format(model=model.strip()), data=body, method="POST",
                                 headers={"Content-Type": "application/json", "x-goog-api-key": key})
    with urllib.request.urlopen(req, timeout=120) as resp:
        data = json.load(resp)
    parts = data["candidates"][0]["content"]["parts"]
    return "".join(p.get("text", "") for p in parts)


def ask(question, options):
    """Return 'A'-'D' from Gemini, or None if unavailable."""
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        print("gemini: GEMINI_API_KEY is not set")
        return None
    prompt = PROMPT.format(q=question, a=options[0], b=options[1], c=options[2], d=options[3])
    for model in MODELS:
        for attempt in range(3):
            try:
                text = _call(model, prompt, key)
                m = re.findall(r"ANSWER:\s*\**\s*([ABCD])\b", text)
                if m:
                    return m[-1]
                break  # answered but unparseable: try the next model
            except urllib.error.HTTPError as e:
                detail = e.read().decode("utf-8", "replace")[:300].replace("\n", " ")
                print(f"gemini {model}: HTTP {e.code} {detail}")
                if e.code in (429, 500, 502, 503, 504):
                    time.sleep(10 * (attempt + 1))
                    continue
                break  # bad key / model not found: try the next model
            except Exception as e:  # network, malformed response
                print(f"gemini {model}: {type(e).__name__}: {e}")
                time.sleep(5)
    return None
