<!--
Conventional-commit title, describing intent rather than mechanics:
  fix(memory): stop a half-built worktree tree and a refusal from vanishing
not:
  fix: update worktree.py
-->

## What this changes, and why

<!-- The behaviour before and after. If it fixes something, describe the failure, not the patch. -->

## Verification

<!--
Paste what you actually ran. Numbers, not adjectives. A stale block is worse than none:
the one section whose job is to establish reviewer trust is the one that must not be guessed.
-->

```
uv run pytest -n auto --cov --cov-fail-under=92
uv run ruff check . && uv run ruff format --check .
uv run mypy
uv run python scripts/mutation_oracle.py
uv run python scripts/release.py check
```

## The mutation

<!--
Every new assertion ships with the mutation that reddens it, or a sentence saying why none
exists. Say which line of source you broke and which test went red. See CONTRIBUTING.md.
-->

## Checklist

- [ ] Runtime code imports only the standard library
- [ ] Any write into a repository goes through `fsops`, and any configured path through `contained()`
- [ ] Any repository-authored string that reaches a summary, a hook context or an exception is wrapped
- [ ] A `changelog.d/` fragment if this is user-visible
- [ ] This is not a security fix — if it is, see [SECURITY.md](../SECURITY.md) before opening it publicly
