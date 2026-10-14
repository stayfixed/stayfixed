---
name: attribute-failure
description: Attribute one failing test or command to the change or to the environment with three runs and one verdict, never a guess. Use when a test fails and it is not obvious whether the change caused it.
---

# Attributing a failure

1. Take the exact failing command, including the environment sync it needs to be
   meaningful: `uv sync --locked && uv run --locked pytest tests/test_example.py::test_case`
   for a Python project; the equivalent for another stack. The command is the whole of what makes
   runs 2 and 3 "synced"; a command that does not sync compares two drifted environments.
2. Run `stayfixed test attribute --command "the command from step 1"`. The base defaults to
   the project's base branch; pass `--base` to compare against another ref. The command
   runs three times — the working tree as it is, `HEAD`'s committed tree in a scratch
   directory, and the merge-base with the base branch in another — and prints a verdict. It
   never moves your checkout between commits to read the "before" side; run 1 does execute
   your command where you are, so whatever that writes, it writes.
3. Take the verdict, and the three exit codes under `--json` beside it. A run that did not
   execute is reported as a failure naming which of the three it was, never as a verdict:
   a timeout is not a result, and reading one as "it fails there too" is the worst wrong
   answer this tool can give. An attribution the tool calls undetermined — `HEAD` and the base
   have several merge bases, or the clone is shallow — has no verdict either: do what it names
   (merge the base in, pass `--base`, or fetch the whole history) and run it again.
4. Before writing "flake" or "environmental" anywhere, read
   [references/baselines.md](references/baselines.md): a baseline can lie in two opposite
   ways, and "transient" ends an investigation, so it has to be earned.
5. Record the verdict where the failure is discussed — the pull request, the ledger entry —
   with the command, the merge-base and the three codes. A verdict without its inputs
   cannot be re-run.
