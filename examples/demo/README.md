# The stayfixed demo

`demo.py` builds a small repository in a scratch directory and runs `stayfixed` against it, act by
act. Each act passes only on what `stayfixed` itself answered: its exit code and the fields of the
one JSON object its `--json` prints. Nothing the script prints is read back, so an act cannot pass
on the script's own word. The recording of the demo is made from this script's run.

## What it needs

- `git` and `pytest` on `PATH`. The script installs nothing and reaches no network.
- Python 3.11 or later, standard library only. The script never imports `stayfixed`: it runs the
  program you give it, as a user would.

It makes no model call.

## Running it

```bash
python3 -I examples/demo/demo.py "$(command -v stayfixed)"
```

The argument is the `stayfixed` program under test. From a checkout, `uv sync` and then
`uv run python -I examples/demo/demo.py .venv/bin/stayfixed`, with `.venv/bin` on `PATH` so that
its `pytest` is the one found.

- `--keep` leaves the scratch directory in place and prints its path.

Every command runs with `HOME` inside the scratch directory, `GIT_CONFIG_NOSYSTEM=1` and a fixed
author, committer and date, so neither your configuration nor the clock changes what it does.
The script exits `0` when no act failed, `1` when one did, and `2` when the program is not an
executable file or `git` or `pytest` is not on `PATH`.

## The acts

1. `stayfixed prove` reads a green pytest run from the runner's own report: `proved`, 2 passed.
2. A command that only prints `42 passed` proves nothing: `not proven`, `not-recognised`.
3. A run whose only test was skipped is `failed`, `all-skipped`, never a pass.
4. `PYTHONOPTIMIZE=1`, which compiles assertions out, is `refused`, `assigned-forging`.
5. A fixed bug's regression, run by a gate of the project's own that `stayfixed adopt promote`
   enforces on `main`, fails `stayfixed gate` on the branch `change` that brings the bug back.
