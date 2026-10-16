"""Write answers/round-NNNN.json for every released round not yet answered.

Usage:
  python answer.py                 # fetch questions.csv from the quiz repo
  python answer.py questions.csv   # use a local copy
  python answer.py --check KEYS    # score practice rounds against an answer key
  python answer.py --unsolved      # list released questions the solver can't answer

Rounds still within 3 hours of release are re-answered on every run, so a
solver fix reaches them automatically.

Exits with code 2 if any question could not be solved, so the GitHub
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

from solver import solve

QUESTIONS_URL = "https://raw.githubusercontent.com/FaisalXL/dso429-hourly-quiz/main/questions.csv"
ANSWERS = Path(__file__).parent / "answers"
UNSOLVED_LOG = Path(__file__).parent / "unsolved.log"
ALERT = Path(__file__).parent / "alert.md"


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


def answer_round(rows):
    answers, unsolved = {}, []
    for r in sorted(rows, key=lambda r: int(r["q_index"])):
        opts = [r["option_a"], r["option_b"], r["option_c"], r["option_d"]]
        letter, _ = solve(r["question_text"], opts)
        if letter is None:
            unsolved.append(r)
            letter = "A"  # placeholder guess; fix within 3 hours of release
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

    rounds = load_rows(args[0] if args else None)
    ANSWERS.mkdir(exist_ok=True)
    all_unsolved = []
    for rid in sorted(rounds):
        out = ANSWERS / f"round-{rid:04d}.json"
        answers, unsolved = answer_round(rounds[rid])
        content = json.dumps({"round_id": rid, "answers": answers}, indent=2) + "\n"
        if not out.exists():
            out.write_text(content)
            print(f"wrote {out.name}" + (f" ({len(unsolved)} unsolved)" if unsolved else ""))
            all_unsolved += unsolved
        elif still_open(rounds[rid]) and out.read_text() != content:
            # The solver changed (e.g. an auto-fix); re-push while the round is still editable.
            out.write_text(content)
            print(f"updated {out.name}")

    if all_unsolved:
        with UNSOLVED_LOG.open("a", encoding="utf-8") as f:
            for r in all_unsolved:
                f.write(f"round {r['round_id']} q{r['q_index']}: {r['question_text']} | "
                        f"{r['option_a']} | {r['option_b']} | {r['option_c']} | {r['option_d']}\n")
        write_alert(all_unsolved)
        print(f"{len(all_unsolved)} question(s) unsolved; see unsolved.log")
        sys.exit(2)


def write_alert(unsolved):
    """Write alert.md, the body of the GitHub issue the workflow opens."""
    try:
        from zoneinfo import ZoneInfo
        tz, tzname = ZoneInfo("America/Los_Angeles"), "Pacific"
    except Exception:
        tz, tzname = timezone.utc, "UTC"
    rounds = sorted({int(r["round_id"]) for r in unsolved})
    lines = [f"@allisonlin09 the solver could not answer {len(unsolved)} question(s). "
             "Each was submitted as `A` as a placeholder.", ""]
    for rid in rounds:
        rel = next(r["released_at"] for r in unsolved if int(r["round_id"]) == rid)
        deadline = datetime.fromisoformat(rel.replace("Z", "+00:00")) + timedelta(hours=3)
        lines.append(f"**Round {rid}**: fix and re-push by **{deadline.astimezone(tz):%a %b %d, %I:%M %p} {tzname}** "
                     "for full credit (submissions lock 3 hours after release).")
    lines += ["", "| Round | Q | Question | A | B | C | D |", "|---|---|---|---|---|---|---|"]
    for r in unsolved:
        cells = [r["round_id"], r["q_index"], r["question_text"],
                 r["option_a"], r["option_b"], r["option_c"], r["option_d"]]
        lines.append("| " + " | ".join(str(c).replace("|", "\\|") for c in cells) + " |")
    lines += ["", "### Fix from your phone", "Paste this into Claude Code (claude.ai/code, on this repo):", "",
              "```",
              "New question type(s) in the table in this issue aren't handled by solver.py. "
              "Add a solver for each, confirm `python answer.py --check practice_keys.csv` still scores 1200/1200 "
              "(download practice_keys.csv from FaisalXL/dso429-hourly-quiz), and push to main. "
              "The workflow re-answers rounds still within 3 hours of release on its own.",
              "```"]
    ALERT.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
