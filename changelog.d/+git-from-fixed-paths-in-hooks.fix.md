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
  in a hook only on that fixed `PATH`. Where it lives elsewhere and the filter is marked
  required, as `git lfs install` marks git-lfs's, the git query that runs it gives no answer:
  after a red test run, for example, the note counting uncommitted files is gone. A
  `core.fsmonitor` program, or a filter not marked required, is skipped there, and git answers
  as it would without it.
- Every `git` a hook runs, the hook wrapper's own included, is handed the home the password
  database records for your user as `HOME`, or no `HOME` where the database lists none. A tool
  that applies a file the repository commits, such as direnv, mise or a devcontainer, can set
  `HOME` for a hook, and git reads its global configuration there: a repository could ship a
  `.gitconfig` whose `core.fsmonitor` names a program it also ships, and the `git status` after a
  red test run ran that program. Where `HOME` is not the database's home, a hook's `git` now
  reads your `safe.directory` and excludes from the database's home.
- `stayfixed gate` in CI, a command you run at your terminal and one an agent runs through its
  shell tool keep the `git` on `PATH`, and the programs it runs by name, as before.
