# docs/changes: one file per PR instead of editing CLAUDE.md and ROADMAP.md

`CLAUDE.md` and `ROADMAP.md` were edited by almost every PR, so parallel PRs conflicted on them every time. Now:

- **A feature, fix or chore PR adds ONE new file here: `docs/changes/<issue-number-or-short-slug>.md`**
  (e.g. `docs/changes/143-money-safety.md`, `docs/changes/spreads-totals-b.md`), and does **not** edit `CLAUDE.md` or
  `ROADMAP.md`. A new file never conflicts with anyone else's.
- **Only a rule or decision change edits `CLAUDE.md` directly** (a hard rule, the Git workflow, Pete's standing
  decisions, how work is done). Say so in the PR description. These are rare; a product change is not one.
- **The release owner folds the files into `CLAUDE.md` / `ROADMAP.md` during the release** (into the matching product
  section, in the same style) and deletes them in the same PR, then back-merges as usual. Until a file is folded, it
  is the truth for what it describes: `CLAUDE.md` plus the files in this folder is the whole brief.
- Do not put anything here that must never be committed (keys, key IDs, topics, emails, settings, history). The repo
  is public.

## Template

Copy this into `docs/changes/<issue-or-slug>.md` and delete what does not apply. Write it the way `CLAUDE.md`'s product
sections are written: plain, specific, with the function and setting names, the numbers and the reason for them,
what is isolated from the money paths, and the tests.

```markdown
# <Short title> (issue #N)

**Section:** <where it belongs in CLAUDE.md: e.g. "Fair prices and data", "Selling", "Live page", "Build page", "Results page">

<What shipped / what changed in the product. Behaviour first, then the names (`function`, `setting`, table, file),
the numbers and thresholds, what it never touches (Pause, caps, rule 8, selling...), and the tests that cover it
(`t_name.py`, `test_name.py`).>

ROADMAP: <removes "<item name>" | adds "<item name>: what it waits on, what comes next" | none>
```

- One `ROADMAP:` line per roadmap item added or removed (a PR may have several); `ROADMAP: none` if it touches nothing.
- If two PRs describe the same area, that is fine: the release owner merges the paragraphs.
- The release owner deletes the folded files; this README stays.
