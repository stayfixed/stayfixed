# Command reference

Every command, what it reads, what it writes, and what each exit code means. `stayfixed --help`
gives you the one-line version; this is the rest.

Three things hold everywhere:

- **`--json` is accepted anywhere** and prints one machine-readable object instead of one line.
  It is not declared per command — the frame strips it from `argv` before parsing. A command
  whose result is a list of findings carries it under **`findings`**, named after what the
  values are and spelled the same way by every command, whatever its summary line calls them.
  Four commands do: `bugs check`, `docs check`, `memory refs` and `plan check`. Every other
  command's keys are its own and are listed with it below — `doctor`'s `checks`, `memory refs`'s
  advisory `notices`, `docs trail`'s `undeclared`, and the two of `docs trail`'s keys that are
  not lists at all, `written` and `stale`.
- **Exit codes**: `0` success, `1` findings, `2` a refusal or an internal error. A caller that
  treats `1` as "proceed anyway" must still never treat `2` that way — a refusal is a boundary,
  not a low-confidence result. Every command that reads `stayfixed.toml` refuses one that is a
  symbolic link, whatever it points at, before reading anything through it: a link to
  `/dev/zero` would otherwise be read until memory ran out. The refusal exits `2`, except in two
  commands whose exits mean something else: `stayfixed hook` refuses only on `PreToolUse` and
  continues on every other event (see [its section](#stayfixed-hook-event)), and `stayfixed doctor`
  reports it as a `stayfixed.toml` that does not load, a red row, exit `1`.
- **Every `memory` command takes the same three options**, described once here rather than six
  times below. `--root` and `--machine` are not memory's alone: [Shared flags](#shared-flags) says
  which commands take them, and in which sense.

| Option | Meaning |
|---|---|
| `--root PATH` | The project root. Default: the current directory. |
| `--store PATH` | Resolve the note store at this path instead of where the configuration says. An override of *where the notes are*, not of the rules about them: the same containment and overlay-binding checks apply, so it is not a way around the trust gate. |
| `--machine PATH` | Read this machine configuration file instead of `~/.config/stayfixed/config.toml`. Mostly for tests and for running against a second machine profile; it also decides which `trust.json` is consulted. |
## Contents

- [`stayfixed memory index`](#stayfixed-memory-index)
- [`stayfixed memory trust --in-repo-memory`](#stayfixed-memory-trust---in-repo-memory)
- [`stayfixed memory session-context --bundle <name> [--part N]`](#stayfixed-memory-session-context---bundle-name---part-n)
- [`stayfixed memory inventory`](#stayfixed-memory-inventory)
- [`stayfixed memory fit`](#stayfixed-memory-fit)
- [`stayfixed hook <event>`](#stayfixed-hook-event)
- [Hooks](#hooks)
- [`stayfixed guard bg-cleanup`](#stayfixed-guard-bg-cleanup)
- [`stayfixed commit check --range RANGE`](#stayfixed-commit-check---range-range)
- [`stayfixed commit strip FILE`](#stayfixed-commit-strip-file)
- [`stayfixed test hygiene`](#stayfixed-test-hygiene)
- [`stayfixed test attribute --command CMD [--base REF]`](#stayfixed-test-attribute---command-cmd---base-ref)
- [`stayfixed bugs new TITLE --severity S --area A [--source S] [--related ID …] [--no-fetch]`](#stayfixed-bugs-new-title---severity-s---area-a---source-s---related-id----no-fetch)
- [`stayfixed bugs index [--check]`](#stayfixed-bugs-index---check)
- [`stayfixed bugs check [--base REF]`](#stayfixed-bugs-check---base-ref)
- [`stayfixed bugs renumber OLD NEW`](#stayfixed-bugs-renumber-old-new)
- [`stayfixed docs check [--budgets] [--links]`](#stayfixed-docs-check---budgets---links)
- [`stayfixed docs trail [--check]`](#stayfixed-docs-trail---check)
- [`stayfixed plan check [--base REF] [PATH …]`](#stayfixed-plan-check---base-ref-path-)
- [`stayfixed assess [--base REF] [--builtin] [--root PATH] [--machine PATH]`](#stayfixed-assess---base-ref---builtin---root-path---machine-path)
- [`stayfixed gate [--only NAME]… [--base REF] [--builtin | --custom] [--workflow-sha SHA] [--annotate] [--summary FILE] [--root PATH] [--machine PATH]`](#stayfixed-gate---only-name---base-ref---builtin----custom---workflow-sha-sha---annotate---summary-file---root-path---machine-path)
- [`stayfixed adopt promote [GATE …] [--base REF] [--builtin] [--root PATH] [--machine PATH]`](#stayfixed-adopt-promote-gate----base-ref---builtin---root-path---machine-path)
- [`stayfixed memory refs`](#stayfixed-memory-refs)
- [`stayfixed init --yes [--dry-run] [--name NAME] [--base-branch BRANCH] [--agent NAME …] [--profile NAME] [--memory-mode MODE] [--local ID …] [--no-ci] [--root PATH] [--machine PATH]`](#stayfixed-init---yes---dry-run---name-name---base-branch-branch---agent-name----profile-name---memory-mode-mode---local-id----no-ci---root-path---machine-path)
- [`stayfixed init --questions [--root PATH] [--machine PATH]`](#stayfixed-init---questions---root-path---machine-path)
- [`stayfixed upgrade [--dry-run] [--force PATH]… [--root PATH] [--machine PATH]`](#stayfixed-upgrade---dry-run---force-path---root-path---machine-path)
- [`stayfixed uninstall [--dry-run] [--force PATH]… [--root PATH] [--machine PATH]`](#stayfixed-uninstall---dry-run---force-path---root-path---machine-path)
- [`stayfixed overlay create --owner OWNER [--name NAME] (--template | --local) [--root PATH]`](#stayfixed-overlay-create---owner-owner---name-name---template----local---root-path)
- [`stayfixed overlay init --owner OWNER [--root PATH]`](#stayfixed-overlay-init---owner-owner---root-path)
- [`stayfixed overlay upgrade [--root PATH] [--dry-run]`](#stayfixed-overlay-upgrade---root-path---dry-run)
- [`stayfixed overlay publish-template --owner OWNER [--name NAME] [--yes]`](#stayfixed-overlay-publish-template---owner-owner---name-name---yes)
- [`stayfixed attach --store PATH [--check] [--yes] [--trust-remote] [--root PATH] [--machine PATH]`](#stayfixed-attach---store-path---check---yes---trust-remote---root-path---machine-path)
- [`stayfixed detach [--root PATH] [--machine PATH]`](#stayfixed-detach---root-path---machine-path)
- [`stayfixed setup [--preset NAME] [--yes] [--home PATH] [--settings PATH] [--machine PATH] [--overlay VALUE] [--root PATH]`](#stayfixed-setup---preset-name---yes---home-path---settings-path---machine-path---overlay-value---root-path)
- [`stayfixed setup --git-hooks [--uninstall] [--root PATH]`](#stayfixed-setup---git-hooks---uninstall---root-path)
- [`stayfixed doctor [--json] [--root PATH] [--home PATH] [--machine PATH]`](#stayfixed-doctor---json---root-path---home-path---machine-path)
- [The reusable workflow](#the-reusable-workflow)
- [Shared flags](#shared-flags)
- [Configuration](#configuration)

---

## `stayfixed memory index`

Rewrite every note's `index:` line and re-render `MEMORY.md` from them.

```bash
stayfixed memory index            # write
stayfixed memory index --check    # report drift, write nothing
```

**Reads** every `*.md` under each configured group, and the current `MEMORY.md`.

**Writes** each note whose `index:` line it filled in, and `MEMORY.md` — in overlay mode, the file
the symlink points at, not the link — and, when the store was trusted before the run,
`~/.config/stayfixed/trust.json` (or the file beside `--machine`), re-recorded over the files it
wrote (see below). Under `--check`, nothing.

What it does, in order:

1. **Harvests.** A second writer — you, another session — may have appended
   `- [trigger → answer](group/note.md)` lines to `MEMORY.md`. Those are read back into each
   note's `index:` frontmatter first, so nothing a session wrote is lost by regenerating.
2. **Invents what is missing.** A note with no `index:` gets a provisional one from its
   `description`. Provisional lines are reported so you can curate them.
3. **Renders.** One section per configured group, a note's `group:` value as a sub-heading
   inside it, ordered by `startup` rank first, then by `group_order`, then by name — so a
   note ranked for the session leads its section whatever its position within a sub-heading.

`--check` exits `1` when the index has drifted, when it is over its word budget, when it is past
the harness's line or byte caps, or when a file in the store cannot be parsed as a note — one
whose name is not UTF-8 on disk included, since the index names every note by its file's name.
Such a file is named by its path inside the store, on the line and in `--json`'s `unreadable`
alike, as `memory refs` names it. Every list of names on the line names up to eight and says
how many more there are; `--json` carries every one.
The same findings are printed on the write path too — they just do not fail it, because `--check`
is the mode that fails a build.

Exits `2` if `MEMORY.md` is a symlink this store may not follow (the target rule: outside
overlay mode a symlinked index is refused outright; in overlay mode only a link into *this*
project's own share of the recorded overlay is honoured).

**When the trust gate is shut, the line says so**, on `--check` and on the write path alike, and
`--json`'s `trusted` is `false`. The question is the one the harness memory link asks: is a note,
or the store's own directory, inside the repository with no record from `stayfixed memory trust
--in-repo-memory` matching it? In overlay mode, where the store's directory is a real directory in
the repository, that is every store until the record is made. When the notes or a committed
`MEMORY.md` are themselves repository data, the line says none of it reaches a session. When only
the directory is — an overlay store whose notes all live in the overlay — it says the link waits
for a record while the standing-rules and volatile-notes bundles still deliver the notes.

**One store however it is named.** In overlay mode `--store <overlay>/projects/<name>/memory` —
this project's own share, the far end of the link tree — resolves exactly as the plain run
does, through the link tree under `paths.memory`, so the two render the same `MEMORY.md` with the
same groups: `developer` lives in `common/memory`, beside that directory and not under it. Any
other `--store` is resolved at the path it names, under the same rules as before.

**When there is no store, the refusal says why** (exit `1`). An overlay root the machine
configuration records that is not a directory on this machine — the overlay moved, or was never
cloned here — is said first, with the root named in stayfixed's own sentence (it is your
machine configuration's, not the repository's) and `stayfixed setup --preset NAME
--overlay PATH` as the way out, since `attach` refuses a store outside the recorded root. A
binding that does not hold names which of its four causes it is, in stayfixed's own words before
the region that carries the repository's: this checkout has no `origin` remote (add it, then run
`stayfixed attach`), which is asked first and is said the same way by `attach`, `attach --check`,
`doctor` and the session-start line; the overlay records no remote for this project (run
`stayfixed attach`); a record that cannot be read (the file is named inside the region); or a
record naming a different remote URL — the same repository under another URL form, https or ssh,
counts too, as URLs are compared exactly — the one case whose way out is
`stayfixed attach --trust-remote`, and only if this checkout should be bound.

**Trust interacts with this command**, and the interaction is the non-obvious part: `memory
index` rewrites the very files the trust hash covers, so it would revoke the approval it depends
on. It does not — it re-records the hash across exactly the files it itself wrote, carrying every
other file's approved digest forward unchanged. If something else changed the store while the
command ran, it refuses to carry trust and says so.

## `stayfixed memory trust --in-repo-memory`

Record that the notes sitting inside this repository may reach the model.

The flag is required and never read: it is a confirmation gesture, not a switch, and it is what
stops this from being a bare, trivially scripted command.

**Reads** every file the store yields.

**Writes** `~/.config/stayfixed/trust.json` (or the file beside `--machine`).

The hash covers every note, `MEMORY.md`, and the repository-controlled configuration rendered
into it, keyed by the store's absolute path. Change any of it and the approval lapses — you are
asked again rather than silently kept. Notes that are *yours* (an overlay store) need no
approval; recording one is inert rather than dangerous.

Exits `2` if `trust.json` exists and does not parse. It holds every project's approval on the
machine, so nothing will overwrite a file it could not read — repair or delete it.

## `stayfixed memory session-context --bundle <name> [--part N]`

Render one injection bundle. This is what a `SessionStart` hook entry invokes; you will rarely
run it by hand except to see what a session actually receives.

| Bundle | What it is |
|---|---|
| `standing-rules` | Every note flagged `startup`, in full, ranked. Never truncated — only flagged when the set outgrows its budget, because a standing rule that does not arrive is a standing rule that gets broken. |
| `volatile-notes` | Dated, perishable notes, in full; over budget, descriptions only. |

Each bundle is emitted across numbered parts, because the harness caps each hook entry's output
independently. `--part N` selects one; a part past the end prints nothing and exits `0`. A part
that is a single block too large for one slot is withheld — the command prints a short notice
saying so instead, because the harness would otherwise truncate it and a truncated region loses
the marker that says where repository content ends. `stayfixed memory fit` names the block.

Output is deliberately **raw**, not JSON: the margin that keeps a bundle inside the platform cap
is additive only because there is no envelope and no escaping. Do not pass `--json` from a hook
entry.

When the store's notes are repository data with no trust record, both bundles are empty, and
this command says nothing rather than explaining why — its output *is* what reaches the model.
`stayfixed memory index` and `stayfixed memory fit` are where the explanation is printed,
because those are the commands a person runs.

**Writes** nothing: the bundle goes to standard output and nowhere else.

## `stayfixed memory inventory`

What a memory sweep reads: every note with its word count, type, `startup` rank, date, whether
it is stale, and whether its index line is curated, harvested or provisional. Plus totals.

**Writes** nothing.

## `stayfixed memory fit`

Whether each bundle fits the numbered hook entries declared for it. Exits `1` when one does not
— either it needs more parts than there are slots, or a single block is larger than one part
and would be truncated by the platform.

A bundle that fits says nothing of whether its notes may reach a session, so the output also
reports whether the trust gate is open, by the question and in the words `memory index` uses:
`--json`'s `trusted` is the harness memory link's question, so `false` says the link waits for a
record, and the line says whether the bundles are withheld too or still deliver the notes.

**Writes** nothing.

## `stayfixed hook <event>`

Internal. Reads a hook payload on stdin, dispatches it to every handler registered for that
event, and writes the harness's expected output.

Not something to run by hand. Its exit-code policy differs from every other command: an internal
error refuses (`2`) only on `PreToolUse`, and degrades open (`0`) everywhere else — on
`UserPromptSubmit` an exit `2` erases what you typed, so a bug in stayfixed must not cost you
your prompt. A `stayfixed.toml` that does not load takes the same path, and standard error names
the kind of fault in stayfixed's own words rather than calling it an internal error:
`stayfixed: stayfixed.toml does not load (a file or value the loader refuses)` — a file it cannot
read, one that is not TOML, or a value it refuses — or `(a path that leaves the project or passes
through a symlink)` — a symlinked `AGENTS.md` is the second, since
`agents_md` is a `[paths]` key — followed by `; refused` or `; continuing open`, and a pointer
to `stayfixed docs check` for the detail. The loader's own message is never printed here:
it carries the repository's text, and a refused `PreToolUse` shows this stream to the model.
`stayfixed docs check` loads the same file and prints that message in full.

A `stayfixed.toml` that is a symbolic link is never read, whatever it points at, and no handler
runs. On `PreToolUse` the call is refused (`2`), and on every other event, `SessionStart`
included, the hook continues (`0`) with nothing on standard output; either way standard error
says `stayfixed: stayfixed.toml is a symbolic link, and no stayfixed command reads stayfixed.toml
through one; replace the link with the file itself`, followed by `; refused` or `; continuing
open`.

**Writes** inside `stayfixed/` under the data root the harness names — `CLAUDE_PLUGIN_DATA`, or
Codex's `PLUGIN_DATA` — and nowhere else of its own: `.probe`, written each time it dispatches to
learn whether the root can be written at all; under `markers/`, one empty file per `once_key`
handler that delivered, filed under a directory per session, both names hashed to a fixed width,
with all but the newest fifty session directories removed; and `diagnostics.jsonl`, one JSON line
per diagnostic record, rotated to `diagnostics.1.jsonl` once it would pass 256 KiB. With no data
root, or a relative one, nothing is written there and a `once_key` handler is asked on every
invocation. One handler writes outside it: `worktree-link`, on `SessionStart` in a worktree
other than the checkout that holds the store, makes the link tree `stayfixed attach` makes — a
symlink for each memory group and for `MEMORY.md`, at the store's own place in the worktree,
with the directories above each link created as it is made — and creates the harness memory
link, `~/.claude/projects/<slug>/memory`, with the directories above it inside the home
directory. Either kind of link replaces a symlink already at its name that points anywhere else,
a dangling one included, and leaves a real file or directory there alone. When the store's trust
no longer covers the harness link, the handler withdraws it instead, and only when it points at
this store.

## Hooks

The two harnesses do not run `stayfixed` directly. Every entry in `hooks/hooks.json` invokes
`hooks/run-hook.sh`, and its argv is:

```
run-hook.sh <policy> <stayfixed args…>
```

`<policy>` is `open` or `closed`, and it is the only argument the wrapper itself reads; the rest
is handed to `stayfixed` untouched. The wrapper exists because a Python process cannot fail
closed about its own absence: a missing script exits `2` by CPython accident, a missing
interpreter `127`, an `ImportError` `1`, a lost executable bit `126` — and Claude Code reads
every exit that is not `2` as a non-blocking error, which is permission. So the wrapper owns
three things Python cannot: it probes for a `python3` of 3.11 or newer by running code rather
than by matching a path, it resolves the project root (`CLAUDE_PROJECT_DIR`, else `git`) and
changes into it so every command's `--root` default is correct, and it maps exit codes.

`0` and `2` are the dispatcher's own and pass through untouched — a `2` it produced is a
handler's deny, not a wrapper failure. Every other exit code, and every fault the wrapper finds
before `stayfixed` runs at all, is judged by `<policy>`: `closed` refuses with exit `2`, `open`
continues with exit `0`. Either way the reason is written to stderr with a token, so the reason
is part of the contract. That Codex downgrades an exit `2` with empty stderr to a plain failure
is unmeasured: Codex 0.160.0 ran none of the plugin's hooks, so no exit of this wrapper has been
observed there, and the README's [What each agent enforces](../README.md#what-each-agent-enforces)
says what does hold on Codex.

**Exit `2` is shared with the platform, and the wrapper does not pretend otherwise.** Because a
`2` the dispatcher produced is a deny that must pass through, a `2` CPython produced underneath
is indistinguishable from it and no token accompanies it. What the wrapper owns is the set of
faults it can reach *first* — a lost policy argument, no interpreter, a launcher it cannot read,
a project root it cannot enter — and each of those prints its token. So an exit `2` **carrying a
token** is attributed; an exit `2` carrying none is a handler's deny or a fault beneath the
wrapper, and `stayfixed doctor`'s `wrapper` row reports on the same basis.

| Token | What it means |
|---|---|
| `SF_ARGV` | The entry lost its policy argument. Always a refusal, whatever the missing policy would have been: a `closed` guard that disarmed itself must say so. |
| `SF_NO_PY` | No candidate interpreter is 3.11 or newer **and outside the project root**. The message distinguishes the two states, because their remedies differ: a candidate that was found inside the checkout and skipped says so and names the remedy, while "none among the candidates" means no interpreter answered at all. `STAYFIXED_PYTHON_CANDIDATES` replaces the built-in list, space-separated — and is honoured **only when the wrapper's stdin is a terminal**, because it names the program the wrapper executes. See below. |
| `SF_NO_GIT` | There is no `git` at any of the wrapper's absolute candidate paths. `git`'s answer is one of the two anchors the interpreter containment is measured against, so a machine without one has no anchor this process can trust: it degrades under `open` and refuses under `closed`, rather than keeping the shape of the containment and none of its strength. `git` is **not** looked up on `PATH` here — see below. |
| `SF_NO_LAUNCHER` | There is no readable `scripts/stayfixed` beside the wrapper. The launcher is derived from the wrapper's own path and never read out of the environment: the harness substitutes the plugin root into the *command string*, so the wrapper that runs is always the plugin's own, while a variable of that name reaching this process from anywhere else would choose the program Python is handed — before any stayfixed guard runs. Readability and not merely existence: a launcher at mode `000` otherwise reached CPython, which printed its own error and exited `2` with no token. |
| `SF_NO_ROOT` | `CLAUDE_PROJECT_DIR`, or `git`, named a project root the wrapper could not enter. A root that cannot be *resolved* is silent and correct — nothing is configured, so nothing is emitted — but a root that was named and cannot be entered used to leave the process in the harness's working directory, where every `--root`-defaulting entry would read whatever project happened to be there. |
| `SF_RC` | `stayfixed` exited with something other than `0` or `2`; the code is printed. |

**Which values may choose what.** The wrapper asks one question of everything it reads: is this
a *destination*, or does it choose a program, or the provenance of what runs? `CLAUDE_PROJECT_DIR`
is a destination and is honoured. `STAYFIXED_PYTHON_CANDIDATES` is not — the probe asks a
candidate only to exit `0` for a trivial `-I -c`, so an unguarded list picks the interpreter that
runs on every tool call — and it is therefore gated where `stayfixed`'s machine configuration
gates `STAYFIXED_CONFIG` and `XDG_CONFIG_HOME`: honoured from an interactive terminal, ignored
everywhere else. A hook's stdin is the harness's JSON payload on a pipe and `stayfixed doctor`
hands its own probe `/dev/null`, so a committed `.claude/settings.json` `env` block — which
applies without a trust prompt in a non-interactive session — cannot reach it, while a machine
owner debugging the probe by hand still can. The `git` that resolves the project root is asked
with an allowlisted environment for the same reason: an inherited `GIT_DIR` or `GIT_WORK_TREE`
otherwise made it answer for a different repository.

**`git` is chosen by the wrapper, not by `PATH`.** It answers the question the containment below
is measured against, and on the Codex path — where `CLAUDE_PROJECT_DIR` is unset — it is the only
anchor there is, so a bare `git` would let a clone that ships one have that binary executed on
every hook invocation, before any guard. The wrapper therefore tries a fixed list of absolute
paths and takes the first that exists, asking the machine owner's own installs before
`/usr/bin/git`; nothing under `$HOME` is on the list, because `HOME` is environment-chosen too.
A machine with `git` at none of them gets `SF_NO_GIT`. This is deliberately stricter than
`stayfixed`'s own `git` calls, which do resolve through `PATH` so that the machine owner's `git`
answers: those run inside a stayfixed that has already chosen its interpreter, while this one
decides which programs may run at all.

**`PATH` is contained rather than trusted or dropped.** The last built-in candidate is bare
`python3`, resolved through `PATH`, and an `env` block can set `PATH` — so gating
`STAYFIXED_PYTHON_CANDIDATES` alone would have moved the choice of program from one variable to
another. The entry cannot simply go: it is the fall-through the built-in list exists for, and a
machine whose Python lives under `pyenv`, `nix` or `asdf` has none at any of the four absolute
paths. So the rule is narrower and matches what a hostile clone can actually stage — **no
candidate whose resolved path lies inside the project root is used**, whatever spelling reached
it. Both sides are resolved before they are compared, so a relative entry, a `.` in `PATH`, a
`..` spelling and a symlink on either side all answer the same question. Where there is no
project root to compare against, the candidate stands.

**"The project root" here means either anchor.** `CLAUDE_PROJECT_DIR` and `git`'s answer are both
taken, and a candidate inside *either* is refused. Measured against `CLAUDE_PROJECT_DIR` alone
the rule was defeatable through the channel it exists to defeat: a clone that set `PATH` to its
own tree **and** named a root outside that tree made its own `python3` "outside the project
root". Against the pair, both anchors have to move at once, and one of them is now the answer of
a binary the clone does not choose. It is a union and not a check that the two agree, because a
disagreement rule has no answer where `git` returns nothing — every project that is not a git
repository — and its only fallback there is to trust the remaining variable on its own, which is
the same hole under a longer name.

**The chosen interpreter starts isolated.** The environment reaches three things here: which
program runs, what that program imports before stayfixed's first line, and what the dynamic loader
injects into it. The candidate list and the containment above close the first. `-I` closes the
second: the wrapper runs every candidate with it — the version probe as well as the launcher —
so no `PYTHON*` variable is read (`PYTHONPATH`, `PYTHONHOME`, `PYTHONUSERBASE`), there is no
user site, and neither the working directory nor the script's own directory is on `sys.path`.
The launcher puts the plugin's own `src` there itself, and stayfixed still sees the whole
environment: `-I` changes how the interpreter starts, not what `os.environ` holds. The third is
out of any wrapper's reach — `LD_PRELOAD` on Linux acts on the wrapper's own shell before its first
line — and [SECURITY.md](../SECURITY.md) says so. On macOS the wrapper's `/bin/sh` is
SIP-protected and drops `DYLD_*` before anything below it starts, which is why its shebang must
stay a protected shell.

A machine whose interpreter really is inside the checkout — a vendored toolchain, or an in-tree
virtual environment that is the only `python3` on `PATH` — gets `SF_NO_PY` rather than a silent
run of the tree's own program: a refusal under `closed`, a degradation under `open`, and a red
`wrapper` row in `stayfixed doctor` either way. That is the accepted cost of the rule, and it is
reached only when none of the four absolute candidates answers first.

**The one row this does not cover.** A `run-hook.sh` whose executable bit has been cleared is
never executed by the harness at all, so no code of ours runs and no policy applies — the guard
is silent rather than closed. The wrapper cannot defend its own mode, so `stayfixed doctor` is
what catches it: the `files` row goes **red** on a cleared bit and hands you the `chmod +x`. Run
it after anything that rewrites the plugin directory.

**What a session hears about the overlay it is bound to: `overlay-status`.** The `attach` area
registers one `SessionStart` handler — `open`, with a `once_key`, so it speaks **at most** once
per session: the marker is banked only when the handler had something to say, so a session that
hears a line hears it once, and a repository with nothing to report is asked again on every
`startup`, `resume`, `clear`, `compact` and `fork` the matcher above covers — and it says
nothing at all unless `[memory] mode` is `overlay`. Eleven fixed lines, each carrying at most a
count, joined by newlines in this order: **no overlay recorded** on this machine, or one that
**could not be asked** about, which is a machine configuration file that will not parse; this
repository **not attached** to that overlay, the overlay recording **a different remote**
under this project's name, or this checkout having **no `origin`** to check the record against;
**a memory path refused**, so the notes were not examined at all; how
many note groups are **real directories** rather than links into the overlay; the overlay's
`stayfixed.requires` in **a form this stayfixed cannot read**, or naming **a floor this stayfixed
does not meet**; and — only when none of those fired — the overlay's branch having **no
upstream**, and the counts of its **unpushed commits and uncommitted changes**. A bound, linked,
up-to-date repository on a satisfied stayfixed hears nothing. Not one byte a repository wrote
reaches any of those lines: `project.name`, `memory.groups`, `paths.memory` and both remotes are
read and none is quoted back, because the field these lines land in is `additionalContext` —
model input with no delimiter and no trust record.

**What it costs, and on which repository.** The binding's own `origin` query runs on every
invocation, at git's five-second cap. The last two lines cost two more `git` calls at two seconds
each, and they are reached **only when nothing above them found anything wrong** — a finding
short-circuits them. So the repository that pays all three, nine seconds against the entry's own
ten-second budget shared with `worktree-link`, is the bound, linked, up-to-date one that then
hears nothing; and because the `once_key` marker is banked only on a line actually delivered,
that is also the repository asked again on every event the matcher covers. A repository with a
finding pays five seconds, hears its line, and is not asked again.

Which is why those last two `git` calls are gated on the event's own `source`: on a **compact** —
the running conversation continuing, under the session id the marker is filed under — they are
skipped, so a healthy repository costs five seconds there and not nine. `startup`, `resume`,
`fork`, `clear` and a payload carrying no `source` all pay: a resume is a new launch, often days
later, over an overlay the conversation may have left dirty, and an invocation stayfixed cannot
place in a context is treated as a new one rather than as one already answered. The cost is that
an overlay which becomes unpushed *during* a session that started clean is not reported at that
session's compactions, only at its next resume or startup; `stayfixed doctor` answers on demand. And the overlay is never a plugin stayfixed
executes anything from — its
`hooks/hooks.json` stays empty; hook entries the owner keeps in *common/claude/hooks.json* and
`projects/<name>/claude/hooks.json` reach a session only through `attach`'s explicit, ledgered
merge.

## `stayfixed guard bg-cleanup`

Judge one Bash call for a background leak. Reads one JSON object on stdin — a whole hook
payload, or a bare `tool_input` with `command` and `run_in_background` — and answers `2` when
the call would be refused (a `&`-backgrounded job with no `trap … EXIT`, or a backgrounded
command that begins with `sleep`), `1` when it carries a trailing restore no trap protects or,
for a backgrounded call, ends in a `; echo …` that hides the exit code the completion
notification will report, and `0` otherwise. Both refusals need `run_in_background` to be
`true` in the object you send —
the leak and the `sleep` are only faults for a job the harness will not reap, so a CI smoke
test written without that key measures `0` on a command that is refused in a session.
Anything it cannot read is `2`: this is the fail-closed row of the CLI table, and a guard that
guessed would be guessing. That is about the JSON, not about the command inside it: a command
longer than the 64 KiB cap is not read either, and is allowed (`0`) rather than refused,
because tokenizing an unbounded string in front of every Bash call is the larger fault.

This is the same judgement the `PreToolUse` `Bash` hook makes; the command exists so a CI
smoke test and a person can ask it without a harness.

**Writes** nothing.

## `stayfixed commit check --range RANGE`

Every message in `RANGE` (a `git log` revision range, e.g. `main..HEAD`), for lines in its
trailing attribution block that are an AI/tool attribution trailer or footer: a `-by:` trailer
whose address is at a vendor's domain or whose name is a product, a `Generated with <tool>`
footer, or a line that is only `AI-generated`. The block is the message's last paragraph plus
every paragraph above it that is attribution to the last line — the canonical harness block is
two paragraphs — and it ends at the first paragraph holding any body line. Body prose is never
judged, and a person whose name happens to be a vendor word is not a violation.
`[commit_messages] attribution_check = false` stops the rules being applied: no message is ever
a violation, but the range must still be readable, because the report says how many messages it
read. Exits `1` naming up to eight offences as `sha line N [label]` and counting the rest —
never the text, which is the repository's; `--json`'s `violations` carries every one — and `2`
when git cannot read the range or the range looks like an option.

**Writes** nothing. `stayfixed gate`'s `commit` gate, which the reusable workflow runs, reads the
range from the base to `HEAD` through this same check.

Exit `1` has two meanings here and a gate should know both: messages were read and some carry a
trailer (`FAIL: …`), and *no `stayfixed.toml` was found under `--root`*, which the configuration
loader reports as a failure — `stayfixed: failed: …/stayfixed.toml does not exist` — and not as a
refusal. A workflow that must tell them apart reads the first word of the output, or checks the
file is there before it runs the gate.

## `stayfixed commit strip FILE`

Rewrite a commit-message file in place with the attribution lines of its trailing attribution
block removed — never a line of the body. Exits `0` whether or not anything was stripped, and
says which; a message that is *only* attribution is left alone, because emptying it aborts the
commit with a confusing error and CI explains better. Refuses a symlink, and fails (`1`) on a
file it cannot read, a file that is not UTF-8 included.

Git's own trailing comment block is kept, and so is everything below the scissors line that
`commit.verbose = true` puts the staged diff under — the message is what lies above both.

This is what the chained `prepare-commit-msg` hook runs, so the trailer is gone before the
commit exists; `git commit --no-verify` skips `commit-msg` but not that hook. Installing the
hook is `stayfixed setup --git-hooks`, and removing it — restoring whatever it chained to — is
`stayfixed setup --git-hooks --uninstall`; both are documented below.
`stayfixed.guards.api.install` is the same call for a caller embedding stayfixed.

**Writes** `FILE`.

## `stayfixed test hygiene`

The environment faults that make a red test run unattributable: uncommitted changes in the
tree, which belong to no stack, and whatever each stack's profile knows about its own — for
Python, `.pyc` files under `[ledger] code_roots` whose recorded source mtime no longer matches
their source. Counts the uncommitted changes across the whole repository — a dirty tree
anywhere makes a red run unattributable — and asks every profile that ships a `hygiene.py`
(today, Python) for its counts. A profile is listed when its markers sit at the repository
root, and also, whether or not they do, when it has something to report: a Python project in a
subdirectory has no marker at the root and still gets its stale bytecode named. So a repository
in two stacks gets two entries whatever `[stayfixed] profile` names. The summary
names each such finding as `<profile>: <its note>`, and a clean tree reads `tree is clean`
followed by `; the <profile> profile has nothing to report` for each profile listed. `--json`
carries `dirty` and, under `profiles`, each listed profile's counts by its name
(`{"python": {"stale": 0, "roots": 2}}`). Exits `1` when the tree is dirty or a profile has
something to report, `2` when git cannot report the tree or a shipped profile's hint cannot be
loaded, answers in something other than text or fails; a failure is named by the profile and the
exception's type alone.

A profile's walk is bounded: Python's lists at most 500,000 directory entries under the code
roots in total, every entry and not only the bytecode, and reads at most 20,000 of the `.pyc`
files it lists. Reading a `.pyc` costs tens of times listing an entry, so each half has its own
bound; over 499,990 `.pyc` files sharing one source, the worst tree for both, the walk stopped
in under 3 s on a laptop with a warm cache, a third of the hook's 10-second timeout. A walk that
stops at either bound has not seen the tree and reports no count, stale or clean, even when the
part it saw held no Python: the command exits `2` with ``the python profile's red-run hint
stopped its walk at a bound and could not tell, so this tree cannot be judged; narrow `[ledger]
code_roots` to the directories that hold code``, which `--json` carries as its `summary` beside
`"error": "refused"`. The bounds are fixed; what they walk is not.

The `PostToolUse` `Bash` hook delivers the same note once per context after a red test run,
chosen by the command that failed rather than by configuration: each simple command of the
red run is offered to every shipped profile's hint, and the dirty-tree line and the line of
each profile whose runner it recognises (Python's: `pytest`, or `python -m pytest`) are
delivered together. A red command no profile recognises gets no note. When Python's walk stopped
at its bound, its line says the walk could not tell whether a stale build was imported, and
names neither stale bytecode nor its absence.

**Writes** nothing.

## `stayfixed test attribute --command CMD [--base REF]`

Run one failing command three times and say what the three exit codes mean. The three trees:

1. **The working tree as it is** — the command runs with `--root` as its directory, exactly
   where you are.
2. **`HEAD`'s committed tree** — extracted with `git archive` into a scratch directory.
3. **The merge-base with the base branch** — extracted the same way. The merge-base, not the
   base's tip: a base branch that advanced after the fork would otherwise carry commits that
   are not "before this change" into the before side.

That merge base has to be one commit. When `git merge-base --all REF HEAD` names several — a
history the change merged into from both sides of a base merge has them — each is as much
"before this change" as the others and a failure can pass on one and fail on another, so the
attribution is undetermined and the command says so, counting them and naming up to eight,
rather than extract the one git would pick alone. Merge the base into the change, which makes
its tip the one merge base, or pass `--base` naming the commit you mean. A shallow clone is
undetermined too, since the commit `HEAD` forked from can be cut off there and an older one stand
in for it, and so is a clone git cannot say is shallow or not. All of it is decided before
anything runs.

`--base` defaults to `refs/remotes/origin/<[project] base_branch>`, named in full so that no tag of
the short spelling stands in for it; pass it to compare against another ref.

**Writes** nothing, and nothing in it runs `git checkout`, `git stash` or `git reset`: the two
committed trees are extracted into a temporary directory that is removed before the command
returns, and your checkout is never moved between commits or restored from one.

**Your command is another matter, and the distinction is the whole safety property.** Run 1
executes it *in the working tree*, so whatever it writes there, it writes — the example above
leaves a lockfile, a virtual environment, `.pytest_cache` and `__pycache__` behind exactly as
running it by hand would. What this command guarantees is that it does not move your checkout
to another commit to get its "before" reading, not that the three runs leave no trace.

**The command is yours, and so is its environment.** `--command` takes the exact failing
command *including the sync it needs to be meaningful* — `uv sync --locked && uv run --locked
pytest tests/x.py::t` for a Python project, the equivalent for another stack. That sync is the
whole of what makes runs 2 and 3 comparable; a command that does not sync compares two drifted
environments and the verdict is worth nothing. It is also what makes this command the same tool
for every language.

The verdict, from runs 2 and 3 first and run 1 only when both passed:

| `HEAD` | merge-base | working tree | Verdict |
|---|---|---|---|
| fails | fails | — | `pre-existing: the failure is on the merge-base too, so it is not this change` |
| fails | passes | — | `this change: HEAD fails and the merge-base passes` |
| passes | fails | — | `this change fixed a pre-existing failure: HEAD passes and the merge-base fails` |
| passes | passes | fails | `environmental: HEAD passes when synced and fails in the working tree as it is` |
| passes | passes | passes | `not reproduced: all three runs passed` |

Five sentences, and the four `HEAD`/merge-base cases are exhaustive: there is no sixth verdict
and no fall-through. A run that **did not execute** — the launcher's wall-clock cap, or a
command it could not start at all — is a failure naming which of the three it was, never a
verdict. That matters more than it sounds: a cold sync in a fresh extraction is the likeliest
thing to hit the cap, and two timed-out runs scored as exit codes would read as "fails on
both", which is the one wrong answer a tool feeding a ledger entry must not give. Narrow the
command to the failing test rather than asking for a wider cap.

`--json` carries `summary` (the line the command would have printed), `runs` (`head_ambient`,
`head_clean`, `base_clean` — the three exit codes in the order they were run), `base` (the ref
asked for), `merge_base` (the commit actually extracted) and `verdict`. Record the last four
where the failure is discussed: a verdict without its inputs cannot be re-run.

Exits `0` with a verdict, `1` when the merge-base cannot be resolved (`is
refs/remotes/origin/main fetched?`), when the attribution is undetermined (several merge bases, or
a shallow clone), when `git archive` fails, or when an archive is missing tracked
files because the archived tree's own `.gitattributes` excluded them, and `2` when `--base` is
shaped like an option, which is refused above the first subprocess rather than handed to `git` as
one.

## `stayfixed bugs new TITLE --severity S --area A [--source S] [--related ID …] [--no-fetch]`

File a bug: allocate the next free identifier (`1 + max` over every entry in the working tree
and every entry ever added on any ref, after a bounded `git fetch origin` unless `--no-fetch`),
write `<paths.bugs>/<PREFIX>-nnn.md` from the template, and regenerate the index. Every
rejection happens before the first write: a title or source the flat frontmatter subset cannot
hold is quoted for you; a `--related` value that is not an identifier, an index carrying content
this tool did not generate (`2`), and an allocated identifier whose file already exists (`1`,
naming `bugs check`) each leave the tree exactly as it was. A skipped fetch is reported on the
result line, not hidden.

**Writes** the entry file (creating `<paths.bugs>` for the first entry) and `<paths.bug_index>`;
and, unless `--no-fetch`, whatever the `git fetch --quiet --no-recurse-submodules origin` it runs
before allocating writes into the repository — the remote-tracking refs, `FETCH_HEAD` and the
fetched objects — even when a rejection that follows the allocation leaves the working tree as it
was.

## `stayfixed bugs index [--check]`

Render `<paths.bug_index>` from the entry files alone. `--check` exits `1` when the committed
index differs from that rendering and writes nothing. Either form refuses (`2`) while the write
would destroy something: a line the index holds that this tool did not generate (a hand-written
section, an operator's note, or a table row with no entry file behind it — recover it into an
entry file first), or a generated index whose entry directory is gone (restore the files; the
index carries nothing of its own). A row is judged by the entry it links and not by its shape,
so a row whose entry file went missing in a merge — the last record that bug existed — is not
something regenerating may delete. A reworded
header is a stale index, not foreign content. The first paragraph names the generator, and that
paragraph is recognised structurally rather than by an exact string, so an index left by an
older generated format is still read as generated rather than refused as hand-written content.

**Writes** `<paths.bug_index>`.

## `stayfixed bugs check [--base REF]`

Every rule the ledger holds, in one pass: each entry parses under the flat frontmatter subset
and its `id:` matches its filename; no entry restates `**Status:**`/`**Severity:**` in its
body; every severity in `[ledger] evidence_boundary_required_for` carries a filled `**What this
evidence does not establish:**` line (the template's placeholder does not count); no identifier
is claimed by two files; every `related:` identifier has an entry; the index carries nothing
this tool did not generate, and is current; every `<PREFIX>-nnn` mentioned under the top-level
files and `[ledger] code_roots` has an entry (a `void` entry counts); every citation of an entry
*file* — from those roots and from the directories the `[paths]` values live under — names a
file that exists. Exits `1` with the count and up to eight `path:line [rule]` labels on the
line; `--json` carries every finding with its `detail`, which may quote the repository and is
why it is not on the line. Before a ledger exists — no `[paths] bugs` directory *and* no
generated index — every mention of an identifier and every citation of an entry file dangles, and
with `--base <ref>` a ledger the change forked with (its `[paths] bugs` or `bug_index`) is one
`ledger-removed` finding: with none of them it prints `nothing to check` and exits `0`, so the
check can be required before the first entry, and a change that deletes the ledger answers for the
ledger and for everything that refers to it. Once a ledger exists its entries are append-only:
with `--base`, each `<PREFIX>-nnn.md` the change forked with directly under `[paths] bugs` whose
exact name the tree's directory does not hold is an `entry-removed` finding, whatever still
mentions the identifier and whatever a file's fixtures marker says, so emptying the directory and
regenerating the index deletes the ledger as surely as removing it, and renaming an entry in case
alone deletes it too, on a filesystem that folds case as on one that does not. Other files under
the directory — a `README.md`, a subdirectory's notes — are not entries and may go. An entry
moves with `bugs renumber`, which leaves a `void` entry at the old number and so removes nothing.

What the change forked with is the ledger at every commit `git merge-base --all <ref> HEAD`
names, their entries taken together. An entry the base filed after the branch forked is not one
the branch deleted. A deletion is still named on a branch behind its base, on the merge commit CI
checks out, and on a history with several merge bases, where the one git would pick alone can
predate the entry while a merge deletes it all the same. Entries are append-only, so on a base
that kept its entries, taking them together refuses no branch that deleted nothing. An entry
removed from the base itself, by a direct push, is still named on a criss-crossed branch whose
merge bases include one from before the removal: restore it on the base.

Each of those commits' ledger is read where that commit's own `stayfixed.toml` put it: its
`[paths] bugs`, `bug_index` and `[ledger] id_prefix`, and nothing of how it judges an entry, so a
base carrying an `evidence_boundary_required_for` level the ledger now refuses does not stop the
change that corrects it. The copy is found and loaded as `stayfixed gate` finds and loads the
base's: at the project root's path inside the repository, through the loader, against the tree's
disk. So a root reached through a symlink, or spelled otherwise than git spells it, is refused
(`2`) here as it is there. The entries are compared by file name with the tree's directory. A
change that moves the ledger by `[paths]` answers for every entry it did not carry along, one that
changes `id_prefix` answers for every entry under the old prefix, and a deleted ledger is named at
the paths the base kept it at. A commit with no `stayfixed.toml` at the project's path is read at
the tree's paths, as the change that adds the configuration decides for itself under `stayfixed
gate`. A copy that does not load fails (`1`); one whose load meets a refusal, or whose `id_prefix`
the identifiers refuse, refuses (`2`); neither is read as a base with no ledger. A refusal prints
the base as data, and a refused prefix clipped to its first 120 characters and its length.

`--base` is what the `bugs` gate passes, the base it judges against. A base git cannot list, one
that shares no commit with `HEAD`, any base in a shallow clone, where the commits `HEAD` forked
from can be cut off and the merge base git sees be an older one, and any base in a clone git
cannot say is shallow or not, fail (`1`) rather than read as a base with no ledger; under a gate
that is the gate not running: fetch the whole history (`fetch-depth: 0`). Without `--base` the
tree alone is judged.

A generated index with no directory behind it is a deleted ledger and exits `1`. Git enumerates
the files where the root is the top of a checkout (tracked plus untracked-not-ignored), and a
walk stands in elsewhere. A file whose first 2 KiB carry `stayfixed:ledger:fixtures` holds sample
identifiers and is neither scanned nor swept.

A stale index is sent to `bugs index`, except the one a `bugs renumber OLD NEW` killed before its
last write leaves: when `NEW` holds `OLD`'s text, or `OLD` is the pointer that move titles toward
`NEW`, and the index is exactly the one rendered before the move, the line names `run: stayfixed
bugs renumber OLD NEW`, which finishes it.

**Writes** nothing.

## `stayfixed bugs renumber OLD NEW`

Move an entry to a free identifier: `NEW` gets the entry with its `id:` rewritten, `OLD` becomes
a `void` pointer at the new number, every scanned file that mentions `OLD` is rewritten, and the
index is regenerated. Both endpoints are written first, then the sweep, so an interruption leaves
`OLD` resolving to the pointer rather than to nothing.

A run that was killed part-way is finished by running the same move again. The re-run recognises
the move's own half-done state: `NEW` holding exactly `OLD`'s text with the `id:` line rewritten,
or `OLD` byte for byte the pointer this move writes to `NEW`, whose title is only held to start
`renumbered to NEW — `, so a `NEW` retitled since is still finished. It makes the writes still
missing and leaves the tree an uninterrupted run would have left, when resumed the same day: a
pointer written by the resume carries the day it is written. A re-run of a move that finished —
the pointer in place and the index fresh — changes nothing and says `OLD was already moved to
NEW; nothing to do`, and `--json`'s `moved` is `false`, so a mention of `OLD` written since stays
as it was written. While an interrupted move is what left the index stale, `bugs check` names this
command, `run: stayfixed bugs renumber OLD NEW`, where it would name `bugs index`.

Rejects `OLD` equal to `NEW`, a missing `OLD`, and any other occupied `NEW` (`1`); the last says
how to finish by hand a move whose `NEW` was edited after the kill, which the re-run can no longer
tell from an entry of its own. Raises the index refusals of `bugs index` (`2`) before touching
anything. A file the sweep could not read or write is listed and the command exits `1` naming it,
because once the pointer exists a stale mention in that file looks intentional to `bugs check`
forever. The line counts them and names up to eight; `--json`'s `unswept` carries every one, each
an object with `path` and `reason`. The path is relative to the root, and the reason is the error
in words, naming no absolute path; a refusal of stayfixed's own may repeat the root-relative path.
The moved entry's own body is the operator's to rewrite and is not swept.

**Writes** the two entry files, every rewritten file, and `<paths.bug_index>`.

## `stayfixed docs check [--budgets] [--links]`

Two checks, both enforced, and no flag runs both (exit `1`, `FAIL:`):
the always-loaded document at `[paths] agents_md` exists, is within `agents_md_lines` and
`agents_md_words`, and has a `## Current status` section within `status_lines`; the roadmap at
`[paths] roadmap`, up to the line `## Design and plan trail`, is within `roadmap_prose_lines`
and `roadmap_prose_words` (a roadmap with no marker is budgeted whole; an absent one is not a
finding); every relative local link in the agents file resolves to a file — read from that
document's own directory, and only when it lands inside the project root, since a link that
walks out through `..` would be settled against the machine rather than the repository (an
absolute link is not read at all, nor is an anchor, a URL or a `mailto:`). Budgets are the
effective ones — the preset's, lowered by `[budgets]` if the project chose to. The memory
store's link graph is `stayfixed memory refs`'s, as advice.

**Writes** nothing.

## `stayfixed docs trail [--check]`

Rewrite the listing between `## Design and plan trail` and `<!-- end design and plan trail -->`
in the roadmap: every `*.md` under `[paths] specs` and `[paths] plans` that git tracks and does
not ignore, grouped by the first `[[theme]]` in `trail.toml` (beside the roadmap) whose
`pattern` is found in its filename, `Unfiled` otherwise, each annotated with its `[states]` entry or
`delivered`. `--check` exits `1` when the listing is stale and writes nothing. Two guards make
the listing unable to lie by silence: a state naming a document that no longer exists fails
(`1`) before anything is written, counting every such key and naming up to eight, with a note
that a re-run after updating those names the rest (a key longer than 120 characters is named by
its first 120 and its length); and a document that enters the listing
without a declared state is written as `delivered` and then reported (`1`), counted and named
up to eight on the line and every one in `--json`'s `undeclared` — a design is written before
the thing is built. A listing that named no document before, such as a new project's first,
reports none of them, so the first design and plan need their states declared before the first
run. That second guard fires on the writing path only: a row enters the listing through
`docs trail`, whose exit `1` the operator sees, and `--check` has no earlier listing to compare
against, so a defaulted `delivered` that was committed over that report is invisible to CI.
A theme's `pattern` is a small part of regular-expression syntax, meaning what it means to a
regular expression: literal text, `.` for any one character, `.*` for any run of them, `|`
between alternatives, `^` and `$` at an alternative's start and end, and `\` before a
punctuation character to take it literally — `.*`, `widget` and `gadget|gizmo` are all
patterns. It is matched without backtracking, so no pattern can make a run take longer than
the name's length times its own, and a pattern holds at most 256 characters and a `trail.toml`
at most 32 themes, since every name is tried against every theme until one matches. Any other
syntax — a group, a class, `+`, `?` or `{n}` — is refused rather than read otherwise.
A `trail.toml` outside its contract fails (`1`): a non-string label, a pattern outside that
syntax or longer than 256 characters (the refusal names the theme by its `label`, a label
longer than 120 characters by its first 120 and its length), more than 32 themes, a file that is not valid UTF-8, or a `label` or `[states]` value that is not a single
line or that carries either marker — both are written into the listing verbatim, so one could
otherwise split the block and push repository prose into the roadmap. A listed document's name
is held to the same rule, and to one more: a name that is not a single line, carries either
marker, or is not UTF-8 on disk fails (`1`) naming the file, escaped, with nothing written —
rename it. A carriage return ends a line here as a newline does. Inside a git work tree,
a question git gives no answer to — which documents it ignores or tracks, when it cannot be run,
runs past its time limit or refuses the checkout — fails (`1`) with nothing written, rather than
listing every document on disk; outside one, every document is listed.

**Writes** `[paths] roadmap`.

## `stayfixed plan check [--base REF] [PATH …]`

With `PATH` arguments, lint exactly those plans; without, the plans under `[paths] plans` that
merging the change could alter on `REF`, `REF` defaulting to
`refs/remotes/origin/<project.base_branch>`, the fully qualified name, as for `stayfixed assess`
and `stayfixed gate`, so a tag called `origin/<branch>` cannot stand in for it. Those are the plans
whose copy in `HEAD` differs from `REF`'s and from that of any commit `git merge-base --all REF
HEAD` names: a copy equal to every merge base's leaves the merge taking `REF`'s, and one equal to
`REF`'s leaves it as it is. Every merge base, not the one `REF...HEAD` diffs against, which can
already hold an old plan the change puts back. Five rules, each from a retrospective: every
backticked path resolves unless the line says `(create)` or `(delete)`, or the plan declares it
on a `Create:`, `Test:` or `Delete:` line; no step is phrased as already knowing its answer
(`confirm that nothing …`, `verify no …`, `check that it does not …`); a `**Scope:**` line
with content is present; a plan claiming `Fixes <PREFIX>-nnn` carries a `**Premise:**` line with
content; and a mutation's outcome stated as fact in the present tense (`-> the test reddens`,
`watch it go red`, `reddens 8 assertions`) is a finding unless its own sentence marks it an
expectation. Without `PATH`, the first rule reads only the lines the change wrote — those that
differ from every merge base's copy and from `REF`'s — so a change editing a delivered plan, an
`Interfaces:` block say, is held to its own lines and never to paths the tree has moved since the
plan was written; a new plan is all such lines. Naming a plan as `PATH` settles every reference in
it.
Fenced code is fixture text, and so is a path claim that lands outside the project root —
an absolute one, or one that walks out through `..` — which is never settled against the
filesystem, because that answer would be about the machine rather than about the repository. A
base that does not resolve, one that shares no commit with `HEAD`, any base in a shallow clone,
where the commits `HEAD` forked from can be cut off and an older commit stand in for them, and
any base in a clone git refuses to say is shallow or not, are this command's `base-unresolvable`
finding (`1`), never an OK: fetch the whole history (`fetch-depth: 0`). A git that could not be
run or ran past its time limit, on any of these questions, fails (`1`) with that cause in
words. The `plan` gate that
`stayfixed assess`, `stayfixed gate` and `stayfixed adopt promote` run reads the same cause as a
gate that could not run, as `commit` does, because it says nothing about any plan. A `REF`
shaped like an option is refused (`2`) before git sees it. Uncommitted plans
are not in the diff; the line counts them and `--json` names them, and naming one as `PATH`
lints it.

**Writes** nothing.

## `stayfixed assess [--base REF] [--builtin] [--root PATH] [--machine PATH]`

What stands between this repository, as it is, and enforcement. It reads the tree's own
`stayfixed.toml` — not the base branch's: the question is about this tree, so this command is
not a trust boundary — and runs every configured gate (see [Configuration](#configuration)): the
built-ins `[gates] builtin` keeps, in their fixed order, then each `[gates.custom.<name>]`. A
custom gate's output goes to standard error as it ran and nowhere else, so running `assess` in a
clone runs the commands that clone configured, as running its test suite would. Then it runs the
probes below, which read files and the git index and never run a tool or reach the network.

`--builtin` runs the built-in gates and the probes and no custom gate: for a clone whose
commands you have not agreed to run. The summary names up to eight of the custom gates it left
out and counts the rest, which count toward no total, and the inventory lists every one under
`skipped`.

`REF` is the revision `plan` and `commit` compare against, and the one `bugs` compares the ledger
with where `HEAD` forked from it (whether it carried one when the tree has none, and which entries
the tree lacks), default
`refs/remotes/origin/<project.base_branch>` — the fully qualified name, so a tag cannot stand in
for it. Where that ref does not exist (no `origin`, or not fetched), `plan`, `commit` and `bugs`
could not run, and each counts as failing; a `note:` after the summary says the base is missing
and suggests `--base refs/heads/<project.base_branch>`, as `adopt promote` does.

A gate that could not judge the tree — a base that is not there, an unreadable plan, a range git
cannot read, a custom gate that could not start or ran past `custom_timeout_seconds`, a file it
reads that CI's checkout will not have (below) — is failing: a gate that could not look has not
passed. A gate never reports that as a finding; it is the one outcome every command that runs
gates spells `could not run`, and `--json` carries it as `answered: false` with a fixed `reason`
naming the command that shows why.

**The `docs` and `trail` gates judge tracked files.** That is the contract: CI checks out what git
tracks and nothing else, so a file that is on disk here and that git does not track — never added,
or ignored — is one those gates read here and CI never sees, and there the gate's own finding for
an absent file fails every pull request. So `assess` reports such a gate as could not run, its
`reason` saying it could not judge the tree as CI will, and counts it as one that would fail, and
`stayfixed adopt promote` never enforces it. To keep one of those files out of git, take its gate out
of `[gates] builtin`.

- **The files.** `[paths] agents_md` and every file or directory its links name, for `docs`, and
  `[paths] roadmap` and the `trail.toml` beside it, for `trail`. The roadmap the `docs` gate reads
  for its prose budget is not asked about: an absent roadmap adds no finding, so one CI cannot see
  can only make the verdict here stricter than CI's.
- **Tracked** means in git's index, as `git ls-files` lists it, so a file staged and not yet
  committed counts — CI checks out commits, so commit it with the change that promotes the gate.
- **Symlinks.** A symlink is tracked as the link alone, and a checkout writes the link whether or
  not what it names is there, so each path is walked as the filesystem walks it, one component at
  a time, and every symlink on the way is followed, a symlinked directory's included: every step
  and the file it lands on must be tracked. Where a link leads is judged against the work tree's
  top, since a project below it may link to a tracked file beside it, which every checkout has; a
  link whose target is absolute or climbs out of the repository counts as untracked, since no other
  checkout has what it names, and so does a link that differs on disk from the one git has — one
  retargeted and not staged — since a checkout writes git's, which may lead elsewhere.
- **The items.** An `untracked` item names the files: the first untracked step on a path, a link
  that differs on disk from git's, or a link that leads out of the repository, a directory's
  included, and when that step or link is outside the project, the last link inside it that led
  there. A name that differs from the one git tracks only in case — a link to `Notes.md` where git
  tracks `notes.md` — reads the committed file on a filesystem that folds case, as macOS's does by
  default, and nothing in a Linux checkout, so it goes to a `case-differs` item instead, whose
  remedy is to spell it as `git ls-files` does; where case is kept apart and the two names are two
  files, the one read is simply untracked. Each name is inside the path grammar or withheld.
- **No answer.** Inside a git work tree, a git that gives no answer is never read as tracked: the
  gate could not run the same way, and its item is `could-not-look`. Outside a work tree nothing is
  asked, since there is no index to ask and no checkout for CI to take, and both gates judge the
  files as they are, as `docs trail` lists every document there.
- **`stayfixed gate`** asks nothing about tracking: it runs on the checkout CI took, where such a
  file is simply absent and the gate's own finding says so.

**A gate's row.** `stayfixed assess`, `stayfixed gate` and `stayfixed adopt promote` each give every
gate they ran one `--json` row in one shape: `name`; `enforcing`; `answered`, false when the gate
could not run; `reason`, that fixed text, else empty; `count`, its findings; and `failing`, true
when it has a finding or could not run. A custom gate `stayfixed gate` did not start because the
run had already failed has a row too, `answered` false and `reason` `not run: the run had already
failed`, and `failing` true, since it judged nothing and a gate that did not look has not passed.
A row names no finding: `assess` lists them as items.

| Probe | Reads | Severity | Principle | Reported when |
|---|---|---|---|---|
| `todo-markers` | tracked files under `[ledger] code_roots` | advice | 1 | a `TODO`, `FIXME` or `XXX` word; `where` names files |
| `tracked-env` | the git index | warning | — | a tracked file named `.env` or `.env.<x>`, except `.example`, `.sample` and `.template` |
| `memory-history` | the history of `[paths] memory` | warning | 8 | the store has history and `memory.mode` is not `in-repo` |
| `foreign-hooks` | the committed hook settings of each harness `[stayfixed] agents` selects | advice | 5 | a hook entry without stayfixed's marker |
| `foreign-workflows` | `.github/workflows/*.yml` and `*.yaml` | advice | — | any workflow but stayfixed's own caller |
| `codeowners` | the first of `.github/CODEOWNERS`, `CODEOWNERS` and `docs/CODEOWNERS` | warning | 7 | the line that governs stayfixed's caller workflow names no owner, or there is no file. Lines end at a line feed, and a carriage return just before one is dropped; words are separated by spaces and tabs, a `#` starts a comment at the line's start or after a blank, a line with an owner outside `@user`, `@org/team` and an email address decides nothing, and a line holding any other whitespace or control character, a carriage return anywhere else included, is read with no owner; not judged under `[ci] mode = "none"` |
| `codeowners-scope` | the same file, and `.github/workflows/*.yml` and `*.yaml` | warning | 7 | the caller workflow is owned, but a workflow a pull request could add — asked at a name no project gives one, as `.yml` and as `.yaml`, so `stayfixed*` or `*.yml` alone does not own it — a workflow the repository already has, or the code-owners file itself is not; a `/.github/` rule in a file kept at `.github/CODEOWNERS` owns all three, until a later line with no owner takes a file back out of it. `where` names `.github/workflows/`, each unowned workflow whose path is inside the plain-path grammar (any other is counted under `.github/workflows/`), and the file. The repository's workflows are asked in turn under a budget of 30,000,000 matching steps, counted as they are taken; past it, the workflows not yet asked are `could-not-look`. Silent where `codeowners` reports; not judged under `[ci] mode = "none"` |
| `commit-types` | the subjects of the last 100 commits, merges excluded | advice | — | a subject whose type is not in `[commit_messages] types`; `where` names commits |
| `profile` | the configured profile's checks | the check's own | — | each failed check, counted once; a profile this stayfixed does not ship is one `profile-not-shipped` warning |

A probe that could not look — a git query that failed or timed out, a settings file stayfixed
cannot read, a path through a symlink — reports a `could-not-look` warning naming where, and
never reads as "nothing found". Two things are deliberately not inventoried: another tool's
design-document directories, because stayfixed names no other tool's convention; and whether a
test exercises what its name says, which only reading one stack's test files could judge.

**Writes** `.stayfixed/assessment.json`, which the `stayfixed:ignore` region keeps out of git,
overwritten on every run that gets that far and never read back: format `1`, with `format`,
`stayfixed` (the version that wrote it), `base`, `state`, `enforcing` (the gates
`[stayfixed] enforced` makes enforcing, every configured gate under `installed`), `skipped` (the
custom gates `--builtin` left out, else empty), `gates` (a gate's row each, above) and `items`
(per item: `probe`, the gate or probe that found it; `rule`; `principle`, a number in
[the principles](methodology/principles.md) or `null`; `severity`, `warning` or `advice`;
`remedy`; `where`, at most 200 labels; and `count`, how many there were, never capped). A gate's
findings become one item per rule, at `warning`. `--json` prints the same object with `summary`
beside it. When git does not ignore the file where it is written, the summary ends with a note
saying so. A `.stayfixed` that is a symlink or not a directory, or a directory at the inventory's
place, is a refusal and the inventory is not written. Anything else at that place, a symlink
included, is replaced by the file, and what a symlink pointed at is left as it was. Without
`--builtin`, a custom gate writes whatever its command writes, and every gate runs before the
inventory is written, so that refusal comes after the custom gates have run.

The summary prints counts and stayfixed's own words — gate names, probe and rule ids,
severities, remedies — and never a path the repository chose: one table with a row per gate
(`gate`, `enforcing`, `findings`, `would fail`) and one with a row per item (`from`, `rule`,
`severity`, `count`, `remedy`).

Exit codes: `0` when no gate would fail, whatever the probes found, so `0` means every gate
could enforce now; `1` when a gate would fail, enforced or not, or when `stayfixed.toml` is
missing or invalid (`failed:`, as for every command that reads it); `2` on a refusal, a
`stayfixed.toml` that is a symlink among them: it is never followed, as no command follows it.

## `stayfixed gate [--only NAME]… [--base REF] [--builtin | --custom] [--workflow-sha SHA] [--annotate] [--summary FILE] [--root PATH] [--machine PATH]`

The gate a pull request faces, runnable on your own checkout. One run:

1. refuses a project root reached through a symbolic link, spelled otherwise than git spells it,
   or given with a `..` component, which after a linked component is not the directory it names;
2. reads the base's `stayfixed.toml` at one exact commit, at the project's own path in the repository;
3. judges this tree's `stayfixed.toml` against it, key by key (below);
4. runs the configuration check and the configured gates under the configuration that judgement
   chose, each enforcing or advisory as it says.

Without `--only` it runs the configuration check and every configured gate: the built-in gates
`[gates] builtin` keeps and the project's own `[gates.custom]`. `--only NAME` runs just the names
given, each once; `config` is the configuration check. A name this run's configuration does not
have is refused, counted and not quoted. Running it in a clone runs that clone's own gate
commands, as [Configuration](#configuration) says.

**`--builtin` and `--custom`.** `--builtin` runs the configuration check and the built-in gates
and executes no command from `stayfixed.toml`; `--custom` runs the project's own gates alone and
judges nothing. Each narrows the bare run, or `--only`'s names, to its kind, and skips a name of
the other kind rather than refuse it. `--builtin` runs the configuration check whatever `--only`
names: it is the run that judges, and a caller that names one gate — a matrix leg, a person
reproducing CI — still judges the change's `stayfixed.toml`, so a loosening fails every such
run. The reusable workflow runs them as two steps, the second only when the first passed. A
custom gate's command is fixed by the base, but the files it executes — a `conftest.py`, a
`Makefile`, a script — are the change under review, so for a custom gate the guarantee is "this
command runs and must exit 0", and nothing about what it runs. An owner who wants those files
pinned puts them under CODEOWNERS. Run bare on your own checkout, everything runs in one
process. Narrowed to nothing — `--custom` on a project with no gate of its own — the run prints
`nothing to run`, appends no summary and exits `0`.

**Which custom gates run, and in what order.** A custom gate runs only with the command the
base's `stayfixed.toml` gives it. One the change adds, or re-commands while the base does not
enforce it, is not run: it prints `<name>: advisory, not run until the base has this command`
(or `enforcing`, when the change enforces it), and runs from the first pull request after it
lands on the base. It fails nothing meanwhile, since the base enforces no command it lacks, and
under the bootstrap, where the base has no `stayfixed.toml`, no custom gate runs. The reason is
that the custom gates share one checkout: a gate the change wrote, run before the base's
enforced ones, could rewrite the script they are about to execute. For the same reason the
built-in gates run first, then the custom gates the base enforces, then every other custom gate.
And once the run has failed — a refused key, or an enforcing gate among those that failed or
could not run — no custom gate starts, one the base enforces included: each prints `<name>:
advisory, not run: the run had already failed` (or `enforcing`), and its `--json` row says the
same, `answered` false with that `reason`. A custom gate can run files the change can edit, and
it runs in the process that holds the verdict, on a GitHub-hosted runner with passwordless
`sudo`, which could rewrite that process and turn its failure into a pass. An enforced gate is
no exception: a test runner the base enforces beside a pinned policy runs the change's code, and
started after the policy failed it would run after the verdict was decided. So once the verdict
is a failure no custom gate runs, and a pinned gate named to sort first among the enforced ones
has passed before any other custom gate starts. While the run has not failed (an advisory gate's
findings do not fail it), a custom gate runs as always; one that was not started is judged on the
next run, once the failure is fixed.
Each custom gate runs in a session of its own, and the command's process group is ended when
the command exits, passes or not, as on a timeout or an interrupt, so nothing it started in the
background in that group runs on into the next gate. A descendant that leaves the command's
process group (a new session, or a job-control shell's own group) is not ended, and nor is one
stayfixed may not signal (a sudo or setuid descendant). Enforced gates that themselves run files
the change can edit — two test runners, say — still share that one checkout, and one could
rewrite what the other runs; one leg per gate isolates them (see "One row per gate" under
[the reusable workflow](#the-reusable-workflow)).

**What a pull request may change in `stayfixed.toml`.** Both copies go through the loader and are
compared by what it derives — each key by its dotted name, each budget by its effective value,
each custom gate's `run` on its own — never by byte. A comment, a key written out at its default,
a reordered `enforced` or `[gates] builtin` list, and `installed` beside a list that says the same
thing are no change at all. Each changed key gets one verdict:

| Key | Admitted when | Verdict | Otherwise |
|---|---|---|---|
| `stayfixed.state` and `stayfixed.enforced`, judged as one | this tree enforces every gate the base enforces, and `state` does not move back (`initialised`, `adopting`, `installed`) | `tightened` when either moved forward, else `neutral` | `refused` |
| `gates.builtin` | a gate added, or one removed that the base does not enforce | `tightened` when one was added, else `neutral` | `refused` |
| `gates.custom.<name>.run` | the gate is new, or the base does not enforce it | `tightened` when new, else `neutral` | `refused` |
| `budgets.<name>` | the effective value is at most the base's | `tightened` | `refused` |
| `stayfixed.preset`, `stayfixed.profile`, `stayfixed.agents`, `project.name` | always: no gate reads them | `neutral` | — |
| `stayfixed.version` and `ci.ref`, judged as one upgrade | the version is exactly the running stayfixed's and not earlier than the base's, and a moved `ci.ref` is the commit `--workflow-sha` names and one of stayfixed's release tags names | `upgrade` | as any other key |
| any other key | — | — | `refused` while the base enforces any gate, `noted` while it enforces none |

A preset switch is judged by what it moves: its own name is `neutral`, a budget it lowers
`tightened`, and anything else it moves falls to "any other key". "Not earlier" is read the way
`stayfixed upgrade` reads it — by the leading `X.Y.Z`, and a release after its own pre-release — and
a pair stayfixed does not order is judged as any other key: refused while the base enforces a gate,
noted while it enforces none. The run uses this tree's configuration unless a key was
refused, and then the base's; it enforces the gates either side enforces. So a pull request that
promotes a gate is held to that gate in its own run.

**How a refused change lands.** While any gate enforces, a pull request cannot make a change the
table refuses, and under `installed` that includes routine upkeep: a `[paths]` value,
`[artifacts] local`, a `[ledger] code_roots` entry, a `[commit_messages] types` entry, a custom
gate's `run`, `[gates] custom_timeout_seconds`, `[project] base_branch`. The owner makes such a
change by pushing it directly to the base branch; every later pull request is judged against it.
If you want that push to need you, and not an agent working with your credentials, protect the
base branch at the repository level so that only you can push to it. Many projects do not need
that, and it is an option, not a requirement.

**What each input rests on.** The verdict holds where the repository has the settings
[the reusable workflow](#the-reusable-workflow) names, and not otherwise.

- *The base's commit.* `--base` takes a full 40-character commit id or a full `refs/…` name, and
  nothing shorter: git resolves a short name through rules in which a tag called `origin/main`
  wins over the remote-tracking branch of that name, and a full name that does not exist falls
  through to a tag of the same spelling, so the name must also exist as itself. In CI the workflow
  resolves the base once to a commit and passes that. Run locally, the default is
  `refs/remotes/origin/<project.base_branch>`, read from this tree's own configuration, which is
  why a local run is advice and never the authority. A clone without an `origin` remote names its
  base with `--base`, such as `--base refs/heads/<project.base_branch>`: a run whose base is not
  in the checkout fails with that suggestion, spelled with the branch the file configures.
- *The base's copy.* It is read at the project root's own path in the repository. A root reached
  through a symbolic link below the repository's top, or spelled otherwise than git spells it, is
  refused: either would look for the copy where the base has none, and a missing copy is the
  bootstrap, where this tree decides. A link above the repository's top — `/tmp` on macOS, a linked
  home directory — belongs to the machine and is admitted.
- *The running stayfixed and `--workflow-sha`.* In CI both are whatever the caller workflow's
  `uses:` line selects. A pull request can edit that line; a required code-owner review of
  `/.github/` is what keeps it out of the pull request's reach.
- *Release tags.* A moved `[ci] ref` is admitted only at a commit one of stayfixed's own `v*` tags
  names, asked of the public repository.
- *The verdict itself* is worth what the process that computed it is worth. It must execute
  nothing the repository wrote: run it with `--builtin`, and start it as
  `python3 -P -s -m stayfixed`, so that no module in the checkout is imported in place of
  stayfixed's own, and no `.pth` file in a user site directory is processed at start-up, even one
  the environment has pointed into the checkout.

Run locally on a branch `stayfixed upgrade` made, a moved `[ci] ref` is refused unless you pass
`--workflow-sha` with the commit the new `uses:` line names; with it, the run answers what CI will.

**Printed.** `config: …` first when the configuration check runs: how many keys changed, how many
were refused and up to eight of their names, or that the base has no `stayfixed.toml` at this
path. Then one line per gate: `<name>: enforcing, N finding(s)`, `<name>: advisory, N finding(s)`, or `could not run`
in place of the count, or `not run: the run had already failed` for a custom gate not started
once the run had failed; and, after the gates that ran, `<name>: advisory, not run until the base
has this command` (or `enforcing`) for each custom gate whose command the base does not have. A run
that fails with a gate failing ends with one `details:` line saying
where the findings are: `stayfixed assess --json` (`stayfixed assess --builtin --json` under
`--builtin`), or the gate's own command. Key names and gate
names print; values from `stayfixed.toml` and a finding's detail never do.

**`--annotate`** also prints GitHub workflow commands, which the platform shows as annotations:
one `error` per refused key, and one per finding or gate that could not run or was not started —
`error` for an enforcing gate, `warning` for an advisory one — and a `warning` per custom gate not
run until the base has its command. The message is `<gate>: <rule>`. `file=` is written
from the repository's root and only for a path of letters, digits, `.`, `_`, `-` and `/`; any
other path is annotated without a location, and a `commit` finding, which names a commit, has
none. At most ten per level; past that one `notice` counts the rest, because the platform shows
ten per level per step and drops the others without a word.

**`--summary FILE`** appends a markdown table — each gate's mode, count and outcome, and each
changed key's verdict — to `FILE`; the workflow names the job summary. **`--json`** carries
`config` (`judged`, `base_state`, `changes` as `{key, verdict}`, `refused`, `enforcing`),
`not_on_base`, the custom gates not run until the base has their command, and `gates`, a gate's
row each as [`stayfixed assess`](#stayfixed-assess---base-ref---builtin---root-path---machine-path)
defines it, `enforcing` as this run enforces it. It lists no finding: `stayfixed assess --json` is
where findings are serialised.

**Reads** `stayfixed.toml`, the base's copy through git, every file a gate reads, and — only when
`--workflow-sha` matches a moved `[ci] ref` — the public repository's tags.

**Writes** nothing but the file `--summary` names; a custom gate writes whatever its command writes.

A pull request that removes `stayfixed.toml` — `stayfixed uninstall` among them — fails the run:
nothing says which gates run, and a run that cannot judge a change does not pass it. Such a
change lands the way a refused key does, by a direct push to the base branch.

A gate that could not run fails the run only when it enforces, whatever stopped it — a refusal
raised inside the gate included, such as a path its own configuration names that turns out to be
a symbolic link. An advisory gate stopped that way prints `could not run` and is a warning
annotation, and the run can still exit `0`; the gate's own command, which the remedy names,
shows the refusal itself.

Exits `0` when no enforcing gate failed or could not run and, when the configuration check ran,
nothing was refused; a custom gate not run until the base has its command changes neither. `1`
when an enforcing gate failed or could not run; when the configuration check refused a key; when
the base is not in the checkout or git could not read its copy (the message names
`fetch-depth: 0`); when the root is not inside a git repository, or git refuses the one it is
in; when this tree has no `stayfixed.toml`; or when either side's `stayfixed.toml` is not UTF-8
text or does not load, the message naming which (a base's copy is fixed on the base branch, and
is never read as the base having none). `2` on a refusal: a `--base` outside its grammar (before
anything runs); a root reached through a symbolic link, spelled otherwise than git spells it, or
given with a `..` component; an `--only` name this run's configuration does not have; a
`stayfixed.toml` that is itself a symbolic link; or a `[paths]` value on either side that leaves
the root, passes through a symbolic link, or names `.git` or `.stayfixed`. Both copies are loaded
against this tree's disk, so a change that turns a directory the base names into a symbolic link
refuses the base's own load, in a message that says it is the base's, and a base written for an
older stayfixed that this one no longer loads fails every pull request until the owner fixes it
on the base branch.

## `stayfixed adopt promote [GATE …] [--base REF] [--builtin] [--root PATH] [--machine PATH]`

Runs gates strictly on the tree as it is, and enforces those that pass by adding them to
`[stayfixed] enforced`. It is the one adoption command: the first gate it promotes moves an
`initialised` project to `adopting`, and an `adopting` project with nothing enforced yet — one
written so by hand, or left so by an earlier release — is promoted from the same way. With no
`GATE`, it runs every configured gate that does not enforce yet, enforces each one that passes,
names the rest with their finding counts, and exits 1 if any failed; the line names up to eight
gates in each of its two lists and counts the rest, and `--json` carries every one. With names,
they pass together or nothing is written, and a named gate that already enforces is refused
rather than skipped. Once every configured gate enforces, the state becomes `installed` and
`enforced` is emptied: under `installed` an empty list means every configured gate, so a gate
the project adds later enforces from its first run — for a custom gate, the first run after it
lands on the base branch, since `stayfixed gate` runs none before. An `adopting` project whose
every configured gate already enforces — one that removed the last gate it had not promoted — is
moved to `installed` with no gate run; a project that configures no gate is refused, since it
has none to have earned. The state never moves back. A name, a gate already enforcing, nothing
left to promote, a `stayfixed.toml` the editor cannot rewrite in place and a manifest it cannot
read are each refused before the first gate runs; a refusal from the editor names `state` and
`enforced` together, one line each: as they stand when the check before the gates finds it, and
as the command would write them when the write itself refuses, so following it either leaves the
project as it was or makes the transition whole.

`--base` is what `plan` and `commit` judge a range against, and what `bugs` compares the ledger
with where `HEAD` forked from it, as for `stayfixed gate`: a 40-hex commit or a `refs/…` name,
`refs/remotes/origin/<project.base_branch>` by default. The reusable workflow judges against `[ci]
gate_branch`, which is that branch unless the file sets it; where the two differ, pass `--base` to
judge as CI will. Run on the base branch itself, that range is empty and those two gates pass
having judged nothing; the pull request that carries a promotion faces every gate it promotes in
its own run. A custom gate runs its command here, as it does under `stayfixed gate`, and only
when that command is the one the base's `stayfixed.toml` gives it: a gate the base does not have,
or has with another command, is not run and not promoted, and is named `(not on the base)` with
a `note:` saying to land it on the base branch first, because `stayfixed gate` would not run it
in the pull request that carries the promotion. A base that cannot be read, or has no
`stayfixed.toml`, has no command, so every custom gate waits.

A `docs` or `trail` gate that reads a file CI's checkout will not have is never promoted, since CI
would fail the gate on every pull request (*The `docs` and `trail` gates judge tracked files*,
under `stayfixed assess`). It could not run, is named `(could not run)`, and a `note:` for it names
up to eight of the files and counts the rest, each inside the path grammar or withheld, and says
to commit them — an ignored one needs
its ignore rule removed, or `git add -f` — and to point a symlink it names at a tracked file in the
repository, or to keep them out of git and take the gate out of `[gates] builtin`. A file git
tracks only under a name that differs in case gets a `note:` of its own, saying to spell it as
`git ls-files` does; one git gave no answer about is named with a `note:` saying so.

`--builtin` runs the built-in gates and no custom gate, as `stayfixed assess --builtin` does: for
a clone whose commands you have not agreed to run, where the base is the clone author's and its
having a command is no brake. A custom gate is promoted only by a run that ran its command, so
each one is not run and not promoted, is named `(not run, as --builtin asked)` with a `note:`
saying that without `--builtin` the command runs them, and, named beside other gates, holds them
back as a gate not on the base does.

`--json` carries, on exit 0 or 1, `before`, `after`, `gates` (a gate's row for each gate it ran,
as `stayfixed assess` defines it, `enforcing` when this run promoted it), `promoted`, `failing`,
which maps each gate that ran and did not pass to its finding count, `unanswered`, the gates that
could not run, `not_on_base`, the custom gates not run because the base does not have their
command, `skipped`, the custom gates `--builtin` did not run, `untracked`, which maps each gate
not promoted because it reads files CI's checkout will not have to those files, other than the
ones below, and `case_differs`, which maps each gate not promoted because git tracks a file it
reads only under a name that differs in case to those files, as read; a gate whose only such files
differ in case is under `case_differs` alone. When a gate stays
advisory, the summary ends with a line saying where its findings are
(`stayfixed assess --json`, or `stayfixed assess --builtin --json` under `--builtin`, or the
gate's own command), and, when `plan`, `commit` or `bugs`
could not run and the base is not in the checkout, a `note:` saying so and naming `--base` with
the project's base branch, since a gate that could not run for want of the base says nothing
about the tree.

**There is no demotion.** Loosening is an edit to `stayfixed.toml`, and `stayfixed gate` refuses
it to any pull request while anything enforces. It lands only through a push that bypasses
branch protection, which is an owner's act and not a command. Removing or renaming a gate that
`[stayfixed] enforced` lists is such an edit, and the same push must take the name out of that
list, or `stayfixed.toml` no longer loads.

**Writes** `stayfixed.toml`'s `[stayfixed] state` and `enforced` through the same editor as
`stayfixed upgrade`, and the manifest's record of it when that record still describes the file —
and nothing when no gate is promoted and the state does not move. A custom gate writes whatever
its command writes.

| Exit | Meaning |
|---|---|
| 0 | every gate it ran passed and now enforces, or an adopting project whose every gate enforces was installed |
| 1 | a gate failed, could not run, is a custom gate whose command the base does not have, or is a custom gate `--builtin` did not run: with names, nothing was written; without, the others were enforced; or `stayfixed.toml` is missing or does not load |
| 2 | a name that is not a configured gate, a named gate that already enforces, nothing left to promote, a project that configures no gate, a `--base` outside its grammar (from the parser), a manifest that cannot be read, or `stayfixed.toml` refused |

## `stayfixed memory refs`

Every backticked repository path a note names still exists. Notes are read as authoritative and
age silently, so a path to a deleted module sends the next session after it. A candidate is
dropped when the tree explains it: shorthand that resolves under the root, a code root or the
directory a `[paths]` value lives in; an absolute path outside the repository; a placeholder
(`scripts/foo.py`); a path the repository's ignore rules cover — except a path into the store
itself, which those rules cover wholesale and which is settled on disk. Fenced code and bare
filenames are skipped. In an overlay store, a note in a cross-project group that `[[links]]`
into a project-scoped note is an `audience` finding. Exits `1` listing `note:line [rule]`; the
targets are in `--json`. A note that exists and would not parse is counted on the line and
named in `--json`, and is exit `1` too: an unread note is not a clean note. Beside those, the
store's link graph is reported as advice: every `[[wiki-link]]` names a document in the store,
no link is immediately repeated, and no ledger identifier is bracketed. Each miss is a notice,
counted on the line and listed under `notices` in `--json`, and never changes the exit code: the
store is shared by every session on the machine, so a link a sibling session left dangling is a
hint, while a stale path is a finding. Refuses (`2`) when a
configured group could not be resolved, counting them on a line that names none, then naming
every group with the resolver's own reason for it, one per line, inside the delimited region that
marks repository-authored text as data — the one list of names not capped at eight, since the
region is data rather than a line, and on the path a model reads the harness keeps at most
`[native_caps] hook_output_chars` of it — because a walk over a subset that reports nothing stale
is worse than no guard. Where *no* store resolves at
all, the exit is `1`, with the number of configured groups and the reasons for the first eight
of them in sorted order, a group longer than 120 characters named by its first 120 and its
length: that comes from the resolver every `memory` command shares, so part of the store being
unreadable is a refusal while the whole of it being unreadable is findings. That is
the wrong way round by the ordering above, it is a known issue in the `memory` area, and until
it is fixed a caller should gate on a non-zero exit rather than on the number. Write a path that
deliberately does not resolve in *italics*.

**Writes** nothing.

---

## `stayfixed init --yes [--dry-run] [--name NAME] [--base-branch BRANCH] [--agent NAME …] [--profile NAME] [--memory-mode MODE] [--local ID …] [--no-ci] [--root PATH] [--machine PATH]`

Writes a repository's stayfixed footprint, once. It is the only command that creates the
documents every other command reads, and the only one that writes `stayfixed.toml`.

**`--yes` is required, and it means "take the defaults `stayfixed init --questions` shows".**
Without it nothing is written, and the refusal (`2`) names `--questions`.

Each answer flag replaces one default and writes one key:
- `--name` writes `[project] name`;
- `--base-branch` writes `[project] base_branch` and `release_branch`; `[ci] gate_branch`,
  left out, is that branch, so the workflow gates the branch pull requests merge into;
- `--agent`, once per harness, writes `[stayfixed] agents`;
- `--profile` writes `[stayfixed] profile`, an empty value meaning none;
- `--memory-mode` writes `[memory] mode`;
- `--local`, once per file, writes `[artifacts] local`.

The parser refuses a value outside its grammar or its choices (`2`), and it refuses a name or
a branch by naming the rule, never the value. A branch is a name git accepts as one, written in
letters, digits, `.`, `_`, `-` and `/` and led by a letter or digit: no `..`, `//`, component
starting with `.` or ending in `.lock`, no trailing `/` or `.`, and not `HEAD`. The same
grammar holds `[ci] gate_branch` and a detected base branch. Answer flags reach only a
`stayfixed.toml` this run creates. Over one the repository already has, they are refused
(`2`), because that file is the answer. Passing a default as its flag loads as the same
configuration as not passing it.

When nothing answers, `init` detects:
- the project's name from `origin`'s last path segment, lower-cased and with `.git` stripped,
  else from the checkout's directory name;
- the base branch from `refs/remotes/origin/HEAD`, read as the full ref with exactly
  `refs/remotes/origin/` stripped, when that is a plain branch name, else `main` with a `note:`
  saying so. A repository with a remote and no `origin/HEAD` — one created locally and pushed,
  until `git clone`, `git remote set-head`, or a `git fetch` from git 2.48 on records one, or one
  whose only remote is another name, such as `upstream`, pushed or cloned with `-o upstream` —
  gives `main`, with a `note:` naming `--base-branch`, and `git remote set-head origin --auto`
  where the remote is `origin`: the branch checked out there is typically the feature branch the
  adoption is made on. Where git cannot list the remotes, it gives `main` with a `note:` saying
  so. Only with no remote at all is it the branch checked out, when that is a plain branch name,
  with a `note:` when it is not `main`, else `main`. The workflow gates the same branch, since
  `[ci] gate_branch` left out is the base branch;
- the agent surfaces from which of `.claude/` and `.codex/` the repository carries, both when
  it carries neither;
- `[stayfixed] profile` from the first shipped profile whose markers sit at the root
  (`python`: `pyproject.toml`, `setup.py`, `setup.cfg`, a requirements file, a `Pipfile` or a
  lockfile), written only when one is found.

Both name candidates, the remote's segment and the directory name, are repository-authored.
So one outside `[project] name`'s grammar is refused naming the grammar and the remedy, and
never the value, unless `--name` answers it. With a `stayfixed.toml` you wrote, the file answers
it: one with no `[project] name` fails (`1`) with the loader's own sentence, whatever the
repository suggests.

**A `stayfixed.toml` you wrote is the answer sheet, not an obstacle.** Every key it carries is
read and kept: the name, the paths, the memory mode, the budgets, the gates. The file itself
is not replaced. It is a create-once artifact, so a repository that already has one is
reported `skip_modified` ("create-once, and the file is already there").

The one change is a missing `[stayfixed] version`, the only key stayfixed owns that the loader
requires. This run writes it into the file in place, leaves every other line as it was, and
says so in a `note:` line.

The file is then checked as it will be on disk, that key included, before anything is
written. One the next command could not load fails (`1`) with the loader's own sentence, and
nothing is written: no `[project] name`, a `state` outside `initialised`, `adopting` and
`installed`, or an `enforced` list the loader holds against `state` and the gates.

The paths it declares are where the footprint lands. A repository with no `stayfixed.toml` gets
one written from the detected values and your answers, headed by a comment naming the four
keys that are stayfixed's to rewrite: `[stayfixed] version`, `state` and `enforced`, and
`[ci] ref`. A file that cannot be read, is not UTF-8 text or is not valid TOML is a failure
(`1`) naming the file. A repository that already carries `.stayfixed/manifest.json` is refused
(`2`): re-running `init` is `stayfixed upgrade`. `stayfixed uninstall` later keeps a
`stayfixed.toml` you wrote, the version line included. When that file configures
`[gates.custom]`, a `note:` names those gates, up to eight and then a count, and says that
`stayfixed assess`, `stayfixed gate` and `stayfixed adopt promote` run their commands: in a clone,
those are commands the clone wrote, and the dry run you read before `--yes` says so. The
commands themselves never print.

**Two passes, both planned before either is applied.** The three write-once files are one pass
and the rest of the footprint is the other, because two artifacts cannot target one file in one
pass and both the `AGENTS.md` skeleton and its `harness` region land on `AGENTS.md`. A refusal
in either plan stops the run with nothing written and no manifest, and `--dry-run` is that same
branch rather than a second code path — it reports both plans and writes nothing. On a
repository with no `AGENTS.md` the dry run plans the region as a *create* of a region-only file
and the real run re-plans it as a *region_update* into the skeleton the first pass has just
written; the report carries one fixed sentence saying the bytes inside the markers are the same
either way.

| id | pass | kind | target | what it holds |
|---|---|---|---|---|
| `config` | write-once | once | `stayfixed.toml` | the document this run rendered |
| `agents-skeleton` | write-once | once | `[paths] agents_md` | a skeleton headed with the project's name, stating this project's own budgets |
| `claude-md` | write-once | once | `CLAUDE.md` | a one-line pointer at `[paths] agents_md`, whatever that file is called |
| `documentation-policy` | footprint | template | `<architecture>/documentation.md` | where each kind of fact belongs |
| `adr-template` | footprint | template | `<adr>/0000-template.md` | the four-heading decision record |
| `ledger-runbook` | footprint | template | `<runbooks>/bug-reports.md` | how to file, close and reference an entry |
| `ledger-audits` | footprint | template | `<bugs>/audits/README.md` | what an audit record is |
| `bug-index` | footprint | template | `[paths] bug_index` | the generated index, rendered empty |
| `roadmap` | footprint | template | `[paths] roadmap` | `Now`, `Next`, and the trail block |
| `roadmap-history` | footprint | template | `[paths] roadmap_history` | an empty history |
| `trail` | footprint | template | `trail.toml` beside the roadmap | one theme, no declared states |
| `specs-keep`, `plans-keep` | footprint | template | `<specs>/.gitkeep`, `<plans>/.gitkeep` | nothing, so the trail lists no documents |
| `gitignore` | footprint | managed region | `.gitignore` | the same block `attach` writes |
| `agents-md` | footprint | managed region | `[paths] agents_md` | which paths this repository's stayfixed uses |
| `ci-workflow` | footprint | template | `.github/workflows/stayfixed.yml` | the pinned call to the reusable gate |
| `profile-rules` | footprint | template | `<stayfixed>/rules/<profile>.md` | the profile's rules, the one copy a project edits; only with `[stayfixed] profile` set |
| `claude-rules` | footprint | template | `.claude/rules/stayfixed-<profile>.md` | a `paths:`-scoped pointer at `profile-rules` for Claude Code; only when `[stayfixed] agents` lists `claude` |

With a profile set, the `agents-md` region also names the profile's rules file and lists the
lines under its *Before the first command* heading, so every harness that reads `AGENTS.md` has
them before its first command. A name in `[stayfixed] agents` that no harness answers to is
counted in a `note:` line and never printed.

**`--local` offers four files.** `documentation-policy`, `adr-template`, `ledger-runbook` and
`roadmap-history` may be kept out of git, under `.stayfixed/local/artifacts/`, and every gate
still passes. The others are not offered:
- `bug-index`, `ledger-audits`, `roadmap` and `trail` are read by a gate at their committed
  paths. The index would read as stale, the ledger directory would be missing, the roadmap
  absent, and a trail kept out of git would be silently ignored.
- `specs-keep` and `plans-keep` have no purpose outside git.
- `config` and `gitignore` work only at the root.
- `CLAUDE.md`, the `AGENTS.md` skeleton and its region, the workflow, and the profile's rules
  and Claude's pointer are read where they are committed.

A `stayfixed.toml` you write may still list any id but `config`, `gitignore` and the profile's
own. `--local` offers only these four.

**The workflow pins what `[ci] ref` says, and nothing else.** The rendered file calls
[the reusable workflow](#the-reusable-workflow) at the ref `stayfixed.toml` carries *after this
run*, and those two are one value by construction — which is the invariant `stayfixed doctor`'s
`ci-ref` row enforces from the other side ("the workflow pins a different ref from `[ci] ref`,
so the gate that runs is not the one recorded"). On a repository this run creates the document
for, the ref is the commit of the stayfixed release running, asked of the public repository's own
`v*` tags and written into `[ci] ref` beside the workflow. On a repository that already had a
`stayfixed.toml`, that document's `[ci] ref` is not rewritten — all `init` may add there is a
missing `[stayfixed] version`, with its `[stayfixed]` header when the file has none — so the workflow
pins the ref **it** records, and `doctor` judges whether that is a released commit, which is its
job.

Seven states cost the artifact rather than the run, each reported under `skipped` with one
sentence: `[ci] mode` is `none`; `[ci] mode` is `uvx`, whose form of the gate has not shipped; the
public repository could not be asked for its tags; no released tag matches the stayfixed running,
which is every repository's state before the first release; the `stayfixed.toml` this repository
already had records no `[ci] ref`, so there is nothing a workflow could pin that anything records;
`[ci] ref` is not a full-length commit sha, which is the only immutable form and the only one
`init` renders — the mutable `v1` alias, from `1.0.0` on, is a file you write by hand, and until
then a `0.x` project pins the commit; and `[ci] gate_branch` is not a plain branch name. `--no-ci`
is the first of those on purpose: it puts `[ci] mode = "none"` into the document this run builds
and asks no remote anything. **On a repository that already has a `stayfixed.toml` the flag governs
this run and nothing more** — that document is a create-once artifact, reported `skip_modified`, so
the file still says whatever it said and the next `init` would ask the remote again. Writing `none`
there is yours to do.

**The two states about the remote are reported only on a run that creates the document.** On the
adoption path the answer is the fifth one whatever the remote said, because it is the whole
reason: a pin this run resolved would be written into a create-once file that is already there,
so nothing would record it. Reporting "run `stayfixed init --yes` again with the network
reachable" there would send you back to a command that cannot help — by the time you read it,
`.stayfixed/manifest.json` exists and `init` refuses to run again at all. `stayfixed upgrade` is
the command that can: `[ci] ref` is one of stayfixed's keys in any `stayfixed.toml`, so it records
a released commit there in place and renders the workflow around it. On a run that created the
document, the unreachable remote's sentence names both remedies: `stayfixed init --yes` with the
network reachable while nothing is written yet, and `stayfixed upgrade` once it is.

**Reads** `stayfixed.toml` when there is one, `.stayfixed/manifest.json`, `git` for the name
and the base branch and for the public repository's tags, which harness directories the root
carries (`.claude/`, `.codex/`), each shipped profile's marker files at the root, every file
an artifact targets, and `git check-ignore` for each existing file a write targets at a place
a `[paths]` value chose.

**Writes**, every one of them through the scaffold engine or `stayfixed.toml`'s key editor, so
that every target goes through the containment walk and none may leave the project root or
pass through a symlink:
- `stayfixed.toml`, or only its missing `[stayfixed] version` when you wrote it;
- `CLAUDE.md`, `[paths] agents_md` and `.gitignore`;
- the documents in the table above (the profile's rules only when a profile is set, and the
  Claude pointer only when a profile is set and `[stayfixed] agents` lists `claude`), each at its
  place in the table, except that a document `[artifacts] local` lists is written under
  `.stayfixed/local/artifacts/` at that place instead;
- `.github/workflows/stayfixed.yml`, where a ref is recorded;
- `.stayfixed/manifest.json`;
- `.stayfixed/local/artifacts.json`, when `[artifacts] local` lists anything.

Exits `0` on success. `1` on a finding: either plan carries refusals — the report's REFUSED section
names each, nothing was written and no manifest exists — or a `stayfixed.toml` that cannot be read,
is not UTF-8 text or is not valid TOML, or the merged document the loader itself refuses (an unknown
section or key, a `[project] name` outside its grammar, a value of the wrong type, a machine
configuration file that does not load), or a `stayfixed.toml` you wrote that, with its version, the
loader would refuse on the next command's load. `2` on a refusal above the plans: no `--yes`, an
answer flag over an existing `stayfixed.toml`, an answer outside its grammar or its choices (from the
parser), a repository already initialised, a detected name outside the grammar that no `--name`
answers, a `[stayfixed]` table the key editor cannot add a version to, a `stayfixed.toml` that is a
symlink, which is never followed, a `[paths]` value outside the plain-path grammar, naming git's
control directory or stayfixed's own `.stayfixed/`, or reaching through a component that is a symlink
— all three refused by the loader before a plan exists — two artifacts, of one pass or of either,
that resolve to one file (`roadmap` and `roadmap_history` set to one path, or `roadmap =
"CLAUDE.md"`), which is named with the two artifacts and their `[paths]` keys to separate, since
only the `AGENTS.md` skeleton and its region share a file by design, an `[artifacts] local` list
naming a profile artifact, which every pointer at it reads at its committed path, one naming
`config` or `gitignore`, which only work at the repository root, and a write git would hide, at an
existing file a `[paths]` value chose, which the refusal names, or one git cannot answer for inside
a repository because it timed out or is not installed (see `upgrade`'s boundary).

`--json` carries `dry_run`, `adopted`, `once` and `footprint` (each the plan's own rendered
report), `writes` (both plans' targets), `skipped`, `pin` (the release this run resolved,
`{tag, sha}` or `null`), `asked`, `note`, `ref` — what `[ci] ref` says on disk after the run
and so what the workflow pins, empty when no workflow was planned — `stamped`, whether this
run's plan adds `[stayfixed] version` to a `stayfixed.toml` you wrote — written only by a run that
is neither a dry run nor refused — `unknown_harnesses`, how many names in `[stayfixed] agents` no
harness answers to, and `head_note`, the `note:` line that says `main` replaced an
`origin/HEAD` outside the plain-branch grammar (the branch it named is never printed), that
`main` stands because a remote is there and no `origin/HEAD` is recorded, or because git could
not list the remotes, or that, with no remote, the branch checked out other than `main` became
the base branch; empty otherwise. An answered `--base-branch` replaced nothing, so it leaves
`head_note` empty.
`custom_gates` lists the custom gates a `stayfixed.toml` you wrote configures, by name, and is empty
when this run writes the file.

---

## `stayfixed init --questions [--root PATH] [--machine PATH]`

Prints the values `stayfixed init --yes` would take for the six things a person may answer, where
each came from, and the flag on `init --yes` that replaces it. It writes nothing. The `init` skill
asks its questions from it, and a person reads it to see the defaults before choosing any.

The summary is one line per question, `<key>: <default> (<where it came from>; <flag>)`, then
one line saying how each is answered:

```text
detected:
  project.name: widget (origin remote; --name)
  project.base_branch: main (origin/HEAD; --base-branch)
  stayfixed.agents: claude, codex (default; --agent)
  stayfixed.profile: python (profile markers; --profile)
  memory.mode: local-only (the preset's default; --memory-mode)
  artifacts.local: none (the preset's default; --local)
each is answered by the flag its line names, on `stayfixed init --yes`; `stayfixed init --questions --json` carries them as a JSON Schema
```

Where a value came from is one of a fixed set of phrases. The name comes from the
`origin remote`'s last path segment or, with no origin, the `directory name`; when that one is
not a lowercase path segment the source is `not derivable`, and the value prints as
`none; asked`, never as what the repository suggested. The base branch comes from `origin/HEAD`
when that names a plain branch under `refs/remotes/origin/`; with no remote at all, from the
`current branch` when that is a plain branch; otherwise, a remote with no `origin/HEAD` and
remotes git could not list included, it is the `default`, `main`. The agents come from the `harness
directories` the root carries; otherwise the `default` is every harness. The profile comes from
`profile markers`, or there are `no profile markers`. The memory mode and the files kept out of
git are `the preset's default`. Each default is exactly what `stayfixed init --yes` writes when
that question is not answered. `origin/HEAD` goes stale after the remote's default branch is
renamed, because git does not refresh one it has. That is why its source is printed: you can
catch it.

`--json` carries `questions`: a JSON Schema object (draft 2020-12) with six required
`properties`. Each is keyed by the `stayfixed.toml` key its answer writes: `project.name`,
`project.base_branch`, `stayfixed.agents`, `stayfixed.profile`, `memory.mode` and
`artifacts.local`. Each property carries three keys: `default` (absent for a name that is not
derivable), `x-stayfixed-source` (the phrase above) and `x-stayfixed-flag` (the `init --yes` flag
that answers it). A choice is a `oneOf` of `const` and `title`, or `items.enum` for a list. The
two free-text properties carry `pattern`, the grammar their flag enforces.

The schema is modelled on MCP elicitation's flat form schema. A client may send it as a
`requestedSchema` once it drops `pattern` and the `x-stayfixed-*` keys, which that subset does not
carry. Harness ask tools take lists of questions and options rather than a schema, so the `init`
skill turns the properties into questions: the first four as one confirmation of their defaults,
the rest one at a time, within each harness's limits. The flags validate the answers; the schema
does not.

It is refused (`2`) before anything beyond the root is read, in three cases:
- the repository already carries `.stayfixed/manifest.json`: re-running `init` is
  `stayfixed upgrade`;
- it carries a `stayfixed.toml`, which answers these questions itself: edit it, then read the plan
  with `stayfixed init --yes --dry-run`;
- any flag is given but `--root`, `--machine` and `--json`.

`--yes` beside it is a usage error from the parser.

**Reads** `git` for the name and the base branch, which harness directories the root carries, each
shipped profile's marker files at the root, and the machine configuration, to learn whether it
records an overlay. A machine file that does not load reads as "not recorded"; `init` reports it
when it loads it.

**Writes** nothing.

Exits `0` with the questions printed; `2` on a refusal.

---

## `stayfixed upgrade [--dry-run] [--force PATH]… [--root PATH] [--machine PATH]`

Refreshes a repository's footprint after a stayfixed update, keeping every hand edit. It moves
`[stayfixed] version` to the stayfixed running, re-plans every footprint artifact against
`.stayfixed/manifest.json` by hash, and never re-plans the write-once files: `stayfixed.toml`,
`CLAUDE.md` and the `AGENTS.md` skeleton are yours after `init`.

`--dry-run` reports everything and writes nothing. `--force PATH` overwrites or removes one file the
report named `skip_modified`, as a path relative to `--root` exactly as the report prints it; repeat
it for each file. It reaches a file you edited, one stayfixed never wrote, and a changed or
unrecorded copy under `.stayfixed/local/artifacts/`, but not a file left at an artifact's old place
(`relocated and hand-edited`, or a recorded target the artifact cannot produce): that one is yours
from then on, to keep or delete by hand. A leading `./` is dropped, and an absolute path or one with
a `..` component is refused (`2`) naming the rule. A forced path no planned action names — a typo, a
case difference, or a file with nothing to force — is counted in a `note:` line and forces nothing.

**Four verdicts.** A file whose bytes are still the ones the manifest records is refreshed
(`update`, or `region_update` for a managed region) when this stayfixed renders it differently,
and reported `unchanged` when it does not. One that is missing is created. One you edited is
`skip_modified` and named, and stays as it is until `--force` names it. So is a file stayfixed
never wrote at a path it would write (`exists and stayfixed did not write it`); forced, it is
overwritten and recorded, and later runs judge it like any file stayfixed wrote. An artifact this
configuration no longer produces is removed while its bytes are the ones recorded (`remove`),
and skipped the same way when they are not. One whose file is already gone is listed
`remove … (retired, already gone)`: nothing is removed, and its record is dropped, so it is not
carried into every later run.

**What is rewritten in `stayfixed.toml`, and what is not.** Only the values stayfixed owns:
`[stayfixed] version` and, under `[ci] mode = "reusable"`, a `[ci] ref` that is a commit sha or
empty. Every other byte stays where it was — comments, order, blank lines, your keys. A key written
in a shape the editor does not rewrite in place (a dotted key, an inline table, a multi-line value)
is refused (`2`) naming the key and the line to write by hand, before anything is written. When the
manifest's `config` record still describes the file, it is re-stamped with the new bytes; when you
have edited the file, it is not, so `stayfixed.toml` stays yours.

**Version, `[ci] ref` and the workflow's pin move together or not at all.** Under
`[ci] mode = "reusable"` the workflow pins stayfixed by commit, so `[stayfixed] version`, `[ci] ref`
and the `uses:` line in `.github/workflows/stayfixed.yml` are one value. When no released commit
of the stayfixed running is found — before its tag exists, or with the network unreachable — or
when the workflow would not be rewritten to the new pin, neither key moves: a `note:` line says
`[stayfixed] version` and `[ci] ref` were left as they are and why, and the rest of the footprint
is still refreshed. A workflow you edited by hand, or one stayfixed never wrote, is reported
`skip_modified` and moves with them only under `--force` with the path the report prints for it.
When the report refuses the workflow, or the `CI:` line says none was rendered (a `[ci]
gate_branch` outside the branch-name grammar, say), no flag moves them: the note says to put
that right and run `stayfixed upgrade` again. The `CI:` line says the workflow pins `[ci] ref` only
when this run created it, refreshed it or found it current; a workflow the report lists
`skip_modified` or refuses was left as it is and may pin anything, and the line says so.

**A `[ci] ref` that is not a commit is yours.** The `v1` alias, documented from `1.0.0` on, or any
other value that is not a full-length sha, is a choice to track a moving stayfixed, so `upgrade`
moves `[stayfixed] version` alone: it never replaces that ref with a sha, and never renders a
workflow over the one you wrote around it. The `CI:` line says no workflow was rendered around the
ref.

**A project recording a newer stayfixed is refused** (`2`), before anything is written: an older
plugin would repin an older release and put older bytes over newer ones. The recorded version is
read by its leading `X.Y.Z` first, so `1.0.0-rc1` is newer than a running `0.9.0`; with the same
`X.Y.Z`, a release is newer than its own pre-release, so a project recording `1.0.0` is refused
by a `1.0.0rc1` build. Update the stayfixed plugin, then run `stayfixed upgrade` with it; never edit
`[stayfixed] version` to get past it. A recorded version with no leading `X.Y.Z`, such as
`v1.0.0`, is refused too, because which way a move would go is unknown; set it to the release
the project was last upgraded with. So is one sharing the running `X.Y.Z` and differing after it
in a way stayfixed does not order — two pre-releases, such as `1.0.0rc1` and `1.0.0rc2`, or a
post-release — and that refusal names the version running: set it to that by hand if it is the
release the project should move to.

**An artifact kept out of git is recorded out of git too.** One listed in `[artifacts] local` lives
under `.stayfixed/local/artifacts/`, and the committed manifest never records it; instead
`.stayfixed/local/artifacts.json`, which the ignore block keeps out of git like the artifacts,
records the bytes stayfixed last wrote there. A file still holding those bytes is refreshed like any
other when this stayfixed renders it differently. One that no longer does is `skip_modified`
(`kept out of git, and changed since stayfixed wrote it`), because nothing brings it back once it is
overwritten, and `--force` with its path takes it; with that record gone, a file that is not exactly
what this build writes is skipped the same way, saying nothing records what stayfixed wrote there.
When an id leaves `[artifacts] local`, or its `[paths]` value moves while it stays there, the
artifact is written at its new place and the copy the record names at the old one is removed while
it holds exactly the bytes recorded for it (`relocated`); otherwise it is `skip_modified`, stays
recorded until it is gone, and `--force` with its path takes it. The record is read as untrusted,
since a clone can commit it anyway: anything but its own exact shape is read as no record at all, it
is never printed, it names nothing outside `.stayfixed/local/artifacts/`, and it vouches only for a
file there whose bytes are exactly the ones it states.

**Retirement.** An artifact this configuration no longer produces — the profile's rules after
`[stayfixed] profile` changes, its Claude Code pointer after `agents` drops `claude` — is removed
only at a target this build could have written for it, and only while its bytes are the ones
recorded. The workflow is removed only when `[ci] mode` is `"none"`; a mode this build does not
render, such as `uvx`, is not a request to delete the gate. Every other record in the manifest is
counted in a `note:` line and left where it is, and never named, as is a record saying its
artifact lived inside a file (a region) that this build no longer produces: a region comes out
only through the template that names it, never as a whole file, which is `uninstall`'s rule too.

**The boundary.** Which artifacts exist, and where each could be, are this build's. The `[paths]`
value a target is built from and the digest a record carries are committed. For a whole file, a
commit can make `upgrade` rewrite it only while it holds exactly the bytes the same commit records,
`--force` aside: that overwrites a whole file whatever it holds, one nothing records included, but
only at a path given exactly on the command line, which no commit can supply. A managed region is
inserted into whatever file its key names: a commit that points `[paths] agents_md` at another
tracked file gets the region written into that file, and the diff shows both the edit and the
region. No `[paths]` value may name git's control directory or stayfixed's own `.stayfixed/`, where
attach's ledger and the local-only notes live out of git's sight; the loader refuses either, naming
the key. And a committed `[paths]` value cannot put a write or a removal where git would hide it:
the run is refused (`2`) before anything is written, dry run included, when all three of these hold
for a file it would write or remove — the file exists, git ignores it, and it is at a place a
`[paths]` value chose rather than where the preset puts that artifact. The refusal names each such
file, as the report prints paths, and says to point the key at a path git does not ignore or take it
out. A new file, a fixed name (`CLAUDE.md`, `stayfixed.toml`, `.gitignore`, the workflow, a harness's
rule) and a preset's own place are never refused, so a `CLAUDE.md` in your global excludes or a
`stayfixed.toml` in `.git/info/exclude` works as before. A tracked file that matches an ignore
pattern is not ignored, because git shows every change to it; the artifacts `[artifacts] local`
keeps under `.stayfixed/local/artifacts/` are exempt, since keeping them out of git is what that
setting asks for; and outside a git work tree there is no guard, because there is no diff to hide
from. Inside one (a `.git` in the root or a directory above it), a `git` that cannot answer, because
it timed out or is not installed, refuses the run rather than letting it through. Run it on a
checkout you trust. There are no hooks to re-trust afterwards: `init` writes no project-level hook
entries, so an upgrade changes none.

**Reads** `stayfixed.toml`, `.stayfixed/manifest.json`, `.stayfixed/local/artifacts.json`, every
file an artifact targets, `git check-ignore` for each existing file a write or removal targets at
a place a `[paths]` value chose, and, under `[ci] mode = "reusable"`, the public repository's
tags.

**Writes** the footprint through the scaffold engine — every `create`, `update`, `region_update`,
`remove` and `relocated` in the report, and each file `--force` takes — then
`.stayfixed/manifest.json`, the committed record, written even when a write or removal fails
part-way, and `.stayfixed/local/artifacts.json`, the record kept out of git, only when what it
records changed; then `stayfixed.toml`, last (with `.stayfixed/manifest.json` again when its
`config` record is re-stamped), so the version is the commit point: a run interrupted before it
leaves the old version recorded, and the next run re-plans from there. Under `--dry-run`,
nothing.

Exits `0` when it applied the plan or there was nothing to do. `1` on a finding: the plan carries
refusals — the report's REFUSED section names each, and nothing was written — or a `stayfixed.toml`
that does not load, as for every command. `2` on a refusal before any write: the repository is not
initialised, `stayfixed.toml` is missing, it records a newer stayfixed, a version with no leading
`X.Y.Z` or one stayfixed does not order against the running one, a key is written in a shape the
editor refuses, two artifacts resolve to one file (named by artifact and `[paths]` key, as `init`
names it), a profile artifact, `config` or `gitignore` is listed in `[artifacts] local`, git ignores
(or inside a repository cannot say whether it ignores) an existing file the run would write or
remove at a place a `[paths]` value chose, or a `--force` path leaves `--root`. `2` also when a file
cannot be written or removed part-way through; what was already applied stays applied and recorded,
and running the command again re-plans from there.

`--json` carries `dry_run`, `moved` (each `{key, before, after}`; a `before` outside its grammar
prints as `(not a version)` or `(not a commit)`), `held` (the note's sentence, or empty),
`footprint` (the plan's rendered report), `writes`, `skipped`, `orphans` (a count), `pin`
(`{tag, sha}` or `null`) and `asked`.

---

## `stayfixed uninstall [--dry-run] [--force PATH]… [--root PATH] [--machine PATH]`

Takes back what `init` and `upgrade` wrote. A file whose bytes are still the ones the manifest
records is removed; stayfixed's managed regions come out of files that hold other text, and such a
file goes too only when nothing else was in it; the ledger goes last. A file you edited stays
where it is, is reported `skip_modified` with its reason, and is counted in a `left in place`
line. Every recorded artifact is judged, including one this configuration no longer produces, at
a target this build could have written for it, whatever `[ci] mode` says now: the workflow goes
under `uvx` too. Any other record is counted in a `note:` line and left where it is, and never
named, as is a record saying its artifact lived inside a file (a region) that this build no longer
produces: a region comes out only through the template that names it, never as a whole file.

`--dry-run` reports everything and writes nothing. `--force PATH` removes one file the report named
`skip_modified`, as a path relative to `--root` exactly as the report prints it; repeat it for each
file. It reaches what `upgrade`'s `--force` reaches, and likewise not a file left at an artifact's
old place (`relocated and hand-edited`), which is yours to keep or delete by hand. The path rules
are `upgrade`'s: a leading `./` is dropped, an absolute path or one with a `..` component is refused
(`2`), and a forced path no planned action names is counted in a `note:` line and forces nothing.

**Two passes, the footprint first.** The footprint pass removes files and takes the regions out;
a region taken out of a file that keeps other text is reported as
`remove  AGENTS.md  (retired; stayfixed's part only, the file stays)`, and a line without that
tail means the file itself goes. Every command that prints a plan says it the same way.
The write-once pass (`stayfixed.toml`, `CLAUDE.md` and the `AGENTS.md` skeleton) is planned again
after it, so the skeleton is judged once stayfixed's region has left `AGENTS.md`: untouched, it is
byte for byte what `init` wrote and goes. A dry run cannot take the region out first, so it
judges the skeleton with the region still in it and calls it edited; a `note:` line says so.
**Forcing `AGENTS.md` takes stayfixed's region out of it and never the skeleton**: a forced path
the footprint pass targets never reaches the write-once pass, compared as the engine places each
file, so what you wrote into the skeleton is judged on its own bytes.

**The ignore block goes last, and only over an empty `.stayfixed/local/`.** The `.gitignore` region
is what keeps `.stayfixed/local/` out of git: attach's ledger, the local-only memory notes, and the
artifacts `[artifacts] local` keeps out of git. So it is taken out in a pass of its own, after the
disk shows nothing left under `.stayfixed/local/`. Every directory above a file a pass removed goes
once it is empty, deepest first, and so does every empty directory under
`.stayfixed/local/artifacts/`, stayfixed's own, which no `[paths]` value reaches; no other goes: an
empty directory a `[paths]` value merely names may be yours. Then `stayfixed.toml`, which the
write-once pass holds back for this point; then the ledger: `.stayfixed/assessment.json`,
`.stayfixed/manifest.json`, and `.stayfixed/local/` and `.stayfixed/` once each is empty. A directory
someone committed where a ledger file belongs stays. So does a harness's own directory
(`.claude/`, `.codex/`, or the same name in any other case), even when it is empty, whoever made it:
`init` may have created `.claude/` to hold the rule it wrote there, but nothing records who made an
empty directory, and to `init` its presence means the project uses that harness. So a later `init`
detects that harness and lists it in `[stayfixed] agents` until you remove the directory.

**Refused before any write** (`2`): the repository is not initialised; it is attached to an overlay,
so run `stayfixed detach` first; `stayfixed.toml` is missing while the manifest records it, so restore
it; `[artifacts] local` names `config` or `gitignore`, which only work at the repository root, so
take them out of the list; two artifacts resolve to one file, named as `init` names it;
`.stayfixed/local/` holds files this run would not remove, such as notes, or an artifact kept out of
git that changed since stayfixed wrote it, which the refusal counts and never names; git ignores an
existing file the run would remove or rewrite at a place a `[paths]` value chose, which the refusal
names; or a `--force` path leaves `--root`. The count is exact before anything is written, including
what taking a region out of a file kept out of git would leave behind; the record of what stayfixed
wrote there, `.stayfixed/local/artifacts.json`, is stayfixed's own and goes once nothing else is left,
before the ignore block. Every artifact it records is judged, a copy left behind when its id left
`[artifacts] local` or its `[paths]` value moved included, so an unedited one goes. Move the files
out; one the report lists `skip_modified` in a file of its own there can be named with `--force`
instead, but an `AGENTS.md` whose region and skeleton are both kept out of git shares one file, and
forcing it takes only the region, so a line you wrote into that skeleton has to be moved. A dry run
reports the count in a `note:` line instead of refusing, even when its plans also carry refusals, so
its report still lists the edited file.

**Refused part-way** (`2`): a file that cannot be written or removed, or files still under
`.stayfixed/local/` after the write-once pass, which the count before any write should already have
refused; move them out. What was removed stays removed and recorded, and `stayfixed.toml` and the
manifest are still there, because they go last, unless the last pass removed `stayfixed.toml` and
then could not write the manifest, which the next paragraph covers; so running the command again
finishes from what the first run left, to the same end as a run that was never stopped.

**Without `stayfixed.toml`, nothing the manifest records can be judged.** While the manifest still
records the file, the run is refused (`2`) before any write, dry run included: restore
`stayfixed.toml` (from git, for instance) and run it again. This command drops that record as it
removes the file, so the file was taken by something other than this command, or by a run of it that
removed the file and then did not rewrite the manifest, because it was killed in between or the
manifest could not be written; either way the restored file is judged like any other, and the run
then goes on to the end. When nothing records it — a run stopped between removing it and removing
the manifest, or a `stayfixed.toml` the project wrote itself before `init`, which `init` never
records — every recorded file stays, a `note:` line gives their count, and only the ledger goes, so
`init` and this command no longer refuse the repository. No other directory is pruned then, because
nothing says where the configuration put its artifacts. A `stayfixed.toml` you wrote before `init`,
which is there and recorded nowhere, is left as it is, with the keys stayfixed wrote into it; a
`note:` line says so, and `--json` carries `kept_config: true`.

**The boundary.** Which artifacts exist, where each could be and every region's name are this
build's. The `[paths]` value a target is built from and the digest a record carries are committed,
so a commit can make `uninstall` remove a whole file only while it holds exactly the bytes the same
commit records, and a region only where its key names; the diff shows both. No `[paths]` value may
name git's control directory or stayfixed's own `.stayfixed/`, and a symlinked `.stayfixed/` is
refused. An existing file git ignores at a place a `[paths]` value chose is never removed or
rewritten: the run is refused (`2`) before any removal, dry run included, by `upgrade`'s rule,
naming the files, and so is a run inside a repository whose `git` cannot answer because it timed out
or is not installed. Take stayfixed's part out of them by hand, or take the `[paths]` key out of
`stayfixed.toml`; the run then leaves those files where they are and lists them. That includes a file
stayfixed itself created at an ignored place a `[paths]` value chose (`roadmap = "build/roadmap.md"`
under an ignored `build/`, say): creating it was allowed because nothing was there, and by the time
`uninstall` runs it exists, so this refusal meets it, and taking the key out is the remedy that
finishes the run. A `CLAUDE.md` or `AGENTS.md` your own excludes ignore is taken back like any
other. Run it on a checkout you trust.

**Reads** `stayfixed.toml`, `.stayfixed/manifest.json`, `.stayfixed/local/artifacts.json`, every file
an artifact targets, `git check-ignore` for each existing file a removal targets at a place a
`[paths]` value chose, and what is under `.stayfixed/local/`.

**Writes** only removals, and region removals, through the scaffold engine, and after each pass
the two records of what is left: `.stayfixed/manifest.json`, which every pass rewrites, whether or
not it finished, and `.stayfixed/local/artifacts.json`, the record kept out of git, which a pass
rewrites when it removed something that record names. Each pass also removes every directory
above a file it removed, once that directory is empty. After the write-once pass it removes
`.stayfixed/local/artifacts.json` and then prunes the empty directories it finds by walking
`.stayfixed/local/artifacts/`, deepest first, that directory included; after the last pass, the
ledger: `.stayfixed/assessment.json`, `.stayfixed/manifest.json`, then `.stayfixed/local/` and
`.stayfixed/`, each once it is empty. A harness's own directory is never removed. When
`stayfixed.toml` is gone and nothing records it, only the ledger is removed. Under `--dry-run`,
nothing.

Exits `0` when it applied the plans, including when every recorded file was edited and nothing
was removed but the ledger. `1` on a finding: a plan carries refusals — the report's REFUSED
section names each, and nothing was removed — or a `stayfixed.toml` that does not load. `2` on the
refusals above, before any write or part-way; a repository with no `.stayfixed/manifest.json` is
one of them.

`--json` carries `dry_run`, `footprint` and `once` (each the plan's rendered report), `left` (the
files left in place, each as the reports print it), `orphans` (a count), `note` (the dry run's
order note, or the missing-configuration count, or empty) and `kept_locally` (how many files
under `.stayfixed/local/` the run would leave, on a dry run and on a run whose plans refuse; `0` on
a run that removed what it planned).

---

## `stayfixed overlay create --owner OWNER [--name NAME] (--template | --local) [--root PATH]`

Creates the private overlay: the repository that holds your standing rules, your cross-project
notes, and one record per repository bound to them. Nothing in it is any project's, which is why
it is a repository of its own and why it is private.

`--owner` is the account it belongs to and `--name` the repository name (default
`stayfixed-private`). Both are held to one path segment matching `[a-z0-9][a-z0-9._-]*`, because
each becomes a directory name, half a remote path and later a marketplace selector; a value
shaped like an option is refused rather than quoted. `--root` is the directory the instance is
created *in*, not a project root, and defaults to the current directory.

**Neither source is a default.** `--template` asks GitHub to generate a private repository from
a template repository and clone it; `--local` renders the shipped template here, makes a git
repository of it, and makes no network call. An invocation with neither is refused (`2`) naming
both, so that creating a repository on an account is never something an omitted flag does.

**`--template` uses your template when you have published one, and the publisher's otherwise.**
It asks `gh repo view <owner>/stayfixed-overlay-template --json isTemplate` once. A template
there is generated from, and it is the one
[`stayfixed overlay publish-template`](#stayfixed-overlay-publish-template---owner-owner---name-name---yes)
publishes to your account. A repository of that name that is not a template, and `gh`'s explicit
answer that there is no such repository, both mean you have published none, and the template is
`github.com/stayfixed/stayfixed-overlay-template`, the publisher's public copy, named with its
host: `gh` looks an unqualified name up on `GH_HOST`, so on a GitHub Enterprise host
`stayfixed/…` would be whoever owns that name there, while your own template's question stays on
your host. The result names the template it used. Any other failure of that question — an expired token, a network error, a
`gh` that is not installed or hung, an answer that is not the JSON asked for — stops the command
with `gh`'s own message and creates nothing (`1`): it is not known whether you have a template of
your own, and guessing "no" would generate your overlay from somebody else's. `--local` renders
exactly the same tree here with no network call, so an owner setting up a first overlay can use
either. `stayfixed setup --overlay create:<owner>/<name>` makes the same choice.

A template and not a fork: a fork's visibility is bound to the upstream network and cannot be
made private, which is the one outcome this command exists to prevent.

The `--template` path is idempotent, because `gh` can give up on the clone with the repository
already created: a directory that already carries `.claude-plugin/` is left alone and reported,
before `gh` is asked anything. When the template question or `gh repo create` itself fails, the
command stops there and reports **its** exit code and **its** stderr: a `gh` that is not installed,
or one that hung, costs one launch rather than three, and the failure names the binary rather than
sending you to `gh auth status` for a repository that was never there. It also names which
template repository each source uses, because a template that does not exist yet is the usual
reason this source cannot work. When `gh` reports success and the clone brings nothing down,
`gh repo view` is asked whether the repository exists at all — the answer tells "not created"
from "created, and the clone raced its generation" — and the clone is retried once, after a
ten-second wait when it was the second. **That retry is carried on reasoning rather than on a
measurement:** the one trial run against it did not reproduce the race, and one clean run cannot
rule out an asynchronous generation step that sometimes outlasts a clone. If the second attempt
is still empty, the command fails (`1`) naming both attempts and what GitHub said in between.

**`--local` leaves a git repository.** After rendering, it runs `git init` and
`git symbolic-ref HEAD refs/heads/main` in the instance directory (not `git init -b main`, which a
`git` older than 2.28 refuses) and prints the two commands that give it a remote once you have
created the private repository on GitHub: `git remote add origin git@github.com:<owner>/<name>.git`
and `git push -u origin main`. A `git` that cannot run, or that runs and fails, is a note, not a
failure: the tree is there, and the note says how the command ended and the commands to run. An
instance directory that is already a git repository is left as it is — no `git init`, its branch
and remotes unchanged — and the note says so. `pre-commit install` is `overlay init`'s.

What `gh`, `git` and `pre-commit` print is quoted in these lines as it came, except that one
holding anything but a plain path is escaped, so a line break or an escape sequence in it cannot
start a line of its own or drive a terminal, and one longer than 120 characters is cut to its
first 120 and its length.

**Writes**, on `--local`, the instance directory `<root>/<name>` with every file of the template
plus `.stayfixed/manifest.json`, and `<root>/<name>/.git`, the repository `git init` makes there
when there is none yet. On
`--template`, through `gh repo create <owner>/<name> --private --template <template> --clone`, where
`<template>` is `<owner>/stayfixed-overlay-template` or
`github.com/stayfixed/stayfixed-overlay-template` as above, a new private repository on GitHub under
`<owner>` and its clone at `<root>/<name>` — or, when that clone brings nothing down, a clone
from the retried `git clone`; a directory that already carries `.claude-plugin/` gets nothing.
A template published at an earlier release also brings the files that release shipped and this
one does not — `common/memory/README.md` from 0.1.x, `skills/attach/SKILL.md` and
`common/rules/README.md` from any — which `overlay init` removes (below). Exits `0` on success, `1`
when no tree arrived, `2` on a refused name or a missing `--root`.

---

## `stayfixed overlay init --owner OWNER [--root PATH]`

Makes a created overlay yours. It rewrites all three manifests — `.claude-plugin/plugin.json`,
`.claude-plugin/marketplace.json` and `.codex-plugin/plugin.json` — so their names carry your
account (`stayfixed-overlay-octocat`, `stayfixed-overlay-marketplace-octocat`), because a harness
installs a plugin by the name in its manifest, and two owners' overlays under one configuration
directory would otherwise be one plugin fighting itself; the Codex half is included for the same
reason as the other two. The marketplace's own plugin entries are suffixed with it, so the
listing still names a manifest that answers. A manifest this overlay does not carry is reported
and skipped, not a failure.

It also puts your account where the harness asks for one: the marketplace's `owner` (without it
`claude plugin validate` refuses the marketplace) and each plugin manifest's `author`, as
`{"name": "<account>"}`. Only where nobody has put a name: the template's placeholder is replaced
and an absent key is added, so an overlay generated from an older template becomes valid, but a
name you wrote yourself, and anything else beside it, stays.

**Installing the overlay as a plugin is two commands**, with the names this command produced
(`<owner>` is your account and `<name>` the overlay repository's name), and nothing runs them for
you:

```bash
claude plugin marketplace add git@github.com:<owner>/<name>.git
claude plugin install stayfixed-overlay-<owner>@stayfixed-overlay-marketplace-<owner>
```

A rewrite of a manifest that still held what stayfixed wrote there is re-stamped into
`.stayfixed/manifest.json`, so `overlay upgrade` still sees the file as stayfixed's own: without
that, the file carrying `stayfixed.requires` read as hand-edited from the moment you ran `init` and
no release could ever refresh it again. A manifest you edited is renamed all the same, but its
record is left as it was, so `overlay upgrade` goes on listing it as hand-edited and never
refreshes your edit away. Every manifest is read before any is rewritten, so one that cannot be
read stops `init` with none of them changed. One it reads and then cannot write is named with a
`<path> cannot be written: <reason>` line and left as it was, record included; the others are
renamed and recorded all the same, and the next run names the one left.

It then runs `pre-commit install` in the overlay, which is one of the two secret scans the
template ships; the other is the workflow that runs on every push, so `--no-verify` is not the
last word. `pre-commit` is optional: a missing or failing one is a reported note and never a
traceback.

Both halves are idempotent. A manifest that already carries the suffix and names an account is
not rewritten, so running `init` again reports nothing renamed. An overlay named at 0.1.x carries
the suffix but no `owner` or `author`, so the first `init` of this release rewrites its manifests
once more, to add them.

**Writes** each of the three manifests that does not already carry the suffix or has no account
under its `owner` or `author` and, where the overlay carries one that records a manifest it
rewrote or a file below, `.stayfixed/manifest.json` — through the same contained walk every other
write in this project goes through; and, through the `pre-commit install` it runs in the overlay,
the overlay's `pre-commit` git hook. It also **removes** the files an earlier release shipped and
this one does not, by the rule and from the list
[`overlay upgrade`](#stayfixed-overlay-upgrade---root-path---dry-run) gives below, and each directory
above one of them that this leaves empty: `init` is the step every generated overlay runs, and a
template published at an earlier release still ships those files.
When it removes `common/memory/README.md` and `common/memory/_README.md` is not there, it
**writes** the shipped `_README.md` in its place: a template from 0.1.x carries only the old name,
and a directory left empty is one git does not keep, so a clone of the overlay elsewhere would
have no `common/memory/` for the `developer` link to reach. A copy holding anything else is left,
and the line says so and names the way out `overlay upgrade` gives for it. Until then each run
names the copy again. A retired file it cannot read or
cannot remove is left too, with a `left <path>: <reason>` line, and a `_README.md` it cannot
write is named with `overlay upgrade`, which writes it — or, when this stayfixed was installed
without its overlay template tree, which `overlay upgrade` reads too, with a reinstall first — and
`common/memory/` is kept for it rather than removed as empty. None of the three is a failure: the
run goes on, and `.stayfixed/manifest.json` drops the records of the files it did remove and keeps
the others, so the next run finishes the job. A record of a retired file that is already gone, at
its own place or at its place under `.stayfixed/local/artifacts/`, is dropped with a
`dropped the record of <path>, which was already gone` line, since there was nothing to remove;
for `common/memory/README.md`, `_README.md` is then written in its place as after a removal.
A path these lines name that the manifest supplied and that holds anything but a plain path is
escaped, so a line break or an escape sequence in it cannot start a line of its own or drive a
terminal.
A tree that arrived without a manifest is not given one. Exits `0`; `1` on a manifest that exists
and cannot be read or is not JSON, with nothing written; `2` on an owner that is not one path
segment or on a scaffold manifest that cannot be trusted. A manifest it cannot write is not a
failure either: once every manifest has been read, nothing stops the run, and
`.stayfixed/manifest.json` is written once, at the end, with the records of what it did.

---

## `stayfixed overlay upgrade [--root PATH] [--dry-run]`

**`--root` must name an overlay, and that is checked before anything is planned.** It defaults
to `.`, and pointed at a directory that is not one this command used to create the overlay's
files there — both plugin manifests, `hooks/hooks.json`, `.gitignore` and
`.github/workflows/scan.yml` among them — report them as work done and exit `0`. An overlay is a
tree whose two `.claude-plugin/` manifests name it `stayfixed-overlay[-<owner>]` and
`stayfixed-overlay-marketplace[-<owner>]`, which is what `overlay create` renders and `overlay
init` renames; anything else is refused (`2`) with nothing written.

Brings an overlay up to date with the template a newer stayfixed ships. It is the project rule
and not a second copy of it: a skeleton file you have not touched is refreshed, one you have
edited is skipped and named, and the oracle is the digest `.stayfixed/manifest.json` recorded when
the file was written. An overlay is where your own rules live, so a silent overwrite here would
destroy the only copy of something.

**The three manifests keep the names `overlay init` gave them.** What a refresh writes there is
the template named after the account the manifests already carry, exactly as `init` names it, so
running `upgrade` right after `init` changes none of them, and a release that moves a manifest
refreshes it under your name rather than back to `stayfixed-overlay` — the name two owners'
overlays would collide on. A manifest the overlay lacks is written under that name too. An overlay
`init` has not named gets the template as it ships.

**Two files are always listed, however their hashes compare.**
`common/claude/permissions.json` and `common/claude/hooks.json` are the two an overlay carries
that can grant a capability — a permission rule, a command that runs on an event — and a hash
that matches is not your consent to either. They are listed under `ASK FIRST` beneath the report,
and under `decisions` in `--json`. Without `--dry-run` that list is printed *after* the refresh,
not before it: nothing waits for an answer, and the reason it can be a notice rather than a gate
is that the shipped template grants nothing — its permissions file is deny-only and its hooks
file is empty, both held by a test. `--dry-run` first is how you read them before anything moves.

`--dry-run` prints the same report and writes nothing; the report you approve is produced by the
code path that then runs, which is what makes the dry run worth reading.

**Writes**, without `--dry-run`, every artifact the report lists as `create` or `update`, plus
`.stayfixed/manifest.json`. It also **removes** three files a release no longer ships:
`common/memory/README.md`, which is `_README.md` now because the note reader reads every other `.md`
there as a note; `skills/attach/SKILL.md`, the template's own copy of the `attach` skill, which the
plugin's own replaces, since it covers detaching and a moved remote as well; and
`common/rules/README.md`, the README of a directory nothing read. It does so only when a file holds
what stayfixed wrote there: the digest `.stayfixed/manifest.json` recorded, or, in an overlay with
no manifest (one generated from a template, since `publish-template` leaves it out), a file a
release shipped there — 0.1.0 and 0.1.1 for the memory README, any of 0.1.0, 0.1.1 and 0.2.0 for the
other two. A recorded one that is already gone is listed as `remove … (retired, already gone)`:
nothing is removed, and its record is dropped. Any other copy may hold your own words, so it is
listed as `skip_modified` with the way out: rename the memory README to `_README.md`; the plugin's own `attach` skill replaces the
template's, so delete your copy once you no longer need your edits; a standing rule is a note with
`metadata.startup`, so move your rules into such notes and delete the README. Until then each run
lists the copy again. Each directory above a file it removed then goes once that leaves it empty,
up to the first that still holds anything and never the overlay root: `skills/attach/` and
`skills/`, and `common/rules/`. A directory that is a symbolic link is left, and so is one above a
file that was already gone when the run began. Exits `0`; `1` when the report
carries a REFUSED section, because nothing would be written while one of those stands; `2` when
`--root` is not an overlay, when the manifest itself cannot be trusted, or when a write is refused
by the containment walk.

---

## `stayfixed overlay publish-template --owner OWNER [--name NAME] [--yes]`

Publishes the repository `overlay create --template` generates from: the shipped
`templates/overlay/` tree, as one commit on `<owner>/stayfixed-overlay-template`.

```bash
stayfixed overlay publish-template --owner you          # what it would create, mark and push
stayfixed overlay publish-template --owner you --yes    # do it
```

Six steps, in this order. It renders the shipped template into a scratch directory; it strips
the scaffold ledger, because a repository generated from a template carries none and publishing
one would make every generated overlay read as hand-edited to `overlay upgrade`; it asks `gh`
what exists under that name; it creates the repository **public** and marks it
`is_template` if it is not one already; it clones it and replaces the tree with the render; and
it commits and pushes to the repository's default branch.

**`--yes` is the gate, and it covers three acts rather than one** — creating the repository,
marking it a template, and pushing. Without it the command renders, asks `gh` what is there,
and reports what it *would* create, mark and push. That is the dry run; there is no separate
`--dry-run` flag, because a second way to say the same thing is a second thing to get wrong.
The gate is a parameter and not a step in a procedure: in a session driven by an agent, a flag
a model can type is not a control, so the flag is where the consent is recorded.

**An existing repository that is not public is refused (`2`), never flipped.** A template is
generated from by other accounts only when it is public, and a repository somebody made private
under that name is not one this command may change a flag on — publish under another `--name`,
or make it public yourself first.

**It runs from your own authenticated checkout by design.** The public repository's CI holds no
credential that can write a second repository, so this is not a workflow and does not become
one: `gh` decides the protocol and carries the token. `gh` that cannot be run at all is a
finding (`1`) naming it.

`--owner` is your account and `--name` the repository (default `stayfixed-overlay-template`);
both are held to one path segment, and the owner is lower-cased the way `overlay create` folds
it. There is no `--root`: the tree is rendered from this stayfixed's own package.

**Writes**, without `--yes`, nothing outside a temporary directory this command creates and
removes. With it, on GitHub through `gh` and `git`: the public repository `<owner>/<name>`, when
there is none; its template flag, when it is not set; and a commit pushed to its default branch,
unless it already carries this stayfixed's template. The clone and the commit are made in the
same temporary directory. Exits `0`; `1` on a `gh` or `git` that failed, with what it printed
quoted as `overlay create` quotes it (escaped, and cut to its first 120 characters and its
length); `2` on a refusal.

---

## `stayfixed attach --store PATH [--check] [--yes] [--trust-remote] [--root PATH] [--machine PATH]`

Binds this repository to your private overlay and links its note store in. After it, a session
in this repository reads your cross-project notes and this project's own notes, and the
permissions and hook entries you keep in the overlay are merged into
`.claude/settings.local.json`.

**`--machine` is honoured only from an interactive shell.** This is the command that turns the
machine configuration into capability: the overlay root comes from that file, and from the
overlay come allow rules, hook entries and standing rules. `STAYFIXED_CONFIG` and
`XDG_CONFIG_HOME` are already gated the same way and for the same reason — a repository can set
an environment variable through a committed settings file, and it can just as easily tell an
agent to pass a flag. In a non-interactive session the flag is **refused** (`2`) rather than
ignored, because silently falling back would read your real configuration while the caller
believed it was reading the file it named. Omit it and the default file is read exactly as
before; `stayfixed detach` follows the same rule.

**`--store` names one directory and nothing else:** `<overlay>/projects/<project name>/memory`,
where `<project name>` is the `[project] name` in this repository's `stayfixed.toml`. The overlay
root itself is **not** taken from that path — it comes from the `[overlay] root` your machine
configuration records, which `stayfixed setup` writes. A `--store` anywhere else is refused (`2`),
including a directory elsewhere under the same overlay: the session-start path holds every linked
group to this project's own share, so attaching to a sibling would produce a store every session
then refuses. A `[project] name` no directory can carry there — the name of a file the overlay
keeps under `projects/`, which on a filesystem that ignores case includes `readme.md`, or a name
longer than the filesystem allows — is refused (`2`) before anything is written, by `--check` as
well, and the refusal names the shape of the path and never the name. So is a name whose directory
there fits under the longest path the system allows while a path `attach` makes inside it does
not — the `project.toml` that records the binding, the notes index `MEMORY.md`, or the directory
of one of `memory.groups` — because nothing could read that record back or link the notes to that
path; a long `memory.groups` entry reaches it as a long name does, and the refusal names neither.

**Only an overlay-mode repository is attached.** A `stayfixed.toml` whose `memory.mode` is not
`overlay` keeps its notes in the repository, and `attach` refuses (`2`) before it writes
anything; `--check` says so first on its line, still reports the rest, and exits `2`, the code
the real run refuses with.

**`--check` writes nothing.** It reports the binding state — `unbound`, `bound`, `mismatch` or
`no-origin`, the last with the cause and the way out ahead of the counts — the permission diff
(which allow rules and which hook entries would be added, and how many of the overlay's rules this
repository already has), the Codex standing-rule files it would place under `.codex/rules/`, and
`real_directories`: how many of this project's memory groups are still real directories rather than
links into the overlay. Read it before the real run: everything under **Writes** below that carries
content from the overlay is named here first. It does not ask what the real run asks after the
diff: an overlay rule file that is not UTF-8, which the real run fails on (`1`), and a `trust.json`
that does not parse, a doubled `stayfixed:ignore` region or `stayfixed:attach` block or a
`.git/info` you cannot write, which it refuses (`2`). The real run does both before it writes
anything.

It exits `1` when that count is non-zero, the same way it does on a mismatch or a checkout with no
`origin` and for the same reason — all three are findings you act on before the real run, and
`attach` itself is what refuses. The count is a count: a group's name comes out of `stayfixed.toml`,
so it is never printed.

Those standing-rule files are reported but **not** gated by `--yes`. The gate is about widening
a *permission*; a standing rule is not one, and adding standing rules is the machine owner's own
to do — which is exactly what the overlay is. `widens` in the `--json` output therefore answers
about permissions alone, and `rules_to_write` lists the files.

**A write that grants a capability needs `--yes`.** If the diff would add an allow rule or a hook
entry, `attach` refuses (`2`) without it. That is a refusal and not a prompt on purpose: the
command line here is usually written by a model that has read this repository, so a gate whose
only enforcement is a step in a procedure is no gate at all. An overlay that grants nothing needs
no flag, because the gate is on the capability and not on the command.

**A mismatch needs `--trust-remote`.** The overlay records the remote URL it bound under this
project name; if this repository's `origin` is a different URL, `attach` refuses (`2`) unless you
say otherwise. URLs are compared exactly, so the same repository under another URL form — cloned
over https where the overlay recorded ssh, say — is a mismatch too, and the refusal says so. A
clone chooses its own `project.name`; it does not choose what the overlay recorded under that
name. A checkout with no `origin` is not a mismatch, whatever the overlay records: there is
nothing to compare, so `--trust-remote` does not apply, and `attach` refuses it, as `--check`,
`doctor` and the memory commands report it, with one sentence: add the `origin`, then run
`stayfixed attach`.

**A group that never moved is refused.** `attach` **links**; it never moves a note. So a
`memory.groups` entry that is still a real directory under `paths.memory` would be linked over,
leaving every session reading the repository's own copy while that group's share of the overlay
stayed empty — with the binding record, the settings merge and the ledger already written.
`attach` refuses (`2`) above its first write instead, counts the groups, and names where each
one goes: `<overlay>/projects/<name>/memory/<group>`, and `common/memory` for the shared group.
Moving the notes is yours to do; no command does it for you. The containment that count is taken
under is anchored on the checkout you pointed the command at, not on any path the repository
configures, so a repository cannot move the directory being counted. **And that containment is a
refusal of its own**, distinct from the two above it: a `memory.groups` entry that does not stay
inside this project's `paths.memory` is refused (`2`) rather than counted — `paths.memory` may
itself be a symlink, and then every group leaves the root at once. Its sentence names neither the
group nor the path, both being repository-authored.

**Reads** the overlay's `common/claude/permissions.json` and `common/claude/hooks.json`, this
project's `projects/<name>/claude/` equivalents, the overlay's `common/codex/` and
`projects/<name>/codex/` rules, and this repository's existing `.claude/settings.local.json`.
`.claude/settings.json` — the committed one — is read for **nothing**: it is repository-controlled,
and the repository never grants a capability.

**Writes** the `stayfixed:ignore` region in `.gitignore` (which is what keeps
`.stayfixed/local/` untracked, and is written first — and only when git does not already ignore
both `.stayfixed/local/` and `.stayfixed/assessment.json`), a block between
`# stayfixed:attach:begin` and `# stayfixed:attach:end` in the repository's own exclude file (the
one `git rev-parse --git-path info/exclude` names, which every worktree shares),
`.claude/settings.local.json`, `.codex/rules/`, the ledger `.stayfixed/local/attach.json`, the
link tree under `paths.memory` in this checkout and in every existing worktree, the harness memory
link, and — in the overlay — `projects/<name>/project.toml`, this project's note directories,
`projects/<name>/memory/MEMORY.md` when the store has none yet (rendered as `stayfixed memory
index` renders it, so the index link never dangles and `memory index --check` passes right after
a first attach in an overlay this release rendered; one generated from a template published at
0.1.x passes once `overlay init` has run on it, and an older overlay once `overlay upgrade` has,
because both remove the `common/memory/README.md` 0.1.x shipped unless it was edited) and, through
the
`pre-commit install` it runs there when the overlay carries a `.pre-commit-config.yaml` and no
`pre-commit` hook yet, the overlay's `pre-commit` git hook. The ledger is the only record
of which allow rules are stayfixed's, because an allow rule cannot carry a marker the way a hook
entry can; `detach` reads it and nothing else.

**What it places, it hides from git, unless git hides it already.** The link tree (`MEMORY.md` and
one link per group), each `.codex/rules/` file and — on a run that writes it, or after one that did
— `.claude/settings.local.json` are this machine's own, so each one is listed in the exclude-file
block, one anchored line per path, unless your own excludes already hide it: the repository's
exclude file or your global excludes file (`core.excludesFile`), read on their own. A `.gitignore`
in the checkout does not stand in for the block, because the repository authors it and a pull can
change it: a path only a `.gitignore` hides gets a line, and a path your own excludes hide gets
none, whatever a `.gitignore` also says. A file the repository tracks is listed only when your own
excludes do not hide it, since no exclude line hides a tracked file. A link whose name no single
exclude line can hold — a group name with a line break, a NUL, U+2028 or another character a line
reader may split at — gets no line and stays visible, rather than being written as a line git, or a
later `attach` reading the block back, would take for several. A path this run does not write is not
listed and is not held to the project either, so a `.claude` linked in from elsewhere is refused,
before the first write, only when the overlay grants something to merge into it. The
`autoMemoryDirectory` fallback is never written through such a link: where it would be taken — a
real directory already sits where the harness memory link goes, and the store is approved — `attach`
skips it and its line says what the harness link is missing and what to do. Whether the fallback may
be taken is decided before the first write too; on a first attach, with no approval recorded for the
store yet, it cannot be. A checkout that already hides all of them in its own exclude file or a
global excludes file gets no block, and one that already hides `.stayfixed/local/` and
`.stayfixed/assessment.json` by any means, `.gitignore` included, gets no `.gitignore` change, so
`git status` after an attach shows at most the `stayfixed:ignore` region. `.gitignore` is never
written beyond that region. When the exclude file did not exist, when the directory it goes in did
not exist either (a repository made without git's templates has no `info/`, and the write creates
it), or when its last line had no line ending, the block says so in a comment line of its own, which
is what lets `detach`, from whichever checkout runs it last, give the file back byte for byte. The
file is read as bytes, so bytes in it that are not UTF-8 are kept exactly and refuse nothing. The
file is read, changed and replaced without a lock, so two runs at once in checkouts of one
repository — two `attach` runs, or an `attach` and a `detach`, in the main checkout and a worktree
say — can each read it before the other writes, and the later write then undoes what the earlier one
did to it. Run one `attach` or `detach` at a time. Running `attach` again in the checkout whose
lines went puts them back.

It also **removes** one file, in one case. The `autoMemoryDirectory` fallback is taken only while
the harness memory link cannot be made, so when the link becomes possible again — or when the
store's trust record lapses — that key is withdrawn in the same run. If it was all
`.claude/settings.local.json` held, the file goes with it, because `{}` is not what that file
looked like before `attach` created it. Nothing you wrote is ever what goes: the case only
arises when stayfixed's own key was the file's entire contents.

**When the harness memory link waits for approval, `attach` says so.** The link exposes the
link tree, which sits inside the repository, so it is made only once the store is approved; until
then the run's line ends with a note to run `stayfixed memory trust --in-repo-memory`, then
`stayfixed attach` again.

**The harness memory link is written under a walk that follows no symlink.** The home
directory itself is found and never created — a missing one is a refusal — and every component
below it has to be a real directory: a `~/.claude` linked into a dotfiles tree is refused by
name, above `attach`'s first write, above `detach`'s first withdrawal and above the first note
link a session makes in a worktree, rather than written through. The refusal names the component
and the way out, which is the same one `--settings`
exists for on the `setup` side: make the directory real and have your dotfiles manager adopt the
files inside it.

It also runs `pre-commit install` in the overlay when the overlay carries a pre-commit
configuration and no hook is installed — the machine that cloned an overlay someone else created
never ran `overlay init`. A missing `pre-commit` is a reported note, never a traceback, and what a
failing one printed is quoted as `overlay create` quotes it (escaped, and cut to its first 120
characters and its length).

Exits `0` on success. Under `--check` it exits `1` on a mismatch, on a checkout with no `origin`,
**or** on a non-zero count of memory groups that are still real directories, which are the findings
the paragraphs above explain and the same number for all three, and `2` for a `memory.mode` other
than `overlay`; the loading, binding and diff failures below end `--check` with the same codes as a
real run.

A real run exits `1` on a failure, something it reads that cannot be read or a `git` that cannot
answer, in the order the run meets them:

- `stayfixed.toml` is missing, cannot be read, is not UTF-8 or valid TOML, or holds a key or value
  the loader refuses; or the machine configuration cannot be read, is not UTF-8 or is not valid
  TOML.
- The overlay's record of this project (`projects/<name>/project.toml`) cannot be read, is not
  UTF-8 or is not valid TOML, or `git` cannot read the `origin` remote.
- The overlay's `permissions.json` or `hooks.json`, or `.claude/settings.local.json`, cannot be
  read or is not UTF-8.
- An existing `.stayfixed/local/attach.json` cannot be read, is not UTF-8, is not valid JSON or is
  not a JSON object.
- A Codex rule file in the overlay cannot be read or is not UTF-8.
- `git worktree list` fails.

Every failure in that list happens before anything is written. One way to exit `1` comes later,
and leaves behind what was written before it: a store that still does not resolve once the link
tree is built.

It exits `2` on a refusal, in the order the run meets them:

- No `--store`, or a `--machine` outside an interactive shell.
- A `[paths]` value that leaves the project or passes through a symlink.
- No overlay root recorded in the machine configuration, or a `--store` that is not this project's
  own directory inside it.
- A `memory.mode` other than `overlay`.
- The overlay's `permissions.json` or `hooks.json`, or `.claude/settings.local.json`, that is not
  JSON or not a JSON object, or whose `permissions` or `hooks` has a shape the merge cannot read.
- A widening without `--yes`; a checkout with no `origin`, whether or not the overlay records the
  project; a mismatch without `--trust-remote`; an `origin` whose URL is not UTF-8 text, which the
  overlay's record cannot hold.
- A `memory.groups` entry that leaves this project's share of the overlay; one that does not name a
  subdirectory of `paths.memory`, or a `paths.memory` that is itself a symlink (a refusal of its
  own, which is why the `--check` count counts only groups that stay inside); a memory group that
  is still a real directory rather than a link into it.
- A home directory that is not there, or a component below it, `~/.claude` included, that is a
  symlink.
- A `.stayfixed` that is a symlink, or an existing ledger naming files, settings keys or
  directories `attach` could not have written.
- A `git check-ignore` that cannot answer; a `.gitignore`, when it needs the `stayfixed:ignore`
  region, that cannot be read, is not UTF-8 or holds that region opened or closed twice (the
  refusal names the file).
- A `.codex` or `.claude` that is a symlink, on a run that writes into it; a
  `git rev-parse --git-path info/exclude` that names no exclude file; an exclude file that cannot
  be read or holds a `stayfixed:attach` block opened or closed twice (the refusal names the file),
  or, when the block needs a line, that is a symlink or sits in a directory you cannot write.
- A trust record, the machine's `trust.json`, that cannot be read or is not the record it should
  be.

Every refusal in that list happens before anything is written, so a refused attach leaves both the
repository and the overlay as they were. What is left can only happen once writing has begun:

- A `.gitignore` that cannot be written. It is the first write, so this refusal leaves nothing
  behind either.
- An exclude file that cannot be written after all, which is refused, naming it, with
  `.gitignore`'s region already written.
- A directory in this project's share of the overlay that became a symlink between the moment it
  was checked and the moment it was written, which is refused.
- Any other write that fails, a rule copy, the settings file, the ledger, the overlay's record or a
  link, which ends as `internal error` with the error the system gave.

---

## `stayfixed detach [--root PATH] [--machine PATH]`

Removes exactly what `attach` added, and leaves the binding alone.

It reads `.stayfixed/local/attach.json` and acts on that and on nothing else *that it is willing
to believe*. A repository with no ledger fails (`1`) naming the missing file rather than guessing
which allow rules were stayfixed's from their content — that guess is the reason the ledger
exists, and getting it wrong removes a rule you wrote by hand. And the ledger is not an
authority: `.gitignore` does not untrack a file a clone committed, so this path can arrive in a
fresh checkout with contents nobody on your machine wrote. Every field is held to what `attach`
could have put there — `rules` to a single file under `.codex/rules/`, `settings_keys` to
`autoMemoryDirectory` — and a ledger naming anything else is refused (`2`) with nothing removed,
rather than obeyed. A ledger claiming `settings_keys = ["permissions"]` would otherwise have
deleted your whole `permissions` block, deny rules included.

**Run it from the checkout you attached from.** `.stayfixed/local/` is untracked and per-checkout,
so a sibling worktree does not carry the ledger of the checkout the attach was run from and
`detach --root <that worktree>` answers "no ledger" — there is nothing there to reverse. Once it
starts it reaches every checkout of the repository, including the one that owns the store; it is
only the *starting* point that has to be the one holding the record.

**Writes**: it takes the recorded allow rules and the fallback key back out of
`.claude/settings.local.json`, drops the hook entries marked `# stayfixed:…` there (a group that
mixes one of those with your own entry is split, never replaced), and leaves the file unwritten when
none of those is in it, removes the `.codex/rules/` files it wrote, withdraws the link tree from
this checkout and every worktree together with the harness memory link, removes the
`stayfixed:ignore` region and the `stayfixed:attach` block in the repository's exclude file, and
deletes the ledger, `.stayfixed/local/attach.json`. A file left holding nothing is removed rather
than left empty — for the exclude file, only when `attach` created it, which the block records, so
an exclude file you had, empty or not, stays, and the `info/` directory it sat in goes with it only
when `attach` created that too and it is empty; the line ending `attach` added to your exclude
file's last line before its block is taken back too, when nothing follows the block. The exclude
file is read and written as bytes, so bytes in it that are not UTF-8 are kept as they are. An
exclude file that is a symlink is left alone, because `attach` never writes through one. **The
exclude block stays while another checkout is attached.** The exclude file is shared by every
worktree of the repository, while the ledger, the settings file and the `.codex/rules/` copies are
each checkout's own; so when another checkout still holds a ledger, the block is kept for its files,
the line ends by saying so, and `--json` reports `exclude_block_kept: true`. The detach of the last
attached checkout takes it. Only a ledger an attach wrote counts: one git does not track (a clone
that committed the file has it in every worktree) and that reads as a ledger. A `git` that cannot
say whether the file is tracked counts it, and the block stays.

Then it removes, each only when empty: the `paths.memory` directory in this checkout when the
ledger records `attach` as having created it, and in every other checkout it withdrew a tree from
(no ledger of this run's records what was there, and that tree was built by `attach` or by the
worktree-link handler); the directories above it in this checkout that the ledger records
`attach` as having created (`docs/`, for the preset's place); and the `~/.claude/projects/<slug>/`
directory each harness memory link sat in. Last,
each directory the ledger records `attach` as having created — of `.stayfixed/local/`,
`.stayfixed/`, `.codex/rules/`, `.codex/` and `.claude/`, in that order — is removed when it is
empty, and left standing otherwise.

**The `stayfixed:ignore` region in `.gitignore` goes only if the manifest does not record it.**
On a repository `stayfixed init` set up, that block is the footprint's — recorded in
`.stayfixed/manifest.json` as a scaffolded artifact, with the body `attach` writes — and it
stays. Ownership decides, not last writer: the block is committed, so withdrawing it would
take a line out of a tracked file this command never wrote and leave `stayfixed upgrade`
reading the footprint as hand-edited. A repository with no manifest is one no
`init` has set up, and its region is withdrawn as before.

A manifest this command **cannot read** — unreadable, not a JSON object, or written by a newer
stayfixed — is read as no answer rather than as an answer, so the block stays and the detach
finishes. That file is committed and `attach` never opens it, so a clone that ships a broken one
would otherwise attach cleanly and then make every later `detach` exit `2` for ever, with the
only way out being to delete a tracked file out of somebody else's repository. `--json` reports
`ignore_region_removed: false`, and `stayfixed init` or a hand edit clears the block.

**Directories come back too.** `attach` records which of `.stayfixed/local/`, `.stayfixed/`,
`.codex/rules/`, `.codex/`, `.claude/` and the directories above `paths.memory` this repository
did not have before it ran, and whether it had `paths.memory` itself, and `detach` removes exactly
those once everything inside them is gone. The removal is `rmdir`: a directory still holding
anything — your own `.codex/rules/` file, your `.claude/settings.json`, a note that never moved
into the overlay — survives, and so does its parent. A directory above or at `paths.memory` that
was already there before the attach, empty or not, is not on the record and is never touched. The
round trip is byte-for-byte in the checkout you attached from; in another worktree, an empty
`paths.memory` goes whether or not it was there before.

**It does not touch `projects/<name>/project.toml`.** That record is your consent to the binding,
not local state: deleting it would turn every later re-attach into a first attach and re-ask a
question you have already answered.

Exits `0` on success. It exits `1` on a failure, in the order the run meets them:

- `.stayfixed/local/attach.json` is not there, cannot be read, is not UTF-8, is not valid JSON or
  is not a JSON object.
- `stayfixed.toml` is missing, cannot be read, is not UTF-8 or valid TOML, or holds a key or value
  the loader refuses; or the machine configuration cannot be read, is not UTF-8 or is not valid
  TOML.
- `.claude/settings.local.json` cannot be read or is not UTF-8.
- `git` cannot list this repository's worktrees.
- `.gitignore` cannot be read or is not UTF-8.

It exits `2` on a refusal, in the order the run meets them:

- A `--machine` outside an interactive shell, for the reason `stayfixed attach` gives above.
- A ledger naming files, settings keys or directories `attach` could not have written.
- A `[paths]` value that leaves the project or passes through a symlink.
- A `.claude/settings.local.json` that is not JSON or not a JSON object, or whose `hooks` has a
  shape the withdrawal cannot read.
- A home directory that is not there, or a component below it, `~/.claude` included, that is a
  symlink, in any checkout of the repository.
- A `stayfixed:ignore` region in `.gitignore` opened or closed twice, or otherwise with markers
  that no longer say where it ends (the refusal names the file).
- A `git rev-parse --git-path info/exclude` that names no exclude file, an exclude file that cannot
  be read, or a `stayfixed:attach` block in it opened or closed twice (the refusal names the
  file).
- A path the withdrawal writes or removes reached through a directory that became a symlink after
  the attach: `.claude` when the settings file is to be rewritten, `.codex` or `.codex/rules` for
  a recorded rule copy, `paths.memory` or a directory above it in any checkout, `.stayfixed` or
  `.stayfixed/local` for the ledger. The refusal says which. A rule copy that is itself a link is
  not one of these: it is unlinked, and what it points at stays.
- A `memory.groups` entry added since the attach that does not name a subdirectory of
  `paths.memory`, in any checkout of the repository. The refusal counts it and does not print it.
- A `.claude/settings.local.json` whose `permissions` is not an object, or whose
  `permissions.allow` is not a list of strings.

Every one of those is answered before the first withdrawal, so a refused `detach` has removed
nothing. What is left can only happen once withdrawing has begun, and leaves the ledger in place
with part of the attach already undone:

- An exclude file that cannot be written, which is refused, naming it, once the settings, the rule
  copies, the link trees and the `.gitignore` region are withdrawn.
- Any other write or removal that fails, which ends as `internal error` with the error the system
  gave.

---

## `stayfixed setup [--preset NAME] [--yes] [--home PATH] [--settings PATH] [--machine PATH] [--overlay VALUE] [--root PATH]`

Configures this machine from a preset, `recommended` unless `--preset` names another: the
machine configuration file's `[personal]` and `[machine]` tables, the deny rules and personal
values in `<home>/.claude/settings.json`, and the preset's plugins, one install per plugin per
configured harness. `--home` and `--machine` default to the home directory and to
`~/.config/stayfixed/config.toml` — the file every reader reads, and not whatever
`XDG_CONFIG_HOME` or `STAYFIXED_CONFIG` names, because a machine file half the installation
cannot find is not a machine file. Both flags exist so this command can be pointed at a
scratch destination instead of your real one, the same way every other command here takes
`--root`. A scratch destination is **not a dry run**: the same files are written, at the paths
these two flags name, and nothing is suppressed. They apply to `--preset` alone — `--git-hooks`
writes inside a repository and ignores both.

`--settings PATH` writes the user-scope settings file at `PATH` instead of at
`<home>/.claude/settings.json`, for a dotfiles layout that links that file into another tree.
`stow` folds a package as far as it can, so with `~/.claude` already created by the harness it
links the *file*: `~/.claude/settings.json -> <dotfiles>/claude/settings.json`. No `--home`
value names that target — `--home <dotfiles>/claude` writes
`<dotfiles>/claude/.claude/settings.json`, a file no reader reads — and the refusal that used
to print an unusable remedy now names this flag. The write still never follows a symlink, and a
link *at* the file itself is refused rather than written through — by a check above the first
write, and not by the walk: the root is the directory `PATH` names and the walk is one component
deep, so the walk never opens the final name and the rename underneath it would *replace* a link
rather than refuse it. The refusal names the file the link leads to, which is the path to pass
instead, and a directory at that path is refused in the same place. `--settings` changes nothing
else: the machine configuration file is still `--machine`'s, and the harness memory link is still
under `--home`.

`setup` is not the only command that writes outside a repository, and two others say so in their
own sections: `stayfixed memory trust` records approval in `~/.config/stayfixed/trust.json`, and
`stayfixed attach` places the harness memory link under `<home>/.claude/projects/`. It is the only
one that writes the machine configuration file and `<home>/.claude/settings.json`. `--root` (default `.`) is the project this invocation
was run from; the only thing it is used for is refusing an `--overlay` any checkout of it could
reach (below).

`setup` is the only writer of the machine configuration file, and the two existing readers do
not change: `[personal]` is `config.loader`'s, `[overlay] root` is `memory.store`'s, and both
still resolve the file `--machine` names or the default one. A second run merges rather than
replaces, key by key: a personal value already recorded — by an earlier `setup` or by your own
hand — is never overwritten by the preset's own default, and an overlay root a previous run
recorded survives a run that only changes something else. A table `setup` knows nothing about is
carried through untouched, and so is a key at the top level; **comments are not** — the file is
parsed and rewritten, and there is no standard-library parser that keeps them.

The `[personal]` values are mirrored into `pluginConfigs` in `<home>/.claude/settings.json`,
where Claude Code reads this plugin's own options, and that mirror is recomputed from the machine
file on every run. The machine file wins: a value you set in Claude Code's plugin-config UI is
overwritten by the next `setup`, because one of the two copies has to decide and the machine file
is the one everything in stayfixed reads.

**Plugins are installed per configured harness**, from `[defaults.stayfixed] agents` (`claude`
and `codex` by default) and from the preset's own per-harness marketplace table
(`[plugins.<harness>]`). For each harness the preset declares a marketplace for, `setup`
registers it (`claude plugin marketplace add <source>`; idempotent — an already-registered
source is a no-op reported as such) and then installs each plugin bare (`claude plugin install
<name>@<marketplace>`; no `--scope` or `-y` — the spike record's own measured output reports
`(scope: user)` as the *default*, and `-y` only ever appears there on `uninstall`). Codex adds
rather than installs (`codex plugin add <name>@<marketplace>`) where the preset declares a
marketplace for it. A harness with no declared marketplace for a plugin is not attempted —
nothing here is vendored on a guessed marketplace name — and a missing binary or a
failed call is a reported note, never a failure.

**The overlay is touched only when `--overlay` names an answer**, and `--yes` does not imply
one. `--overlay <path>` records an existing overlay's root; `--overlay create:<owner>/<name>`
asks GitHub for a private repository from the template and initialises it, the same as
`stayfixed overlay create --template` followed by `overlay init` — and makes the same choice of
template that flag makes: yours when you have published one,
`github.com/stayfixed/stayfixed-overlay-template` otherwise. Creating one needs `--yes` —
explicit confirmation for the one irreversible, outward-facing act this command performs — and
refuses (`2`) without it. Recording an *existing* path needs no `--yes`
(a model-written command line reaches `--overlay X --yes` exactly as easily as `--overlay X`,
so the flag would be theatre there); instead the path itself is validated **before the first
write** — before the machine file, the settings merge and the plugin installs, and for `create:`
before `gh repo create` runs on anybody's account. It must exist; its two `.claude-plugin/`
manifests must name it `stayfixed-overlay[-<owner>]` and `stayfixed-overlay-marketplace[-<owner>]`,
which is what `overlay create` renders and `overlay init` renames, rather than merely being
present; and it must lie outside the repository `--root` names — not inside it, not above it, and
not in another checkout of it, since a worktree is not a different repository and a clone ships
its tree into all of them. The path comparisons stand alone only where `--root` is in no
repository, or where `git` cannot be run and no `.git` is at or above the directory it was asked
from. Everywhere else inside a checkout, a `git` that gives no answer, refuses the repository it
found (another user's under `safe.directory`, or one whose `.git` it cannot read) or cannot list
its checkouts is a refusal.

**Writes** `<home>` itself when it is not there yet; `--machine`'s file, with the directories above
it, once for the preset and again for the overlay root `--overlay` records;
`<home>/.claude/settings.json`, or the file `--settings` names in its place; and, through the plugin
commands it runs for each harness with a declared marketplace (`claude plugin marketplace add` and
`claude plugin install`, `codex plugin marketplace add` and `codex plugin add`), the marketplace
registrations and installed plugins those commands write into each harness's own configuration.
`--overlay <path>` writes nothing in the overlay; it is only recorded.
`--overlay create:<owner>/<name>` writes what `overlay create --template` writes — a private
repository on GitHub and its clone — and then what `overlay init` writes in that clone, including
its removal of the files a template published at an earlier release ships and this one does not.
Run again over the overlay it made, it generates nothing, but `overlay init` still runs there, and
the report names each file `init` changed (an overlay named by 0.1.x gains its account) or says it
changed none of the overlay's tracked files (`pre-commit install` may still have written its git
hook). Exits `0` on success, `2` on a refused `--overlay` (missing, not an overlay, reachable from
the project root, at a path that is not UTF-8 text and so cannot be recorded in the machine file, or
`create:` without `--yes`), and `2` when a symlink stands between `<home>` and the settings file:
that file is written through a walk that never follows one. Every one of those refusals happens
before the first write, **with one exception**: for `--overlay create:<owner>/<name>`, "not an
overlay" is a check on the tree that arrived, so it runs after the repository has been created on
GitHub and cloned — along with the machine file, the settings merge and the plugin installs. That
refusal says so, and names the repository and where it was cloned to, because nothing else would.
Everything else `create:` can be refused for — the missing `--yes`, a malformed spec, a name that is
not one path segment, a destination the project root could reach or the machine file could not
record — still happens before `gh` is run at all.

The symlink refusal names the link, where it leads, and a `stayfixed setup --home …` that writes
the file the link leads to — and where no `--home` can express the layout, it says that instead
of printing a command. `stow` folding a package to per-file links
(`~/.claude/settings.json -> <dotfiles>/claude/settings.json`) is that case: `--home H` writes
`H/.claude/settings.json` and nothing else, so no `H` names that target. Point the link at a
path ending in `.claude/settings.json`, or let this command write a real file and have your
dotfiles manager adopt it.

A plugin that fails to install or a harness that is absent is a note in the report, not a
nonzero exit. What the failing plugin command printed is quoted as `overlay create` quotes it
(escaped, and cut to its first 120 characters and its length).

---

## `stayfixed setup --git-hooks [--uninstall] [--root PATH]`

Installs the commit-message hook into this repository's own hooks directory — `git
rev-parse --git-path hooks`, never `core.hooksPath`, which is global state this command has no
business owning and which a repository-wide install would silently compete with husky or
`pre-commit` elsewhere on the machine.

A foreign hook of the same name is kept as `prepare-commit-msg.local` and the installed hook
`exec`s it last, so nothing that was already running there stops running; `--uninstall` puts it
back under its original name, byte for byte. The report names exactly what moved — a `.local`
file nobody was told about is indistinguishable from a lost one.

**Refuses (`2`) together with `--preset`.** The two write to different scopes — one repository,
one machine-wide — and a single invocation has only one exit code to report, so it does one of
the two.

**Writes** the hook file in `--root`'s hooks directory, and the `.local` file beside it only
when a foreign hook was there to preserve, by renaming that hook. Under `--uninstall` it removes
the hook file only when it is stayfixed's, and renames the `.local` file beside it, when there is
one, back to `prepare-commit-msg`. Exits `0`; `2` when `--preset` is also given.

---

## `stayfixed doctor [--json] [--root PATH] [--home PATH] [--machine PATH]`

Sixteen checks over one installation. It **reports and never repairs**: every finding
carries the command that would fix it, and not one of them is run for you. Nothing is written.

The rows come in a fixed order: the installation's own eleven first, then the five about the
private layer — the binding's (`attached`), the note store's (`bundles`, `store-debris`) and the
private overlay's (`pre-commit`, `overlay-requires`). Match a row by its `name`, never by its
position.

**Several subprocesses are run and every one of them only asks.** stayfixed's own
`hooks/run-hook.sh` with `--version`; `git ls-remote --exit-code` against the public
repository's tags, to judge `[ci] ref`, only when one is set; and the `git` queries the other
rows need — where the overlay keeps its hooks, what its `origin` is, and where the note store
resolves to, which the binding's row and the note store's rows each ask for themselves. Five of
those are measured on a green attached installation — the wrapper probe and four `git`
questions — and not one of the five leaves this machine. The `ci-ref` row's `git ls-remote` is a
sixth on a repository that records a `[ci] ref` at all, and it is the only one that does leave:
it goes through the `Runner` seam, which is what lets the case that pins the five answer it in
process instead of launching it. That one is bounded at **30 seconds**, and not
at the seam's own five minutes: five minutes is the bound for `gh repo create --clone` and the
clone behind it, and a peer that does not answer must not turn a one-line diagnostic into a
five-minute block. The other `git` questions are `gitenv`'s five seconds and the wrapper probe is
this area's own thirty.

**The rendered workflow is read as a regular file, and to a bound.** That path is the
repository's: a clone chooses what sits at `.github/workflows/stayfixed.yml`. Anything there that
is not a regular file — a directory, a symlink to a FIFO, a dangling link — is a warning naming
the path and never the ref's own verdict, and so is a file past 256 KiB, the same bound the
`diagnostics` row reads its log under. Not one byte of the file is printed on any arm, and a byte
that is not UTF-8 is replaced rather than raised: it used to reach the report as a red row saying
the check could not run, which is a red a clone could force.

The summary line carries the counts and the names of whichever status most needs reading, capped
the way every summary in this CLI is. The rows are in `--json`, under `checks`, one object per
check with `name`, `status`, `detail` and `remedy`. A remedy that is not in `--json` is a remedy
nobody sees, so that is where they all are.

`status` is one of `ok`, `warn`, `red`, `skip`.

| Check | What it answers | What it reads |
|---|---|---|
| `not-initialised` | whether there is a `stayfixed.toml` here, and whether it loads | `stayfixed.toml` |
| `versions` | whether the project's `[stayfixed] version` is the stayfixed running | `stayfixed.toml`, the package |
| `files` | the hook wrapper's executable bit, and the three shipped files against the hashes the release recorded beside them | `hooks/run-hook.sh`, `hooks/hooks.json`, `scripts/stayfixed`, `hooks/hashes.json` |
| `wrapper` | whether the wrapper can actually reach stayfixed on this machine | one `run-hook.sh open --version`, and only under the plugin root this stayfixed is part of |
| `hook-entries` | every hook entry, counted by provenance, with any that claims the stayfixed marker and is in no ledger named by position | `.claude/settings.json`, `.claude/settings.local.json`, `.codex/hooks.json`, and `~/.claude/settings.json` |
| `codex-trust` | whether any stayfixed hook is untrusted on Codex, and, when `[stayfixed] agents` lists `codex`, which surfaces do not run there and which hold in CI | `stayfixed.toml`, the harness registry |
| `budgets` | every budget that overrides the preset, and every one the ceiling clamps | `stayfixed.toml`, the preset |
| `cli-path` | whether `stayfixed` resolves on `PATH` | `PATH` |
| `ci-ref` | whether `[ci] ref` is the commit of a released stayfixed tag (or the `v1` alias: a warning, as mutable, once a `1.x` release creates it, and red until then), and whether the rendered workflow pins the same ref — under `[ci] mode = "reusable"`, a workflow that is not there at all is a warning and never a green row, and so are a path that is there and is not a regular file and a file past the 256 KiB bound on the read | `git ls-remote --exit-code` over the public repository's tags, bounded at 30 seconds; *.github/workflows/stayfixed.yml*, read as a regular file and to a bound |
| `diagnostics` | how many reasons the hook sink recorded — a count, never a line of the file | `${CLAUDE_PLUGIN_DATA}/stayfixed/diagnostics.jsonl` |
| `ignored-env` | `STAYFIXED_CONFIG` or `XDG_CONFIG_HOME` set and not honoured | the environment |
| `attached` | the overlay binding, and the shape of the harness memory path | `.stayfixed/local/attach.json`, `~/.claude/projects/<slug>/memory` |
| `bundles` | a bundle that does not fit its slots, and one whose part reaches the cap | the note store |
| `store-debris` | files in the note store that are not notes | the note store |
| `pre-commit` | whether the overlay's commit-time secret scan is installed on this machine | the overlay |
| `overlay-requires` | whether the overlay this machine records requires a stayfixed the running one satisfies — red when this project keeps its notes in that overlay, a warning when it does not | the overlay's `.claude-plugin/plugin.json`, `stayfixed.toml` |

**Ten of the sixteen have a `skip` arm — sixteen arms between them: one no build can answer,
and fifteen on a state of this machine or this repository.** A `skip` is **not** a finding and
never reaches the exit code, so read the detail — each one says which measurement it is missing.

The one no build can answer is `codex-trust`: it needs the hash Codex keys hook trust on, which
no spike measured. When `[stayfixed] agents` lists `codex`, its detail also says what was
measured: on Codex the session guards and session notices do not run, and the repository gates
hold in CI. `ci-ref` was counted beside it and is not any more, and neither is `files`.
`init` writes `[ci] ref`, so what `ci-ref`'s skip reports is a state — this repository records
none — and which state is the ordinary one moves with the release history rather than with any
code here: while no released tag matches the stayfixed running there is no commit to pin, so
`init` records nothing and the row skips on a correct installation; once a release exists, a
repository `init` set up carries a ref and the row answers. `files` compares the installed
plugin against the hashes the release recorded beside it, and skips only on a build carrying no
such record.

The nine that skip on a state are `files` and `wrapper`, when there is no plugin root this
process can vouch for; `attached`, when this machine records no overlay to check the ledger
against, or the overlay could not be asked at all; `pre-commit` and `overlay-requires`, when
no overlay root is recorded on this machine **or** when the root it records is not a directory
— two different arms with two different sentences, because a machine that recorded an overlay
and then moved it is not a machine that recorded none; `overlay-requires` again when the
overlay declares no stayfixed requirement; `bundles` and `store-debris`, when the note store does
not resolve; `diagnostics`, when no harness data root is set in the environment, which is every
`stayfixed doctor` run from a terminal rather than from a hook; and `ci-ref`, when no `[ci] ref`
is recorded. `files` has a second state arm of its own — a plugin built
before the release record existed carries none, and it says so rather than comparing anything.

**A `skip` does not mean there is nothing to do.** Seven of the sixteen arms carry a remedy:
the two plugin-root skips, `wrapper`'s named-root skip, both of `attached`'s, and the
moved-overlay arm of `pre-commit` and of `overlay-requires`. The dividing line is not "always"
versus "on a state" — every other arm skips on a state and carries nothing: `bundles`,
`store-debris`, `diagnostics` and `ci-ref`, the *no overlay recorded* arms of the two overlay
rows, `overlay-requires`' no-requirement arm, and `files` on a build with no release record. Nor
is it whether some command elsewhere in the report would change the state: `stayfixed setup
--overlay`, which `attached` names when it skips for a machine that records no overlay, changes
the state `pre-commit` skips on there too, and `pre-commit`'s arm still carries nothing. It is
whether the skip is itself worth acting on. Those seven report something wrong that no other
row will tell you: a plugin root nothing can find, a root that will be read and never executed,
a recorded attach the overlay could not confirm, an overlay root recorded and not there. The
other nine report a measurement that is simply unavailable — no store, no overlay, no overlay
requirement, no harness data root, no `[ci] ref`, no release record in this build, no way to ask
Codex — and no command in that row's gift changes it.

**The one to read first is the plugin root**, because it is the quietest and the worst. When
this process can find no plugin root at all, `files` and `wrapper` both skip — two rows, no red,
and every hook entry on this machine silent. Both carry a remedy: run `stayfixed doctor` from the
plugin's own launcher, so its root answers for itself, or set `CLAUDE_PLUGIN_ROOT` to where the
plugin is installed, which lets `files` read the wrapper even though `wrapper` still will not
run it.

One more case is not a skip but produces fifteen of them: with no `stayfixed.toml` in `--root`,
or one that does not load, `not-initialised` goes **red** and every other check skips against it.
The red row is the one to act on. A `stayfixed.toml` that is a symbolic link is one that does not
load, whatever it points at, and the row says it is a link; for any other, the row names
`stayfixed docs check`, which prints the loader's own message.

**What is printed, and what is not. There is no exception.** Counts, statuses, file paths this
project chose and stayfixed's own vocabulary print freely; a repository-authored string does not.
`[stayfixed] version`, `[ci] ref`, a note's filename, a hook's command text, the marker id an
entry claims, every field of the hook sink's diagnostics log and the reason the store would not
resolve are all read and none is quoted back — `stayfixed doctor --json` is relayed to a model
verbatim by the `doctor` skill, so a byte a repository wrote reaching this report is a byte
reaching the model outside `trust.wrap`.

`hook-entries` is where that bites, because its job is to list every entry with its provenance.
It identifies an entry **by position** — `.claude/settings.local.json entry 3 of 5` — which is
what a reader needs in order to open it, survives two entries claiming one id, and reproduces
nothing. A settings file that exists and cannot be read as hook entries is reported by path as
`warn`, never skipped: this is the one check whose whole purpose is that nobody's entries go
unlisted, so "all accounted for" must never mean "could not look". One that is valid JSON nested
deeper than Python's parser follows is reported by path as `red`: a harness may still read it, as
Claude Code does, so the hooks in it may run, and nothing here can check them. A number longer
than Python converts to an integer is read as its text, and the entries beside it are judged as
usual.

`diagnostics` is the same ruling in the other direction, and is why that row counts rather than
quotes. Its three fields are stayfixed's own vocabulary *for a log stayfixed wrote*, and the log
is found through `${CLAUDE_PLUGIN_DATA}` — the same environment class a committed `env` block
reaches — so this command never establishes that. Refusing a marker id that a grammar bounds and
a cap limits, while printing an unbounded free-text `error` from a file of unknown provenance,
would not be a policy. The row reports how many failures are recorded and how many sessions were
seen, and the remedy names the file by its variable; you open it yourself.

**A plugin root the environment named is read and never run.** `wrapper` launches
`hooks/run-hook.sh` only under the root this stayfixed derived from its own module path. With a
wheel installation there is no such root — which is what `uv tool install` gives, and what
`cli-path`'s own remedy suggests — and `CLAUDE_PLUGIN_ROOT` or `PLUGIN_ROOT` may then name one:
that root's wrapper is still read by `files`, for its executable bit, and `wrapper` reports
`skip` saying why. A report that ran a script the inspected repository could commit, and then
called the result green, would be worse than one that says it could not vouch for it.

**Writes** nothing. Exits `0`, or `1` when any check is red.

---

## The reusable workflow

`.github/workflows/check.yml` is a `workflow_call` workflow a project runs its stayfixed gates
through. `stayfixed init` writes the caller —
[`.github/workflows/stayfixed.yml`](#stayfixed-init---yes---dry-run---name-name---base-branch-branch---agent-name----profile-name---memory-mode-mode---local-id----no-ci---root-path---machine-path)
— so most projects never type these lines; what follows is what that file contains, and what to
write by hand if you would rather:

```yaml
on:
  pull_request:
    branches: [main]
    types: [opened, synchronize, reopened, edited]
  merge_group:
    branches: [main]
  push:
    branches: [main]

jobs:
  check:
    uses: stayfixed/stayfixed/.github/workflows/check.yml@<40-hex sha>
    with:
      base: main
```

The branch is named four times, and each one is load-bearing. A pull request into any other
branch runs nothing, so it cannot collect a green check against a looser base and then be
retargeted. `edited` re-runs the check when a pull request is retargeted, and on every title
edit too, because a job filtered out with `if:` reports as skipped, which a required check
counts as passing. `base:` is a literal, so a pull request whose base is not this branch is
refused even where the trigger has been widened by hand. `merge_group` makes the check report
for the gate branch's merge queue and no other: a merge group reports no base the workflow reads,
so with the literal `base:` another branch's queue would be judged against the gate branch's
configuration, and it gets no run, as a pull request into that branch gets none. Each
`edited` run is a job, billed by the whole minute like any other. A pull request into another
branch — one stacked on a feature branch, say — gets no run at all, which blocks nothing as long
as the check is required on the gate branch only.

| Input | Default | Meaning |
|---|---|---|
| `base` | `""` | the branch the gates' configuration is read from; empty means the pull request's base, and on any other event the repository's default branch. On a pull request a value that disagrees with the pull request's own base is refused |
| `path` | `"."` | the project root inside the caller's checkout, for a monorepo or a fixture. A **plain relative path** — letters, digits, `.`, `_`, `-` and `/`, with no `..` component — and anything else is refused before a gate runs, because the value reaches the run's own outputs, and those carry the base commit the gates' configuration is read from. A root any component of which is a symbolic link in the checkout is refused too |
| `python-version` | `"3.13"` | the interpreter stayfixed runs on; 3.11 is the floor |
| `only` | `""` | the checks to run, space-separated: `config` and any configured gate name. Empty runs the configuration check and every configured gate, and the configuration check runs whatever this names |
| `timeout-minutes` | `15` | the job's time limit, a whole number of minutes from 5 to 60; any value the runner does not render as a whole number from 5 to 60 fails the job in its first step, before anything is checked out |

The caller's job needs `contents: read`. That is the default, so the lines above are enough —
but a caller that sets `permissions:` at workflow level replaces the default rather than adding
to it, and a called workflow cannot grant itself a scope the caller did not have.
`permissions: {}` at the top of the calling file therefore fails this workflow at its first
checkout, with an error that names neither the cause nor the remedy. Give the calling job
`permissions: { contents: read }` if the file sets any permissions at all.

**One job, and what it runs.** The job, `gates`, checks out the caller, checks out stayfixed **at
the commit the `uses:` line pins** — read off the platform's own record of which reusable
workflow is running, never off the caller's inputs, and asserted against `git rev-parse HEAD`
before anything else runs — resolves the base to one commit, and runs `stayfixed gate` against it
in two steps. The first, "The configuration and the built-in gates", judges the configuration and
runs the built-in gates, and executes nothing your repository wrote. The second, "The project's
own gates", runs the commands `[gates.custom]` names, and only if the first passed. Each gate is
advisory or enforcing, with every finding as an annotation, and each step that runs a check
appends its results to the job summary. No resolver and no build backend; the network is the two
checkouts, whatever `setup-python` fetches when the runner has no matching interpreter cached,
and, on a pull request that moves `[ci] ref`, one listing of stayfixed's public release tags.
It is one job because a job is billed by the whole minute: a push costs one runner-minute, not
one per gate. Its check, in the caller `init` writes, is `check / gates`.

**The time limit is bounded, and running out still fails.** The job is cancelled after
`timeout-minutes`, 15 unless the caller passes another. The caller `init` writes passes none; a
project whose own gates need longer adds one line under its `with:`:

```yaml
    with:
      base: main
      timeout-minutes: 30
```

The range is fixed at 5 to 60, in this file and not in yours. 5 is the least a healthy run needs —
two full-depth checkouts, an interpreter and two gate runs on a runner that has cached nothing —
and 60 is the most this input lets one run of the job spend of your runner time. The caller file is
pull-request content, so that line is one a pull request can edit, and this is what it can move
through the input: this job's limit, anywhere from 5 to 60, in every run the pull request starts —
one per push, and one per edit of its title, description or base. Through the input it cannot
remove the limit, raise it past 60, or turn running out into a pass: a job that runs out of time is
cancelled, and a required check that was cancelled has not passed. Any value the runner does not
render as a whole number from 5 to 60 fails the job in its first step rather than being quietly
replaced, and whatever was passed, the limit the job runs under stays inside the range.

**What the input does not bound.** The rest of the caller file is pull-request content as well, and
runs as the pull request wrote it: a matrix around the call runs this job once per leg, each leg
with a limit of its own, and a `uses:` pointed at another workflow runs none of this file, under
whatever limit that workflow sets, up to the platform's own 360 minutes. That is a change to
`.github/`, and under the settings below a code owner reviews it before it merges — not before it
runs, since a pull request's run starts before any review.

**Your own gates run on a bare runner.** The second step has the runner image and the
interpreter `python-version` names, and nothing of your project's: a custom gate that needs
your toolchain installs it in its own command, for example `run = ["sh", "-c", "pip install -e
.[test] && pytest -q"]`, and that installation is billed in the same job. Why it is a step of
its own: a custom gate executes files the pull request can change with the runner's privileges,
which on a GitHub-hosted runner include passwordless `sudo`. In the process that decides the
verdict those files could rewrite it; in a later step, only its own results are left to them.
Within that step the base's enforced gates run first, and once one of them has failed no other
custom gate starts, enforced or not, so the process that holds a failing verdict runs nothing
more that the change can edit.
What it guarantees, and how to pin those files, is in the `stayfixed gate` section.

**One row per gate, if you want one.** Each leg of a matrix in your own caller is its own check
row and its own billed job:

```yaml
jobs:
  check:
    strategy:
      fail-fast: false
      matrix:
        only: [docs, bugs, plan, commit, trail]
    uses: stayfixed/stayfixed/.github/workflows/check.yml@<40-hex sha>
    with:
      base: main
      only: ${{ matrix.only }}
```

The list is yours to keep: a gate it leaves out never runs, and a custom gate added to
`stayfixed.toml` needs a leg of its own. Every leg runs the configuration check as well as the
gate it names, because `only:` sits in a file a pull request can edit: a change that loosens
what the base enforces fails every leg. Require every leg's check, not only one.

A leg is also the one real isolation between custom gates. Within one job they share a
checkout, and the base's enforced gates run before every other custom gate for that reason; but
two enforced gates that each run files the change can edit — a test suite and its
`conftest.py`, a `Makefile` — still run one after the other in that checkout, and the first can
rewrite what the second executes. A leg per such gate gives each a checkout no other gate has
touched.

**Where the configuration comes from.** `stayfixed gate` reads `stayfixed.toml` from the base
commit and judges the tree's copy against it key by key; the `stayfixed gate` section has the
table, what each input rests on, and how an owner lands a change it refuses. What this workflow
adds: the base's **name** is the pull request's base as the platform reports it, held against
the caller's `branches:` filter and its literal `base:`; its **commit** is
`refs/remotes/origin/<base>` in the caller's own checkout, resolved once to a full sha that
every gate reads; its **copy** is read at `path:`; the **stayfixed that runs** is the one the
caller's `uses:` line pins, whose commit the judging step passes as `--workflow-sha`; and the
**verdict** is the exit status of the first step.

On a pull request, the tree is the merge commit the platform built from the base as it was when
the event fired, while the base commit is read when the job checks out. A base that tightened
in between makes the change appear to undo that tightening, and the configuration check refuses
it. That fails closed; re-run the job, or update the branch. On a push to the gate branch the
base is the branch's tip when the job checks out, which is usually the pushed commit itself: that
run judges the configuration against itself, it proves the gates run, and the pull request's run
is the one that decided. If a later push has moved the branch by then, the run judges the pushed
commit against that later tip, and fails closed in the same way when the tip tightened.

**What makes the verdict binding.** The caller workflow is part of every pull request: a pull
request can edit its `uses:` line, its `on:` filter and its `base:`, or add a job of its own
named like the required check. A ruleset that requires a workflow can close that where your
plan offers one. Everywhere else the verdict binds under six settings, and without them the
gates still run and still report but cannot stop a pull request that edits its own caller:
- **CODEOWNERS covering `/.github/`, with review from code owners required**, so a change to
  the caller needs someone other than its author. GitHub reads the rules from the base
  branch's copy; keep the file at `.github/CODEOWNERS`, where its own `/.github/` rule covers it
  (`stayfixed assess` warns, `codeowners-scope`, when a line owns only the caller, or when a
  later line with no owner takes a workflow back out of the `/.github/` rule);
- **"Dismiss stale pull request approvals when new commits are pushed"**, or **"Require
  approval of the most recent reviewable push"**, so an approval of an innocuous `.github/` edit
  does not carry over to a later commit that repoints `uses:`;
- **the `check / gates` status check required** (`check` is the caller job `init` writes; a
  caller of your own names its own job), or every leg's check under a matrix;
- **that check's expected source set to GitHub Actions**, not "any source": otherwise anyone
  with write access can post a `success` status of that name through the API, and no file
  changes for a code owner to see;
- **branches required to be up to date before merging, or a merge queue**: a verdict is judged
  against the base as it was when the run started, and a base that tightened since would not be
  seen. The caller subscribes to `merge_group` for the gate branch's queue;
- and one that is stayfixed's, not yours: **a `v*` tag ruleset on the stayfixed repository**,
  because an upgrade is admitted only at a released tag's commit, and a tag that could move
  would move that anchor for every caller.

Whoever may bypass branch protection holds the gate: "Do not allow bypassing the above settings"
decides who that is, and a change the gate refuses lands by the direct push the `stayfixed gate`
section describes.

**Advisory or enforcing, per gate.** A gate is advisory until it enforces: its findings are
warning annotations and the job stays green. An enforcing gate's findings are errors and fail
the job. What enforces is what the base's `[stayfixed] enforced` names, with any gate the change
itself adds there, and every configured gate once `[stayfixed] state` is `installed`.
`stayfixed adopt promote` moves a gate across. Within a step, every gate runs whatever the one
before it said, so a project fixing its documents does not pay a round trip per finding; the one
exception is a custom gate, which is not started once the run has failed. A custom gate runs
in the second step, and only with the command the base gives it ("Which custom gates run" under
`stayfixed gate`). The job's token is `contents: read` and neither checkout
keeps it, and the judging step's verdict was decided before any command started.

**Pin it by SHA.** A reusable workflow's ref is resolved when the run is created, so `@v1` and
`@dev` are a moving stayfixed running against your repository. `stayfixed init` writes that pin,
and writes it from `[ci] ref` in `stayfixed.toml` so that the file and the configuration cannot
come apart: on a repository it initialises from scratch that value is the commit of the released
stayfixed running, read off the public repository's own `v*` tags rather than off anything the
project says; on one that already had a `stayfixed.toml`, it is the ref that file records.
`stayfixed upgrade` moves it, with `[stayfixed] version`, and the file says so in its own first
lines. **A project with no release to pin gets no workflow at all**: before the first stayfixed
tag there is no commit to name, so `init` reports the workflow skipped with the reason and writes
nothing into `.github/`, and `stayfixed upgrade` renders it once a release matches. `@v1` is the
documented opt-in for a project that would rather track the major, written by hand;
`stayfixed upgrade` then moves `[stayfixed] version` alone and leaves the ref and that file as they
are. The alias exists from `1.0.0` on: a `0.x` minor may break what the one before it did, so
there is no `v0` to track, a `0.x` project pins the commit, and until the first `1.x` release
`stayfixed doctor` reports `v1` red, as a tag the public repository does not carry.
`smoke-release.yml` in this repository runs the `owner/repo/…@ref` form on demand, at `@dev` and
at the latest release's tag, so that the branch and tag forms are known to work — it is not a form
this reference tells you to write.

**What proves it.** `tests/test_fixtures.py` and `tests/test_check_workflow.py` run the job's
three scripts, extracted from this file, against real clones: a `base:` naming a branch the
author pushed, a tag named like the base, a change that loosens what the base enforces, a
custom gate that must not run in the judging step, and `only:`. `tests/assess/test_read_base.py`
holds the refusal of a root reached through a symbolic link, which both gate steps run
first. `.github/workflows/smoke.yml` installs this plugin from the checkout with the real
harness CLI under a temporary configuration directory, feeds every `hooks/hooks.json` entry the
event it is filed under through the *installed* wrapper, runs `doctor` over the result, runs the
clone-to-exfiltration scenario — a hostile clone attempting to reach the model through committed
memory — and calls this workflow against the committed fixture project, so the reference above
is checked by a run and not only by this page.

**Checked out with `fetch-depth: 0`.** The base commit, the merge bases `plan` and `bugs` read
and the range `commit` reads all come out of that checkout; a shallow one can lack them or show
an older commit in their place, and the run says so rather than passing over a history it cannot
see. `persist-credentials: false` on both
checkouts, so nothing a gate reads can reach a token.

---

## Shared flags

Six flags mean the same thing wherever they appear, and each has exactly one sentence. Both
tables below are held to `stayfixed.command`'s own constants, row by row, by
`tests/test_documents.py` — so a sentence cannot be spelled by hand here any more than it can be
in a parser, which is the whole point of the rule.

| Flag | What it means |
|---|---|
| `--root` | project root (default: current directory) |
| `--machine` | machine configuration file to read |
| `--store` | resolve the memory store at this path |
| `--dry-run` | report what would change and write nothing |
| `--home` | the home directory to read and write under (default: the real one) |
| `--check` | report drift instead of writing, and fail if there is any |

`--check` is the CI half of `--dry-run`: both read and write nothing, and `--check` fails when
anything differs. `stayfixed bugs index`, `stayfixed docs trail` and `stayfixed memory index` all
take it with that meaning.

Five commands mean something else by a shared name. Each is a **named exception** — a decision
that the flag means something else, not a sentence that drifted — and each has its own constant
beside the six above:

| Command and flag | What it means there |
|---|---|
| `stayfixed overlay create --root` | directory to create it in (default: current directory) |
| `stayfixed overlay init --root`, `stayfixed overlay upgrade --root` | the overlay root (default: current directory) |
| `stayfixed setup --root` | the repository --git-hooks installs into, and the project root --overlay must not be recorded inside of (default: .) |
| `stayfixed setup --machine` | the machine configuration file to write (default: ~/.config/stayfixed/config.toml, the file every reader reads) |
| `stayfixed attach --check` | report the binding, the diff and the groups that never moved, and write nothing |

`attach --check` reports the way the other four do and exits differently on purpose: its `1` is a
binding **mismatch** or a checkout with no `origin`, not a non-empty diff. A diff carrying allow
rules is the ordinary state of a first attach and is exactly what the `--yes` gate exists for — the
refusal `attach` raises names this flag as the way to read that diff first. A `--check` that failed
whenever the run would widen would make the documented remedy itself a failure.

Every command that reads a project takes `--root` and `--machine`, with the meanings in the first
table, whether or not its heading spells them. Neither flag is taken by `stayfixed guard
bg-cleanup`, `stayfixed commit strip`, `stayfixed hook` and `stayfixed overlay publish-template`,
because none of them reads a project: the first two read only what they are handed, `hook` finds
the project from the harness's own event, and `publish-template` renders the shipped overlay
template. The other `overlay` commands take `--root` alone, in the sense the second table gives
it, and read no `stayfixed.toml`; `setup` takes both, in its own senses. `tests/test_documents.py`
holds both lists to the real parser.

---

## Configuration

`stayfixed.toml` in the project root, committed. Every value is repository-controlled, which is
why so few of them are trusted with anything.

```toml
[stayfixed]
version = "0.2.0"        # required; there is no default
state = "installed"      # initialised | adopting | installed — default: initialised
enforced = []            # tool-owned: the gates promoted while adopting
preset = "recommended"
profile = ""
agents = ["claude", "codex"]

[project]
name = "widget"          # one lowercase path segment
base_branch = "main"
release_branch = "main"

[paths]                  # each must stay inside the root, and out of .git and .stayfixed
agents_md = "AGENTS.md"
architecture = "docs/architecture"
runbooks = "docs/runbooks"
adr = "docs/adr"
specs = "docs/specs"
plans = "docs/plans"
bugs = "docs/bugs"
bug_index = "docs/bug-reports.md"
roadmap = "docs/roadmap.md"
roadmap_history = "docs/roadmap-history.md"
memory = "docs/memory"
stayfixed = "docs/stayfixed" # stayfixed's own project files: <stayfixed>/rules/<profile>.md

[memory]
mode = "local-only"      # local-only | in-repo | overlay
groups = ["developer", "project-stable", "project-volatile", "specs"]
index_extra = []         # extra pointers rendered into MEMORY.md

[ledger]
id_prefix = "BR"         # a capital letter, then up to seven more capitals or digits
code_roots = ["src", "tests", "scripts"]
evidence_boundary_required_for = ["high"]

[budgets]                # a project may lower a preset's budget, never raise it
agents_md_lines = 300
agents_md_words = 3000
status_lines = 50
roadmap_prose_lines = 350
roadmap_prose_words = 3500
memory_index_words = 1200
startup_rules_words = 1600
volatile_notes_words = 2500
volatile_ttl_days = 30

[artifacts]
local = []               # scaffold template ids whose artifact is written under
                         # .stayfixed/local/artifacts/ instead of being committed; never
                         # config or gitignore, which only work at the repository root

[ci]
mode = "reusable"        # reusable | uvx | none — how this project means to be gated
ref = ""                 # the commit of the stayfixed release the workflow is pinned to;
                         # `init` writes it; from 1.0.0, `v1` is the mutable opt-in
gate_branch = "main"     # the branch the workflow gates; left out, [project] base_branch

[gates]
builtin = ["docs", "bugs", "plan", "commit", "trail"]  # the built-in gates this project runs
custom_timeout_seconds = 600  # how long one of your own gates may run: a whole number above 0
# [gates.custom.tests]         # zero or more gates of your own, each a table like this
# run = ["pytest", "-q"]       # an argv, never a shell string

[commit_messages]
attribution_check = true # whether `commit check` enforces the attribution block
types = ["feat", "fix", "docs", "test", "refactor", "style", "chore", "harden", "guard"]
```

**Ten sections, and the list is closed**: a section this block does not show is refused when
the file loads (`unknown section(s)`), so the grammar above is the whole of it. All three
`[ci]` keys are read today: `mode` decides whether `stayfixed init` renders a CI workflow at all
and which form, `gate_branch` is the branch the rendered workflow gates — it runs for pull
requests into it and pushes to it, and passes it as a literal `base:`; left out, it is `[project]
base_branch`, so a file that names `develop` as its base gates `develop`, and `stayfixed upgrade`
re-renders a caller you have not edited for that branch where an earlier release gated `main`;
set `[ci] gate_branch = "main"` to keep the old one — and `ref` is written by `init` and judged by
`doctor`'s `ci-ref` row. `[commit_messages] attribution_check` is read by
`commit check`, `[commit_messages] types` by `stayfixed assess`'s commit-vocabulary probe,
`[artifacts] local` by the scaffold engine, and `[gates]` and `[stayfixed] enforced` by
`stayfixed assess`, `stayfixed gate` and the reusable workflow.

Every value above is what a key you leave out takes, from the `recommended` preset — with three
exceptions, and one line that is an example rather than a default. `[stayfixed] version` and
`[project] name` have no default at all and are yours to write: a file without `version` does
not load at all (`[stayfixed] is missing required key(s): version`). And `[stayfixed] state`
defaults to `initialised` — it is one of `initialised`, `adopting` and `installed`, and the
`installed` above shows a set value, not what an omitted key takes. `[ci] gate_branch` has no
preset default: left out, it is `[project] base_branch`, whose default is `main`. Everything else
from `[project] base_branch` down is the preset's default exactly as written. `[project]
base_branch` and `release_branch` are branch names git accepts, from letters, digits, `.`, `_`,
`-` and `/` (the grammar `--base-branch` and `[ci] gate_branch` follow); anything else does not
load, and the refusal names the key and never the value.

**Gates.** A gate is one check run over a pull request. `[gates] builtin` names which of
stayfixed's own five the project runs, all of them by default, and each
`[gates.custom.<name>]` names one of the project's own: `run` is an argv to run from the
project root, never through a shell, given `custom_timeout_seconds` to finish, and a non-zero
exit is its one finding. A custom gate's name is one lowercase path segment, neither a
built-in gate's name nor `config`, which names the configuration check. `stayfixed assess`,
`stayfixed gate` and [the reusable workflow](#the-reusable-workflow) run exactly the configured
gates. A custom gate runs only from a command a person or a workflow runs on purpose, never
from a hook or `doctor`, so running such a command in a clone runs the commands that clone
configured, as running its test suite would. The `docs` and `trail` gates judge tracked files,
so a project that keeps its roadmap or its `AGENTS.md` out of git — ignored, never added, or
written under `[artifacts] local` — drops `trail` or `docs` from `[gates] builtin`: those gates
read the committed place, where in CI the file is not, and `stayfixed assess` reports such a gate
and `stayfixed adopt promote` never enforces it.

**Enforcement is per gate.** `[stayfixed] enforced` lists the gates promoted while a project
adopts stayfixed, and `state = "installed"` means every gate the project runs. Both keys are
stayfixed's to write (`stayfixed adopt promote`), and the loader holds them together: an
`initialised` project lists none, and an `installed` one lists every gate or none. So there are
three shapes and no others: `initialised` with an empty list (nothing has begun), `adopting`
with any list of configured gates, each named once (the adoption has begun, and each gate is
promoted when it passes), and `installed` with every gate or none. `adopting` with the empty
list is one of them: `stayfixed adopt promote` never writes it, since its first promotion lists
a gate, but a person may write it by hand and an earlier release wrote it, and it loads and is
promoted from like any other `adopting` list. The state is kept beside the list because
`initialised` and `adopting` differ even when nothing enforces; any other combination does
not load. A gate enforces when the base branch's list names it, when the change under review
adds it there, or once either side's state is `installed`, so a change that moves the state to
`installed` is held to every gate in its own run; every other gate is advisory.
[The reusable workflow](#the-reusable-workflow) says what each means for a run.

**Which command reads which path.** `agents_md` and `roadmap` are the two documents `docs check`
budgets, and the roadmap is also what `docs trail` writes into; `specs` and `plans` are the two
trees `docs trail` lists, and `plans` is where `plan check` looks for the plans a diff touched.
`bugs` is the ledger's entry directory and `bug_index` its generated index — `bugs new`,
`bugs index`, `bugs check` and `bugs renumber` all read both — and `runbooks` supplies the
`<runbooks>/bug-reports.md` link that index's generated header writes. `memory` is the note
store, which `memory refs` walks. `stayfixed` is the directory stayfixed's own project files go
under, so that `uninstall` can account for them and a reader can find them; a stack profile's
rules are the first, at `<stayfixed>/rules/<profile>.md`. The remaining three are read for their
location alone, and so is every one of the others: `bugs check` treats the first component of
every `[paths]` value that has more than one — `docs`, for the defaults — as a directory
documents live in, and therefore as a place a citation of an entry file may be written and must
resolve. Pointing a path key somewhere unusual widens that sweep; it cannot take a document
outside it, because a value that leaves the root is refused before any command runs.

**`[ledger]`.** `id_prefix` is the one definition of what an identifier looks like: `BR-001`,
and `BR-nnn` in every message. It is interpolated into patterns and filenames, so it is held to
a shape — a capital letter followed by up to seven more capitals or digits — and a prefix
outside it is a refusal (`2`), not a finding. The number is three digits or more. `code_roots`
are the trees `bugs check` sweeps for mentions of an identifier, each of which must have an
entry behind it; `evidence_boundary_required_for` names the severities whose entries must carry
a filled `**What this evidence does not establish:**` line, the template's placeholder not
counting. Widening it is how a project asks the same of `medium`. Each value must be one of the
severities, `high`, `medium` and `low`, spelled as the table below spells it. A value that names
none would require the line of no entry, so it is a refusal (`2`), counted and not quoted, of
every command that reads the ledger — `bugs`, `plan check`, `memory refs`, `init` and `upgrade`
among them — and never of `uninstall`. An empty list is the project asking it of no severity.

**The two ledger vocabularies**, neither of them configurable — they are the entry contract, and
a value outside either is a finding (`1`) naming the file:

| Field | Values |
|---|---|
| `status:` | `open`, `partial`, `fixed`, `rejected`, `void` |
| `severity:` | `high`, `medium`, `low` |

`void` is the one that is not a state of a bug: it records a number that was allocated and never
carried one — what `bugs renumber` leaves behind at the old identifier — and it is the only
status that needs neither `severity:` nor `area:`. `severity` is `bugs new`'s required
`--severity`, and `--area` beside it is free text that becomes the entry's Area column.

**`[budgets]`.** The first five are the documentation budgets `docs check` enforces:
`agents_md_lines`, `agents_md_words` and `status_lines` over the always-loaded document and its
`## Current status` section, `roadmap_prose_lines` and `roadmap_prose_words` over the roadmap
above its trail marker. The last four bound the memory store. A budget is only ever lowered: a
value above the preset's is ignored rather than refused, so raising one is not an escape.

`~/.config/stayfixed/config.toml` is yours, not the project's:

```toml
[personal]
reply_language = ""      # recorded; nothing in this release reads it
artifact_language = "en" # recorded; nothing in this release reads it
preset = "recommended"   # the preset `setup` applies

[overlay]
root = "~/stayfixed-overlay"   # only read in overlay mode
```

`reply_language` and `artifact_language` are kept for you and read by nothing in this release:
they meant something only through the `recommended` preset's standing rule about which language
each audience gets, which the preset no longer carries. To state a language preference, write a
personal standing rule, a note with `metadata.startup` in your overlay's `common/memory/`.

`stayfixed setup` writes a third table, `[machine]`, into the same file — `version`, the
stayfixed that ran, and `installed`, the date it ran. It is `setup`'s record of what it did, not
a setting: it is written, never hand-edited, and a file that has never had one loads fine.

**This file's location is not selectable by a repository.** The path is
`~/.config/stayfixed/config.toml`, and neither `STAYFIXED_CONFIG` nor `XDG_CONFIG_HOME` changes
it: a committed `.claude/settings.json` `env` block would otherwise choose your overlay root
and your trust record. Pass `--machine <path>` to read a different file — a path you typed
rather than one an environment chose, and honoured by every reader of it.

Only `[overlay]` and the trust record used to be held to that rule while `[personal]` followed
the environment, so one command could read the two halves of this file out of two different
files: `[personal]` honoured, and the overlay silently unrecorded a few lines below it.
