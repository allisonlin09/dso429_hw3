# DSO 429 HW3 — Hourly Quiz

A GitHub Actions job (`.github/workflows/answer.yml`) runs every 15 minutes. It fetches
`questions.csv` from the quiz repo, answers every round that has no file in `answers/`
yet, and pushes `answers/round-NNNN.json`.

- `solver.py` — one formula per question type; picks the option closest to the computed value.
- `answer.py` — fetches rounds, writes answer files; `python answer.py --check practice_keys.csv`
  scores the solver against the practice keys (1200/1200 on rounds 1–48).

If a question matches no known type, the answer defaults to `A`, the question is logged
to `unsolved.log`, and the workflow run fails so GitHub sends an email. Fix the solver,
delete that round's file, and re-run the workflow within 3 hours of release.
