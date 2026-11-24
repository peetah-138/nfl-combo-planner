# Working with Pete

How Pete likes work done. `CLAUDE.md` is the rulebook; this is the short version for a fresh session.

## Talking

- Replies short, in plain English.
- Goals in order: **profit is #1, fun is #2.**
- Questions go through the AskUserQuestion tool, interview style. He is often on his phone.
- Every piece of his feedback gets its own GitHub issue.

## Git and releases

- Git Flow: branch from `develop` as `feat/`, `fix/` or `chore/`; open a PR into `develop`; squash-merge when the CI
  job `checks` is green. Never push to `main` or `develop`.
- Releases go `develop` into `main` as a merge commit (not squashed), with the version bump in all three places.
- Every change gets a test.
- Visual changes: send phone-size screenshots to Pete before any release that includes them.

## Agents

- No fixed cap on subagents on the dev Mac (the old limit of 3 was for the weaker MacBook Air). Manage by machine
  resources: CPU, RAM and ports. Give each parallel check run its own `CHECK_PORT_BASE`.
- Use Opus for money-path work.
- Never `pkill`.

## Reviews

Four on every PR: code, security, profit, delight (`docs/REVIEW_LENSES.md`). Fix every finding or file an issue
labelled `profit` or `fun`.

## Money safety (never break)

- Rule 8: an unknown buy outcome is "check" and is never retried.
- Pause is always respected.
- The Pi never trades.
- Rule 7: only price or buy the combo on screen.
- No new automatic money movement without Pete's explicit opt-in.
- Never touch the Vercel project `cynserus`.
