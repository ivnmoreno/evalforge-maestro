# Repository Agent Rules (`evalforge-maestro`)

## Commit Message Presentation (VS Code Source Control)

Whenever you finish making code, configuration, documentation, or specification
edits that leave uncommitted changes in this repository (unless the user asked
you to commit directly via `git`):

1. Inspect the repository's actual changes (`git status --short` / diff summary)
   and recent commit conventions (`git log`, matching `[tool.commitizen]`
   `cz_conventional_commits` in `pyproject.toml`).
2. Derive every detail strictly from directly observed files, symbols, counts,
   and verification commands run after your final edit—never fabricate
   unverified claims.
3. Always present the **complete**, Commitizen-compatible commit message
   (subject line, wrapped body bullets covering all changed areas, and a
   `Verified:` summary footer) verbatim inside a single fenced ```` ```text ````
   code block so it can be copied directly into the VS Code Source Control commit
   message box, and validate the exact message with `.venv/bin/cz check --message`
   when `.venv` is available.

## Git Branch & Commitizen CI Hygiene

- Before proposing edits or commits after a PR merge, check `git status -sb` and
  remote branch tracking (`git branch -vv`) so work is not stranded on a deleted
  or already-merged branch.
- Remember CI validates every commit in a PR range (`cz check --rev-range
  base..head` in `.github/workflows/ci.yml`), not just the top commit or PR
  title. If a branch contains a non-conventional commit, instruct/fix via
  `git commit --amend` (or interactive rebase) plus `git push --force-with-lease`
  rather than stacking a new commit on top.
