---
name: git-commit
description: Generate a Conventional Commits message based on the current diff, then run verify and create the commit.
---

# Git Commit (Conventional Commits)

When the human says "commit" / "make a commit" / "git commit" / "let's commit this":

Generate a proper Conventional Commits message based on what's actually staged, run pre-commit verification, then create the commit.

## Workflow

### Step 0 — Branch awareness

**Before** writing any commit message, check where you are AND what other branches exist:

```sh
git branch --show-current        # current branch
git status --short --branch      # ahead/behind state + dirty files
git branch -vv                   # all local branches + tracking info
git branch -r                    # remote branches (catches "the work I want is on a branch I forgot about")
```

The human prefers **reusing existing branches** when scope matches — avoid creating new branches unless none fit.

Decision tree:

```
Are you on main / master?
├── YES → STOP. Do NOT commit on main. Do this in order:
│        1. Inspect the change about to be committed (its type/scope).
│        2. Scan existing branches — does one match this work?
│           Match signals: branch name resembles the change's scope,
│           the branch's recent commits are on the same files, the
│           human mentioned working on it earlier.
│        3. If a match exists → propose switching to that branch:
│             "There's an existing `<branch>` that looks like the right
│              home for this. Switch to it instead of creating a new one?"
│        4. If no match exists → propose creating a new branch:
│             "No existing branch matches. Create `<type>/<short-name>`?"
│        5. Wait for the human's choice. Do not switch / create
│           automatically.
│
└── NO → Are you on the right branch for this change?
    ├── YES → Continue to Step 1
    │
    ├── Branch name doesn't match the change you're about to commit
    │   → Ask the human: "This change looks like <type>(<scope>) but the
    │      branch is `<other-branch>`. Reuse this branch as a fixup, or
    │      switch to / create another one?"
    │
    └── Detached HEAD / weird state
        → Surface to the human, don't guess.
```

**If the human picks an existing branch**: `git switch <branch>`. The uncommitted changes follow naturally as long as they don't conflict with that branch's working tree.

**If the human confirms a new branch:** see [branches.md](branches.md) for naming rules and creation commands. Default pattern: `<type>/<short-descriptive-name>` (e.g., `feat/check-due-loans-use-case`, `fix/borrow-race-condition`).

After branch is in the right state, continue to Step 1.

### Step 1 — Inspect the change

Run **in parallel**:

```sh
git status                # what's staged vs unstaged
git diff --staged         # what will go into the commit
git log --oneline -5      # check existing commit style for consistency
```

If **nothing is staged**, ask the human:
- "Should I stage everything (`git add .`) or only specific files?"
- Never run `git add -A` or `git add .` without asking — accidental commit of `.env`, secrets, or large binaries is a real risk.

If unstaged changes exist alongside staged ones, mention this — the human may want to include them.

### Step 2 — Determine `<type>` and `<scope>`

**Types** (lowercase, exactly one):

| Type | Use when | SemVer impact |
|---|---|---|
| `feat` | New user-visible functionality | minor |
| `fix` | Bug fix | patch |
| `refactor` | Internal rework, no behaviour change | – |
| `perf` | Performance improvement | patch |
| `docs` | Documentation only (README, docstrings, comments) | – |
| `test` | Adding/fixing tests, no production change | – |
| `build` | Build system, dependencies (`pyproject.toml`, lockfiles) | – |
| `ci` | CI configs (`.github/workflows/`) | – |
| `chore` | Maintenance not fitting elsewhere (gitignore, formatting tools) | – |
| `style` | Whitespace, formatting (rare — usually folded into other commits) | – |
| `revert` | Revert a previous commit | depends |

**Scopes for this project** (use one, matching the slice that owns the change):

- `book`, `member`, `loan`, `auth`, `notification` — bounded-context slices
- `shared` — cross-cutting (config, logging, clock, password hasher, cache, composition root)
- `api` — when the change spans HTTP-layer concerns across slices
- `deps` — when the change is purely dependency bumps
- `docker` — Dockerfile / docker-compose changes
- `ci` — when CI is the *scope*, not the type (rare — usually `ci:` without scope is enough)

**Without scope** is fine for cross-cutting changes (`chore: bump python to 3.13`).

### Step 3 — Write `<subject>`

Rules (non-negotiable):

1. **Imperative mood** — "Add X" / "Fix Y" / "Refactor Z". Test: "If applied, this commit will **___**".
2. **≤ 50 characters** (subject only, not counting `<type>(<scope>): ` prefix)
3. **Lowercase first letter** after `: ` (Conventional Commits style)
4. **No period at the end**
5. **No vague verbs** — never `update`, `change`, `improve`, `tweak` alone. Be specific.

| ❌ Bad | ✅ Good |
|---|---|
| `feat: update` | `feat(book): add availability check on borrow` |
| `fix: bug` | `fix(loan): prevent double-borrow on concurrent requests` |
| `chore: stuff` | `chore(deps): bump pydantic to 2.13.4` |
| `feat(loan): Added the ability to return books.` | `feat(loan): add return-book use case` |

### Step 4 — Write `<body>` (optional, keep it laconic)

Body covers the *why*; the diff shows *what*. **Default ceiling: 6 lines.** A commit that genuinely needs more is usually a commit that should be split.

Rules:

- **Blank line between subject and body**
- **Wrap lines at 72 characters**
- **Explain WHY, not WHAT** — the diff already shows what
- **One short paragraph or 2-3 bullets** — not a per-file change list, not a restating of the subject, not a long preamble

Earns body lines: bug root cause, non-obvious tradeoff, architectural rationale, breaking-change explanation, why the chosen approach beat the obvious alternative.

Does NOT earn body lines: a bullet per file (the diff shows files), "this commit does X" (subject already said that), per-section breakdowns of mechanical edits, narrating what the next session might think.

| ❌ Too long | ✅ Laconic |
|---|---|
| 30-line bullet list per file touched | 4-line paragraph: why + key tradeoff |
| "This commit adds X. X does Y. The motivation is Z…" | "Add X — needed for Y because Z" |
| Restating the subject in the first body line | Skip; jump to the why |

If you genuinely have multiple independent points (rare), 2-3 short groupings are fine. If you're past ~10 lines, ask whether the commit should be split (see "Atomic commits" below).

**When to skip the body entirely:** trivial deps bumps, mechanical renames, self-explanatory docs fixes, format-only chores. Subject alone is enough.

### Step 5 — Footers

#### Breaking changes

Mark with `!` after scope **and** explain in footer:

```
feat(auth)!: replace JWT access tokens with opaque sessions

BREAKING CHANGE: Bearer tokens are now opaque session IDs, not
JWTs. Clients that decoded the JWT payload locally must instead
call GET /auth/me to fetch claims.
```

#### Issue references

```
fix(loan): handle returns of already-returned books

Closes #42
Refs #38
```

#### Co-author (when AI helped)

**Always** add when Claude generated substantive code/text in the change:

```
Co-Authored-By: Claude <noreply@anthropic.com>
```

### Step 6 — Run `/verify` before committing

Before writing the commit:

```sh
pytest -W error
ruff check library tests
mypy library tests
```

All three must pass. If any fails, **do not commit** — fix the failure first. Never use `--no-verify` to skip hooks.

(For a slower task with more time, run the full `/verify` skill: pytest + ruff + mypy + codespell + pip-audit + pip-licenses.)

### Step 7 — Compose the message and commit

`/git-commit` invocation IS the human's acceptance — don't ask them to confirm the message before committing. Compose it per Steps 2-5, run `git commit` with a heredoc, surface the SHA after (Step 9). This holds regardless of diff size, breaking-change marker (`!`), or `revert:` type — the human gated the commit at the skill invocation; the message wording is the AI's responsibility.

If the human wants to preview wording first, they can ask for a draft **without invoking the skill** — e.g. "draft a commit message for this", "what would you write?". `/git-commit` itself is always direct.

Use a heredoc to pass multiline messages safely:

```sh
git commit -m "$(cat <<'EOF'
feat(notification): add reminder scheduler for due loans

Add CheckDueLoansUseCase that polls loans hourly and sends
reminders 3 days and 1 day before due date. Uses NotificationLog
table for idempotency — cron may run repeatedly without spamming.

Chose polling over deferred tasks for simplicity at this scale;
revisit when notification volume justifies a real task queue.

Co-Authored-By: Claude <noreply@anthropic.com>
EOF
)"
```

**Why heredoc:** safe for multiline content with quotes, backticks, dollar signs. Avoid `git commit -m "line1\nline2"` — the `\n` is literal.

### Step 8 — Verify the commit landed

```sh
git status        # should show clean working tree
git log -1        # show the commit just made
```

If the commit failed (pre-commit hook, etc.), **fix the cause and create a NEW commit**. Do **not** `--amend` — that modifies the previous commit, which is destructive if work was already pushed.

## Decision tree — picking type

```
Did behaviour change for a user / API caller?
├── New user-visible thing → feat
├── Existing thing was broken → fix
└── No → look deeper:
    ├── Test files only? → test
    ├── Docs/README/docstrings only? → docs
    ├── pyproject.toml / lockfile / dependencies? → build
    ├── .github/workflows / ci.yml? → ci
    ├── Performance optimisation (with benchmark)? → perf
    ├── Code rearranged, behaviour identical? → refactor
    ├── Reverting an earlier commit? → revert
    └── None of the above → chore
```

## Atomic commits

**One logical change per commit.** Signs you should split:

- Subject naturally has "and" (`fix loan check and refactor book repo`)
- Diff touches unrelated slices for unrelated reasons
- You're tempted to write 5 bullets in the body, each about a different file

If the changes are entangled and hard to split, mention this and **ask the human** whether to split or commit together. Sometimes it's genuinely one commit (e.g., adding a use case requires changes in domain + application + infrastructure + presentation + tests — all one commit, one feature).

## Examples (good)

```
feat(book): add availability check on borrow

The Book entity now tracks an `available` flag. BorrowBookUseCase
raises BookNotAvailable when attempting to borrow a book already
on loan. Returns set available back to True.

Co-Authored-By: Claude <noreply@anthropic.com>
```

```
fix(auth): reject refresh tokens with mismatched purpose claim

PyJWTTokenIssuer was accepting any valid signature without checking
the `purpose` claim. A verification token (purpose=verify_email)
could be used as a refresh token. Now both issuers validate the
expected purpose and raise InvalidAccessToken / RefreshTokenInvalid
respectively.

Co-Authored-By: Claude <noreply@anthropic.com>
```

```
refactor(loan): extract overdue check to pure function

Moved the "is loan overdue" computation out of BorrowBookUseCase
into loan/domain/services.py as `is_loan_overdue(loan, now)`. Pure
function, takes Clock-provided `now` as a parameter, easier to test
without the use case context.

Co-Authored-By: Claude <noreply@anthropic.com>
```

```
docs(readme): document email-verification flow

```

```
chore(deps): bump argon2-cffi to 23.1.0
```

```
ci: pin ruff to 0.7.0
```

## Examples (bad — fix before committing)

| Commit message | Why bad |
|---|---|
| `feat: stuff` | Vague subject, no scope |
| `Fixed the bug` | Past tense, no type, no scope, vague |
| `feat(book): Added the book add endpoint!!!` | Past tense, capital letter, exclamation, vague |
| `WIP` | If on main — incomplete work shouldn't be there |
| `feat(loan): add return endpoint and fix book repo and update docs` | Three unrelated changes — split into 3 commits |
| `chore: update` | What was updated? `chore(deps): bump pydantic to 2.13.4` |

## Hard rules

- ❌ **Never use `--no-verify`** to skip pre-commit hooks unless human explicitly asks
- ❌ **Never use `--no-gpg-sign`** unless human explicitly asks
- ❌ **Never `--amend` a commit that was already pushed** — create a new commit
- ❌ **Never run `git add .` or `git add -A`** without showing the human what will be added
- ❌ **Never commit `.env` files, secrets, large binaries, `__pycache__`, lock files marked as build artifacts**
- ❌ **Never commit if `pytest -W error` fails** — fix tests first
- ❌ **Never `git push` after committing** unless the human explicitly asks

## Step 9 — After the commit (and what's next)

- Run `git status` to verify the working tree is clean.
- Tell the human: "Committed: `<type>(<scope>): <subject>` on branch `<branch>`."
- Then surface the next-step options. Do **not** execute any of these without confirmation:
  1. **Continue working on this branch** — more commits, then merge later
  2. **Push to remote** — `git push -u origin <branch>` (first push) or `git push` (subsequent)
  3. **Open PR** — `gh pr create` with body summarising the commit(s)
  4. **Merge to main** — only if the human says "merge", "ship it" or similar
  5. **Start next slice** — switch back to main, pull, create the next feature branch

See [branches.md](branches.md) for the merge / rebase / squash decisions and PR conventions.

**Default — stay on the branch, do nothing else.** Pushing, merging, and PRs are explicit operations the human asks for.
