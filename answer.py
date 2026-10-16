"""Write answers/round-NNNN.json for every released round not yet answered.

Usage:
  python answer.py                 # fetch questions.csv from the quiz repo
  python answer.py questions.csv   # use a local copy
  python answer.py --check KEYS    # score practice rounds against an answer key
  python answer.py --unsolved      # list released questions the solver can't answer

  python answer.py --test-llm KEYS # ask Gemini 5 practice questions (checks GEMINI_API_KEY)

Questions solver.py can't answer go to Gemini (gemini.py, free tier); its
answers are cached in llm_answers.json. Rounds still within 3 hours of
release are re-answered on every run, so a solver fix or a Gemini retry
reaches them automatically.

Exits with code 2 if any question was left as a placeholder, so the GitHub
Actions run shows as failed (and GitHub emails you) while still pushing
best-guess answers.
"""
import csv
import io
import json
import sys
import urllib.request
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

import gemini
from solver import solve

QUESTIONS_URL = "https://raw.githubusercontent.com/FaisalXL/dso429-hourly-quiz/main/questions.csv"
ANSWERS = Path(__file__).parent / "answers"
UNSOLVED_LOG = Path(__file__).parent / "unsolved.log"
ALERT = Path(__file__).parent / "alert.md"
LLM_CACHE = Path(__file__).parent / "llm_answers.json"


def load_rows(src):
    if src:
        text = Path(src).read_text(encoding="utf-8")
    else:
        req = urllib.request.Request(QUESTIONS_URL, headers={"Cache-Control": "no-cache"})
        text = urllib.request.urlopen(req, timeout=60).read().decode("utf-8")
    rounds = defaultdict(list)
    for r in csv.DictReader(io.StringIO(text)):
        rounds[int(r["round_id"])].append(r)
    return rounds


def released(rows):
    return datetime.fromisoformat(rows[0]["released_at"].replace("Z", "+00:00"))


def still_open(rows):
    """True while a re-push still replaces the graded version (3 hours after release)."""
    return datetime.now(timezone.utc) < released(rows) + timedelta(hours=3)


def list_unsolved(rounds):
    """Print every released question the solver can't answer; return how many."""
    n = 0
    for rid in sorted(rounds):
        for r in rounds[rid]:
            letter, _ = solve(r["question_text"], [r["option_a"], r["option_b"], r["option_c"], r["option_d"]])
            if letter is None:
                n += 1
                print(f"round {rid} q{r['q_index']}: {r['question_text']}")
    print(f"{n} unsolved")
    return n


def load_cache():
    return json.loads(LLM_CACHE.read_text()) if LLM_CACHE.exists() else {}


def answer_round(rows, cache):
    """Return (answers, unsolved). Unsolved rows get an 'llm' key: Gemini's letter or None."""
    answers, unsolved = {}, []
    for r in sorted(rows, key=lambda r: int(r["q_index"])):
        opts = [r["option_a"], r["option_b"], r["option_c"], r["option_d"]]
        letter, _ = solve(r["question_text"], opts)
        if letter is None:
            key = f"{r['round_id']}-{r['q_index']}"
            if key not in cache:
                guess = gemini.ask(r["question_text"], opts)
                if guess:
                    cache[key] = guess
            r = dict(r, llm=cache.get(key))
            unsolved.append(r)
            letter = r["llm"] or "A"  # placeholder if Gemini is unavailable
        answers[f"q{int(r['q_index'])}"] = letter
    return answers, unsolved


def check(rounds, keys_path):
    keys = {(int(k["round_id"]), int(k["q_index"])): k["answer"]
            for k in csv.DictReader(open(keys_path, encoding="utf-8"))}
    right = total = 0
    for rid, rows in rounds.items():
        for r in rows:
            k = (rid, int(r["q_index"]))
            if k not in keys:
                continue
            letter, name = solve(r["question_text"], [r["option_a"], r["option_b"], r["option_c"], r["option_d"]])
            total += 1
            if letter == keys[k]:
                right += 1
            else:
                print(f"MISS r{rid} q{k[1]} [{name}] got {letter} want {keys[k]}: {r['question_text']}")
    print(f"{right}/{total} correct")
    return right == total


def main():
    args = sys.argv[1:]
    if args[:1] == ["--check"]:
        sys.exit(0 if check(load_rows(args[2] if len(args) > 2 else None), args[1]) else 1)
    if args[:1] == ["--unsolved"]:
        sys.exit(1 if list_unsolved(load_rows(args[1] if len(args) > 1 else None)) else 0)

    if args[:1] == ["--test-llm"]:
        sys.exit(test_llm(load_rows(args[2] if len(args) > 2 else None), args[1]))

    rounds = load_rows(args[0] if args else None)
    ANSWERS.mkdir(exist_ok=True)
    cache = load_cache()
    new_unsolved = []
    for rid in sorted(rounds):
        out = ANSWERS / f"round-{rid:04d}.json"
        if out.exists() and not still_open(rounds[rid]):
            continue  # locked: re-pushing can't change the grade
        answers, unsolved = answer_round(rounds[rid], cache)
        content = json.dumps({"round_id": rid, "answers": answers}, indent=2) + "\n"
        if not out.exists():
            out.write_text(content)
            print(f"wrote {out.name}" + (f" ({len(unsolved)} unsolved)" if unsolved else ""))
            new_unsolved += unsolved
        elif out.read_text() != content:
            # Solver fixed or Gemini answered a retry; re-push while the round is still editable.
            out.write_text(content)
            print(f"updated {out.name}")
    if cache:
        LLM_CACHE.write_text(json.dumps(cache, indent=2, sort_keys=True) + "\n")

    if new_unsolved:
        with UNSOLVED_LOG.open("a", encoding="utf-8") as f:
            for r in new_unsolved:
                f.write(f"round {r['round_id']} q{r['q_index']} (gemini: {r['llm'] or 'none'}): "
                        f"{r['question_text']} | {r['option_a']} | {r['option_b']} | "
                        f"{r['option_c']} | {r['option_d']}\n")
        write_alert(new_unsolved)
        missing = sum(1 for r in new_unsolved if not r["llm"])
        print(f"{len(new_unsolved)} question(s) not handled by solver.py; "
              f"Gemini answered {len(new_unsolved) - missing}; see unsolved.log")
        if missing:
            sys.exit(2)  # placeholders submitted: fail the run so GitHub emails you


def test_llm(rounds, keys_path, n=5):
    """Ask Gemini a few practice questions and compare with the key (checks the API key works)."""
    keys = {(int(k["round_id"]), int(k["q_index"])): k["answer"]
            for k in csv.DictReader(open(keys_path, encoding="utf-8"))}
    sample = [r for rid in sorted(rounds)[:1] for r in rounds[rid]][:n]
    right = 0
    for r in sample:
        got = gemini.ask(r["question_text"], [r["option_a"], r["option_b"], r["option_c"], r["option_d"]])
        want = keys[(int(r["round_id"]), int(r["q_index"]))]
        right += got == want
        print(f"r{r['round_id']} q{r['q_index']}: gemini={got} key={want}")
    print(f"gemini {right}/{len(sample)} correct")
    return 0 if right >= len(sample) - 1 else 1


def write_alert(unsolved):
    """Write alert.md, the body of the GitHub issue the workflow opens."""
    try:
        from zoneinfo import ZoneInfo
        tz, tzname = ZoneInfo("America/Los_Angeles"), "Pacific"
    except Exception:
        tz, tzname = timezone.utc, "UTC"
    rounds = sorted({int(r["round_id"]) for r in unsolved})
    missing = sum(1 for r in unsolved if not r.get("llm"))
    status = ("Gemini answered all of them, so nothing is required from you; check its answers if you like."
              if not missing else
              f"Gemini could not answer {missing}; those were submitted as `A` and will be retried "
              "every 15 minutes while the round is open.")
    lines = [f"@allisonlin09 solver.py has no formula for {len(unsolved)} new question(s). {status}", ""]
    for rid in rounds:
        rel = next(r["released_at"] for r in unsolved if int(r["round_id"]) == rid)
        deadline = datetime.fromisoformat(rel.replace("Z", "+00:00")) + timedelta(hours=3)
        lines.append(f"**Round {rid}**: answers can change until **{deadline.astimezone(tz):%a %b %d, %I:%M %p} {tzname}** "
                     "(submissions lock 3 hours after release).")
    lines += ["", "| Round | Q | Question | A | B | C | D | Gemini |", "|---|---|---|---|---|---|---|---|"]
    for r in unsolved:
        cells = [r["round_id"], r["q_index"], r["question_text"],
                 r["option_a"], r["option_b"], r["option_c"], r["option_d"], r.get("llm") or "none (A)"]
        lines.append("| " + " | ".join(str(c).replace("|", "\\|") for c in cells) + " |")
    lines += ["", "### Optional: add a formula from your phone",
              "Formulas are more reliable than Gemini for future rounds. "
              "Paste this into Claude Code (claude.ai/code, on this repo):", "",
              "```",
              "New question type(s) in the table in this issue aren't handled by solver.py. "
              "Add a solver for each, confirm `python answer.py --check practice_keys.csv` still scores 1200/1200 "
              "(download practice_keys.csv from FaisalXL/dso429-hourly-quiz), and push to main. "
              "The workflow re-answers rounds still within 3 hours of release on its own.",
              "```"]
    ALERT.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
