---
name: verify
description: Run the full pre-commit verification — tests, lint, types, spell, security — and report any failures.
---

# Verify

Run the full pre-commit verification suite for this project. **Do this before declaring work done.** Each step below maps 1:1 to a step CI runs on every push; see [.github/workflows/ci.yml](../../../.github/workflows/ci.yml).

## What to run

Execute in this order, **stop on first failure**:

### 1. Tests (warnings = failures)

```sh
pytest -W error
```

Expected: all tests pass with **0 warnings**. If a deprecation warning appears, fix it — do NOT silence it with `-W ignore::DeprecationWarning`.

### 2. Linter — must be clean

```sh
ruff check dispatcher tests
ruff format --check dispatcher tests
```

Expected: `All checks passed!` and `N files already formatted`. Ruff covers style, import sorting (I), bug patterns (B), security (S), pyupgrade (UP), and pytest style (PT). Configuration is in [`pyproject.toml`](../../../pyproject.toml) under `[tool.ruff]`. Do **not** add `# noqa: ...` to silence — fix the underlying issue. Per-line `# noqa: <code>` is acceptable only for a genuine false positive and must carry a one-line comment explaining why.

### 3. Type checker — must be clean

```sh
mypy dispatcher tests
```

Expected: `Success: no issues found`. mypy is configured `strict = true` in [`pyproject.toml`](../../../pyproject.toml) under `[tool.mypy]`, with a loosened override for `tests.*` that skips "missing return annotation" noise and `strict_equality` (enum-identity asserts), while keeping real correctness signals (union-attr, no-any-return, attr-defined, call-arg). Do **not** add `# type: ignore[...]` to silence — fix the underlying type.

### 4. Spellcheck

```sh
codespell --skip="*.lock,.git,__pycache__,.venv,*.egg-info,.pytest_cache,.mypy_cache,.ruff_cache,.claude"
```

Expected: zero hits. If there's a false positive (technical term), add it to a project codespell ignore list — do NOT comment it out per-line.

### 5. pip-audit — dependency CVEs

```sh
pip-audit --skip-editable
```

Expected: no known vulnerabilities in declared dependencies.

### 6. License audit — no GPL-family

```sh
pip-licenses --fail-on="GPL;LGPL;AGPL"
```

Expected: pass. The project intentionally uses only permissively-licensed runtime dependencies.

## Report format

After running all six, report to the human:

```
✅ pytest:       all passed, 0 warnings
✅ ruff:         all checks passed
✅ mypy:         no issues found
✅ codespell:    clean
✅ pip-audit:    no vulnerabilities
✅ pip-licenses: no GPL-family dependencies
```

If something failed:

```
❌ pytest: 2 failures in tests/test_task.py
   - test_happy_path_to_success: AssertionError ...
   - test_cannot_start_before_assignment: ...

⏭️ ruff: skipped (pytest failed)
⏭️ ...
```

Then **fix the failures** before continuing. Do not suggest "ignoring" or "skipping" them.

## When to run

- ✅ Before committing
- ✅ Before pushing (the `/git-push` skill calls this as its gate)
- ✅ Before declaring a task complete
- ✅ After resolving a merge / rebase
- ✅ When the human asks "is everything green?"

## Common failures and fixes

### `pytest -W error` fails on a deprecation warning

Fix the deprecated usage. Common culprits:
- `datetime.utcnow()` → `datetime.now(UTC)`
- `pkg_resources` → `importlib.metadata`
- `pytest.warns()` without `match=...` argument

### `ruff check` reports an issue

Read the rule code (e.g., `B008`, `S105`, `PT011`). Common fixes:
- `F401` (unused-import) — remove the import
- `S` family (bandit security) — real security finding; fix or document the false positive with `# noqa: S<code>` + explanation
- `I001` (unsorted-imports) — run `ruff check --fix` to auto-sort
- `UP` family (pyupgrade) — auto-fixable; modernize the syntax
- `PT011` (pytest-raises-too-broad) — add `match="..."` to the `pytest.raises(...)` call

Per-line `# noqa: <code>` is allowed for genuine false positives but each must carry a one-line comment explaining why.

### `mypy` reports a type error

Read the error code (e.g., `[union-attr]`, `[call-arg]`, `[no-any-return]`). Fix the underlying type — don't paper over with `# type: ignore[...]`. Any legitimate ignore must carry an inline comment explaining the specific external typing gap.

### `codespell` hits a domain term

Add to the project's codespell allow list. Don't ignore inline.

### `pip-audit` finds a vulnerability

- If the affected library is in `dependencies`: bump version in `pyproject.toml`
- If transitive: bump the parent dependency
- If no fix available yet: confirm with human whether to wait or pin to last safe version

### `pip-licenses` finds a GPL dependency

- Check if it's transitive — sometimes you can switch the parent dep
- If direct — replace with a permissively-licensed equivalent
- This project intentionally avoids the GPL family in runtime dependencies

## Do not

- ❌ Skip any of the 6 checks
- ❌ Add `# noqa: ...` or `# type: ignore[...]` to silence rather than fixing
- ❌ Add `-W ignore` to pytest to mask warnings
- ❌ Declare a task done with any check failing
- ❌ Run only the first check that passes and call it good — the suite is a chain
