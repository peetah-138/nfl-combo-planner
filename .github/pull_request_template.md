## What this changes (plain English)

<!-- A few lines: what changed and why. "Closes #N" if it fixes an issue. -->

## Checklist

- [ ] Tests added (see `tests/README.md`; a new test is one new file with a `# CHECK:` header, no shared list)
- [ ] `CLAUDE.md` and `ROADMAP.md` NOT edited: this PR adds one `docs/changes/<issue-or-slug>.md` instead (template in `docs/changes/README.md`, with a `ROADMAP:` line). Only a rule/decision change edits `CLAUDE.md`; if so, say so above.
- [ ] `ruff check .` and `bash tests/run_checks.sh` green
- [ ] Code review done, findings fixed
- [ ] Security review done, findings fixed (no secrets in the diff; the repo is public)
- [ ] PROFIT review done (`docs/REVIEW_LENSES.md`). One line on the profit impact and the Smart Buy / Smart Sell link:
- [ ] DELIGHT review done (`docs/REVIEW_LENSES.md`). One line on haptics, motion and empty states:
- [ ] No new automatic money movement (or Pete opted in; Pause still respected)
- [ ] Screenshots or a short clip for visual changes
- [ ] Version NOT bumped (only release PRs bump it)
