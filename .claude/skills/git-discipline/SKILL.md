---
name: git-discipline
description: "Mandatory git workflow: Conventional Commits, atomic commits, and strictly linear history via feature branches that rebase onto the default branch and integrate with --ff-only. Use whenever committing, staging, branching, merging, rebasing, or preparing a PR — including bare requests like \"commit\", \"commit this\", or \"merge my branch\"."
---

# Git discipline

Three non-negotiables. They apply to every change, including one-line fixes.

1. **Conventional Commits** — every message follows the spec.
2. **Atomic commits** — one logical change per commit, each independently valid.
3. **Linear history** — work on a feature branch, rebase onto the default branch
   when behind, integrate with `git merge --ff-only`. No merge commits on the
   default branch, ever.

## The default branch

Everything below refers to the repo's **default branch** — never a hardcoded name.
It may be `main`, `master`, `trunk`, `develop`, or anything else, and a
long-lived integration branch (`develop`) may or may not be the same ref. Detect
it; do not assume:

```bash
DEFAULT="$(git symbolic-ref --short refs/remotes/origin/HEAD 2>/dev/null | sed 's|^origin/||')"
[ -n "$DEFAULT" ] || DEFAULT="$(git rev-parse --abbrev-ref HEAD)"
```

Capture into a variable and test it; `symbolic-ref ... | sed || fallback` silently
yields an empty string, because the pipe's exit status is `sed`'s success, not
`symbolic-ref`'s failure.

Notes on the fallback chain:

- `refs/remotes/origin/HEAD` is authoritative but is only set by `git clone`, so it
  is often missing in a repo created with `git init`. Refresh it with
  `git remote set-head origin --auto`.
- `gh repo view --json defaultBranchRef -q .defaultBranchRef.name` is authoritative
  for GitHub remotes.
- `init.defaultBranch` describes what *new* repos get, not what this repo uses.
  Do not rely on it.
- With no remote, the currently checked-out branch is the best available answer.

If the repo distinguishes a release branch from an integration branch, feature work
targets the **integration** branch; ask which it is rather than guessing.

Below, `<default>` means that detected name.

## 1. Conventional Commits

```
<type>(<optional scope>): <description>

<optional body>

<optional footer>
```

| Type | Use for |
|---|---|
| `feat` | new capability |
| `fix` | bug fix |
| `docs` | documentation only |
| `refactor` | restructuring with no behavior change |
| `perf` | performance |
| `test` | tests only |
| `build` | build system, dependencies, Docker |
| `ci` | CI config |
| `chore` | maintenance that fits nothing above |
| `revert` | reverts a previous commit |

Rules:

- Imperative mood, lowercase, no trailing period: `add`, not `added` or `Adds`.
- Description under 72 characters. If it will not fit, the commit is probably not
  atomic — split it.
- Scope is the affected area. Optional, but include it when the change is localized.
- Breaking changes: `feat!:` / `feat(api)!:`, **and** a `BREAKING CHANGE: <what
  broke and what to do>` footer.
- The body explains **why**, not what — the diff already shows what. Skip the body
  when the subject is self-evident.
- Reference issues in the footer: `Closes #123`, `Refs #456`.

Never write a message that describes the process instead of the change ("address
review comments", "fix tests", "wip"). Describe the resulting state.

## 2. Atomic commits

One commit = one reviewable, revertable idea. A commit that needs "and" in its
description is two commits.

Split these apart:

- a fix and the refactor that made it easy
- a feature and the formatting churn it dragged along
- production code and unrelated dependency bumps
- behavior changes and pure renames

Work the staging area rather than committing everything present:

```bash
git status --porcelain          # see everything, including untracked
git diff                        # unstaged
git diff --cached               # what would actually be committed
git add <specific paths>        # never `git add -A` when the tree is mixed
git add -p <path>               # split changes inside one file
```

Before each commit, confirm the staged set is exactly one idea and that the project
is still sound at that point — run the repo's linter and whatever tests cover the
change. A commit that leaves the default branch broken is not atomic, it is a
bisect landmine.

Review before committing, and never stage secrets (`.env`, credentials, keys,
tokens). If a file's contents are unclear, read it before staging.

## 3. Linear history

The default branch's history must read as a straight line of the exact commits that
were reviewed. `--ff-only` is what guarantees that: it moves the branch pointer to
the feature tip, so **the feature branch's commit SHAs become the default branch's
SHAs, unchanged**. A regular merge would instead add a merge commit and preserve a
fork; a squash would replace your reviewed commits with one new SHA. Both are
forbidden here.

### Start work

```bash
git switch "$DEFAULT"
git pull --ff-only                       # skip when there is no remote
git switch -c <type>/<short-slug>        # e.g. feat/expert-remove, fix/stale-stamp
```

Never commit directly to the default branch.

### Stay current

When the default branch has advanced while you worked, rebase — do not merge it
into your branch, as that creates the fork you are trying to avoid.

```bash
git fetch                                     # when a remote exists
git rev-list --count "HEAD..$DEFAULT"         # how far behind; 0 = current
git rebase "$DEFAULT"
```

Rebase only branches that are yours and unshared. If a branch has been pushed and
someone else may have it, stop and ask before rewriting it.

On conflict: resolve it. `git rebase --abort` returns you to safety if you need to
regroup; never resolve by discarding the other side wholesale.

### Integrate

```bash
git switch "$DEFAULT"
git merge --ff-only <branch>
```

If `--ff-only` fails, that is the check working: the default branch moved and your
branch is behind. Go back, rebase, retry. Do not reach for a plain `git merge` or
`--no-ff` to force it through.

Verify the SHAs carried over, then delete the branch:

```bash
git log --oneline --graph -5             # must be a single line, no forks
git branch -d <branch>
```

## Safety

- Never force-push the default branch. Never `git push --force`; if a rewritten
  branch must be updated, use `--force-with-lease`, and only for your own unshared
  branch.
- Never `git reset --hard`, `git checkout .`, or `git clean -f` without first
  running `git status` and stashing (`git stash -u`) anything present.
- Never `--no-verify`. If a hook fails, fix the cause.
- A failed hook means **no commit was created** — fix, re-stage, and make a new
  commit. Do not `--amend`, which would rewrite the *previous* commit.
- Prefer new commits over `--amend` generally; amend only an unpushed commit you
  just made, and only to correct its message or complete the same single idea.
- Never modify git config as part of a task.
