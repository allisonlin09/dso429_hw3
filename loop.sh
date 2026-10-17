#!/usr/bin/env bash
# Answer new rounds every INTERVAL seconds for LOOP_MINUTES minutes.
# GitHub's cron only fires every few hours on this repo, so one long run
# does the polling and the workflow restarts itself when this exits.
set -u
end=$(( $(date +%s) + ${LOOP_MINUTES:-320} * 60 ))
git config user.name "github-actions[bot]"
git config user.email "41898733+github-actions[bot]@users.noreply.github.com"

while :; do
  echo "== $(date -u +%H:%M:%S) check"
  git pull --rebase -q || git rebase --abort  # picks up any solver fixes you push

  python answer.py || echo "answer.py exited $? (placeholders or fetch error)"

  git add answers
  for f in unsolved.log llm_answers.json; do [ -f "$f" ] && git add "$f"; done
  if ! git diff --cached --quiet; then
    rounds=$(git diff --cached --name-only answers | sed -E 's/.*round-0*([0-9]+).*/\1/' | paste -sd, -)
    git commit -q -m "Answer rounds $rounds"
  fi
  # Push whenever we're ahead, so a failed push is retried next check.
  if [ -n "$(git log origin/main..HEAD --oneline)" ]; then
    git pull --rebase -q && git push -q && echo "pushed" || echo "push failed; retrying next check"
  fi

  if [ -f alert.md ]; then
    gh issue create --title "${TITLE_PREFIX:-}New question type found - see status inside" \
      --body-file alert.md && rm alert.md
  fi

  [ "$(date +%s)" -ge "$end" ] && break
  sleep "${INTERVAL:-180}"
done
