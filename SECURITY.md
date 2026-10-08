# Security policy

stayfixed has an explicit threat model: **a repository is untrusted input.** A clone can commit
a `stayfixed.toml`, a `.claude/settings.json` `env` block, a `MEMORY.md`, a `.stayfixed/manifest.json`
and a tree of symlinks, and every one of those reaches stayfixed before any human has read it.
So a bug that lets repository-authored bytes reach the model as instructions, or lets a write
land outside the project root, is a security bug here even where it would be a nuisance
elsewhere.

## Reporting a vulnerability

**Use GitHub's private vulnerability reporting:**
<https://github.com/stayfixed/stayfixed/security/advisories/new>

That opens a private advisory only the maintainers can see. Please do **not** open a public
issue for anything in the list below — the public issue tracker discloses a containment bypass
to every user at the moment it is reported, including the ones who have not upgraded.

If private reporting is unavailable to you for any reason, say so in a public issue **without
the details** ("I have a security report and cannot use private reporting") and a maintainer
will arrange another channel.

### What to include

A proof of concept is worth more than a description. The most useful shape is a repository — or
a script that builds one — plus the command you ran and what you observed. Say which operating
system and Python version, because two of the containment paths behave differently on Linux and
macOS by design.

### What to expect

This is a small project with a single maintainer, so please read these as intentions rather
than guarantees:

| | |
|---|---|
| First response | within 7 days |
| Assessment and a plan | within 14 days |
| Fix released | as soon as it is ready; you will be told the date |
| Credit | in the advisory and the changelog, unless you ask otherwise |

## What counts

In scope, and treated as security rather than as an ordinary bug:

- **Containment.** Any write, or any read that feeds a write, that lands outside the project
  root or outside the machine owner's own store — through `..`, an absolute path, a symlink at
  any component, a TOCTOU window, or a configured value that reaches no guard.
- **The trust gate.** Any way repository-authored text reaches the model without
  `stayfixed memory trust` having been given, or reaches it outside `trust.wrap`'s delimited
  region — including through a channel stayfixed hands to the harness, such as a symlink into
  the harness's own project-memory directory.
- **Marker forgery.** Any note, index entry or configuration value that can close or forge the
  repository-data region it is wrapped in.
- **The machine anchors.** Any way a repository can choose which machine configuration file,
  overlay root or `trust.json` stayfixed reads — for example through an environment variable a
  committed settings file can set, such as `STAYFIXED_CONFIG`, or through a `HOME` that direnv,
  mise or a devcontainer applies from a file the repository commits. Claude Code's own `env`
  block cannot set `HOME`.
- **Destruction.** Any way a repository, or an ordinary mistake, silently destroys the machine
  owner's own state: the trust record, a hand-edited file, or a hook configuration stayfixed did
  not write.
- **A program a hook runs.** Claude Code applies a committed `env` block's `PATH` to hooks, and
  resolves a relative entry against the project (measured on Claude Code 2.1.293). So the hook
  path looks up no program through the inherited `PATH` but the wrapper's last-resort `python3`,
  which it refuses inside the project or any checkout of it (`docs/cli.md`): in a process the
  hook wrapper launched, stayfixed runs `git` from fixed absolute paths and hands it a fixed
  `PATH` for the programs git runs by name, such as `git-lfs`, and the wrapper names every other
  program by absolute path. Where `/bin/sh` is bash, which imports a function from any
  `BASH_FUNC_<name>%%` variable, the wrapper first removes any function named for a command it
  runs, so none stands in for one of its builtins. A committed `PATH` or exported function that makes
  the wrapper or stayfixed run a program the repository chose is in scope. What the shell acts
  on before the wrapper's first line is not; see below.

Out of scope:

- Anything that requires the attacker to already be able to write to the machine owner's home
  directory or to a directory on their own `PATH`. Outside a hook, at a terminal and in a
  `stayfixed gate` step in CI, stayfixed runs the `git` on your `PATH` by design. In the commands
  an agent runs through its own shell tool, `PATH` is the harness's to choose, and that includes
  which `stayfixed` runs, and so which `git` it runs, which nothing inside stayfixed can decide.
- `HOME` choosing git's global configuration: `$HOME/.gitconfig` and `$HOME/.config/git/config`,
  whose `core.fsmonitor` names a program git runs on `status`, `ls-files` and `diff`. stayfixed
  hands its `git` your `HOME` on purpose, so that your `safe.directory` and excludes answer.
  Claude Code never applies `HOME`, or any `XDG_*` variable, from a project's or a local `env`
  block: its settings reference says so under "Variables Claude Code ignores in `env`", and
  Claude Code 2.1.293 was measured keeping the real `HOME` and an empty `XDG_CONFIG_HOME` in
  project and plugin hooks. `XDG_CONFIG_HOME`, git's other door to that configuration, is
  dropped before any `git` runs all the same. A direnv, mise or devcontainer environment can set
  `HOME` for a checkout; that is the person's own environment, the same class as `PATH` at a
  terminal.
- A repository being able to make stayfixed **refuse** — suppressing memory, failing a hook
  closed. Undesirable, and an ordinary bug, but not a vulnerability: the whole design fails
  closed on purpose.
- Findings in a dependency that stayfixed does not reach; it has no runtime dependencies.
- A variable the dynamic loader reads (`LD_PRELOAD` and `LD_LIBRARY_PATH` on Linux,
  `DYLD_INSERT_LIBRARIES` and `DYLD_LIBRARY_PATH` on macOS) reaching a hook, from a committed `env`
  block or anywhere else. The loader acts on the hook wrapper's own shell before its first line, so
  no wrapper can refuse it. On macOS the wrapper's `/bin/sh` is SIP-protected and drops `DYLD_*`
  before anything below it starts; a shebang that loses that protection is in scope.
- `SHELLOPTS` and `PS4` reaching a hook. bash, `/bin/sh` on macOS and on the Linux distributions
  where it is bash, reads both at start-up, and with `xtrace` in `SHELLOPTS` it expands `PS4`
  before every command, so `PS4='$(program)'` runs that program. Measured against `/bin/sh`
  (bash 3.2.57) directly: the program ran in a `sh -c` handed a hook's command line, before that
  command started, and in a script whose first line was `set +x`. The shell that runs a
  shell-form hook command is the harness's, and the wrapper's own `/bin/sh` acts on both before
  its first line, so, as with the loader's variables, no wrapper can refuse them: they are the
  harness's to filter from a hook's environment, and the harness is where to report them.
  Whether Claude Code applies either from a project's `env` block is not measured here.

## Supported versions

stayfixed is pre-1.0. Only the latest released version is supported; fixes land on `main` and in
the next release rather than being backported.
