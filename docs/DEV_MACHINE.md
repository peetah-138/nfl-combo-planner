# The dev machine

Public-safe notes on how development is set up. Since 2026-11-23 (Pete) the dev Mac owns ALL building, testing,
subagents, merging and releasing (see `CLAUDE.md`). Pete's MacBook Air is production only.

## What lives where

- **Dev Mac:** the git clone, tests, linting, subagents, PRs, releases. It never holds Pete's Kalshi key,
  `~/combowatch`, the history database or any `combo_*.json`. It never runs the watcher and never places orders.
- **MacBook Air (production):** trades real money, runs the watcher and web app, auto-updates from `main` within
  about 10 minutes. Nothing is built, tested or merged there.

## Setup

- **Clone:** `~/dev/nfl-combo-planner`. Keep it under `~/dev`, not iCloud Drive, Desktop or Documents (sync and
  permission prompts break git and the test runs).
- **Python:** 3.13 in a git-ignored venv at `.venv-tests`. `tests/python_env.sh` builds it on first use and
  `bash tests/run_checks.sh` sources it; you rarely need to touch it.
- **Lint:** `.venv-tests/bin/ruff check .` (or `ruff check .` if ruff is on PATH).
- **GitHub:** `gh auth login` once; `gh auth status` should show the repo owner's account.
- **One-time per clone:** `git config rerere.enabled true`.
- **Worktrees:** one per branch, under `~/dev/wt`:
  `git worktree add ~/dev/wt/<name> -b <feat|fix|chore>/<name> develop`. Remove them after the PR merges.

## Running the checks

```
ruff check .
bash tests/run_checks.sh
```

Both must pass before a PR (CI job `checks` runs the same). When several agents or worktrees run checks at once,
give each its own port range so they do not collide, e.g. `CHECK_PORT_BASE=19100 bash tests/run_checks.sh`
(next lane: 19200, and so on). Never use the real app's ports 8765/8766.

## Hard rules

- Never run the watcher or place orders from this machine. Dev and test default is no live buying.
- Never commit keys, key IDs, ntfy topics, emails, settings, history or session files. The repo is public.
- Never push to `main` or `develop`; branch from `develop`, PR into `develop`.
- A **pre-commit secret-guard hook** lives in this clone's `.git/hooks/` and is local only (not tracked). It
  refuses commits containing known secret strings. The strings it blocks are never written into any tracked file,
  including this one.
- Never touch the Vercel project `cynserus`.
