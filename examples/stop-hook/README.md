# Run `stayfixed prove` before the agent finishes

`prove_on_stop.py` is a Claude Code `Stop` hook. When the agent finishes responding, it runs your
test command under `stayfixed prove` and lets the agent stop only on `proved`. On any other verdict
it keeps the agent working, with one line saying what `prove` answered and asking for a green run,
or a word on why there cannot be one, before finishing.

It needs Python 3.11 or later, standard library only, and `stayfixed` and `git` on `PATH`. It never
imports `stayfixed`: it runs the program, as you would.

## Installing it

Copy `prove_on_stop.py` somewhere outside the repository, and add the hook to your own settings
file, `~/.claude/settings.json`, with the test command you want run after `--`:

```json
{
  "hooks": {
    "Stop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "python3 -I ~/.claude/hooks/prove_on_stop.py --timeout 540 -- pytest -q",
            "timeout": 600
          }
        ]
      }
    ]
  }
}
```

The hook's `"timeout"` must stay above the recipe's `--timeout` (540 seconds when it is not given),
so that `prove` ends its own run and answers before Claude Code cuts the hook off. A hook past its
timeout is a non-blocking error, and the stop goes ahead.

## What it does on each stop

- It reads the hook's input, the one JSON object Claude Code writes on standard input. Input that
  is not one is a non-blocking error (exit 1): the stop goes ahead, and you see the line.
- When `stop_hook_active` is `true`, the agent is already working on because this hook blocked its
  last stop. The recipe lets that stop through at once, without a run (exit 0).
- Otherwise it runs `stayfixed prove --json --timeout SECONDS -- COMMAND…` at the top of the work
  tree that holds the input's `cwd`, so a worktree the agent works in is the one tested and a `cd`
  into a subdirectory is not followed. When `cwd` is no directory, or is in no git work tree, it
  runs where Claude Code started it.
- `proved` lets the stop through (exit 0). Any other verdict keeps the agent working (exit 2), and
  its stderr line is the reason the agent is given.
- When `stayfixed` cannot start or answers no JSON object, the stop goes ahead and you see why
  (exit 1): no continuation repairs a missing install.
- It prints nothing on standard output, ever. Claude Code reads a JSON object there on every exit
  code, so `prove`'s own would be taken for the hook's answer.

## What it costs

One run of your command on every stop that is not a continuation, a turn that edited nothing
included. If the whole suite is too slow for that, a fast selection is your choice to make, and
`proved` then covers only the tests that selection ran.

## What bounds it

Claude Code caps stop-hook continuations at eight in a row, but the count resets each time the
agent calls a tool. An agent that runs the tests between stops resets it, so the cap does not bound
a hook that blocks every stop. `stop_hook_active` does: once a block has sent the agent on, its
next stop arrives with `stop_hook_active` set to `true`, and the recipe lets that stop through.

## Whom it stops, and what it trusts

The adversary is the agent's "done". The agent in the session can edit the hook's settings file or
weaken the tests, so the anchor is your own install and the harness's sandbox, which can keep the
settings file out of the agent's writes. Even so, the recipe is a convenience, not a control: the
`stop_hook_active` let-through passes the next stop whatever the tests say, and no sandbox keeps
the agent from weakening them. It costs at most one continuation per stop and stops no agent that
means to finish. The check that holds is your project's own CI run of its tests.

## Where the `Stop` behaviour comes from

Read on 2026-10-28 in Claude Code's hooks reference, <https://code.claude.com/docs/en/hooks.md>
(sections "Stop", "Stop input" and "Stop decision control"), against Claude Code 2.1.312.
