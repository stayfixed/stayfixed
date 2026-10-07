When the hook wrapper launches it, as it does for every hook, stayfixed now runs `git` only from
fixed absolute paths, and hands it a fixed `PATH`. The paths are the ones the hook wrapper already
took its own `git` from, the first that exists: `/opt/homebrew/bin/git`, `/usr/local/bin/git`,
`/home/linuxbrew/.linuxbrew/bin/git`, `/run/current-system/sw/bin/git`, `/usr/bin/git`,
`/bin/git`. The `PATH` is those directories followed by `/usr/bin:/bin:/usr/sbin:/sbin`. Before,
stayfixed ran the `git` the inherited `PATH` named, and Claude Code applies a repository's
`.claude/settings.json` `env` block `PATH` to every hook, a relative entry resolved against the
project. A repository could therefore ship a `git`, or a `git-lfs` your own `git` then ran as a
filter, and have it run by every hook that asks git anything. The hook wrapper likewise no longer
runs `dirname` or `env` through `PATH`. Only a `stayfixed` the wrapper launches takes `git` from
these paths: the wrapper sets `STAYFIXED_HOOK_WRAPPER=1` for it, over any value it inherited.

- A `git` found only elsewhere, such as MacPorts' `/opt/local/bin`, a per-user Nix profile or
  `~/.local/bin`, is not the one that answers in a hook: the first of the paths above does. Where
  none of them holds one, git gives stayfixed no answer there, as when git is missing.
- A program git runs by name, such as `git-lfs` for a filter or a `core.fsmonitor` hook, is found
  in a hook only on that fixed `PATH`. Where it lives elsewhere, the git query that runs it can
  fail and then gives no answer: after a red test run, for example, the note counting uncommitted
  files is gone.
- `stayfixed gate` in CI, a command you run at your terminal and one an agent runs through its
  shell tool keep the `git` on `PATH`, and the programs it runs by name, as before.
