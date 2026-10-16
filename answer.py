"""Write answers/round-NNNN.json for every released round not yet answered.

Usage:
  python answer.py                 # fetch questions.csv from the quiz repo
  python answer.py questions.csv   # use a local copy
  python answer.py --check KEYS    # score practice rounds against an answer key

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
from pathlib import Path

from solver import solve

QUESTIONS_URL = "https://raw.githubusercontent.com/FaisalXL/dso429-hourly-quiz/main/questions.csv"
ANSWERS = Path(__file__).parent / "answers"
UNSOLVED_LOG = Path(__file__).parent / "unsolved.log"


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

    rounds = load_rows(args[0] if args else None)
    ANSWERS.mkdir(exist_ok=True)
    all_unsolved = []
    for rid in sorted(rounds):
        out = ANSWERS / f"round-{rid:04d}.json"
        if out.exists():
            continue
        answers, unsolved = answer_round(rounds[rid])
        out.write_text(json.dumps({"round_id": rid, "answers": answers}, indent=2) + "\n")
        print(f"wrote {out.name}" + (f" ({len(unsolved)} unsolved)" if unsolved else ""))
        all_unsolved += unsolved

    if all_unsolved:
        with UNSOLVED_LOG.open("a", encoding="utf-8") as f:
            for r in all_unsolved:
                f.write(f"round {r['round_id']} q{r['q_index']}: {r['question_text']} | "
                        f"{r['option_a']} | {r['option_b']} | {r['option_c']} | {r['option_d']}\n")
        print(f"{len(all_unsolved)} question(s) unsolved; see unsolved.log")
        sys.exit(2)


if __name__ == "__main__":
    main()
