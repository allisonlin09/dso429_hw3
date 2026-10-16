# DSO 429 HW3 — Hourly Quiz

A GitHub Actions job (`.github/workflows/answer.yml`) runs every 15 minutes. It fetches
`questions.csv` from the quiz repo, answers every round that has no file in `answers/`
yet, and pushes `answers/round-NNNN.json`.

- `solver.py` — one formula per question type; picks the option closest to the computed value.
- `answer.py` — fetches rounds, writes answer files; `python answer.py --check practice_keys.csv`
  scores the solver against the practice keys (1200/1200 on rounds 1–48).

- `gemini.py` � fallback for questions `solver.py` can't answer: asks Gemini (free tier, key in the
  `GEMINI_API_KEY` repo secret). Answers are cached in `llm_answers.json`.

Rounds still within 3 hours of release are re-answered on every run, so a solver fix (or a Gemini
retry after a failed call) reaches them automatically.

If a question matches no known type, the workflow opens a GitHub issue that @mentions you with the
question and Gemini's answer. If Gemini also failed, the answer is `A`, the run fails (GitHub emails
you), and later runs keep retrying while the round is open.

Test the Gemini key: push a commit whose message contains `[test-gemini]`.
