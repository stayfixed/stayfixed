#!/bin/sh
# stayfixed hook wrapper. $1 = policy (open|closed); the rest is stayfixed's own argv.
#
# This file exists because a Python process cannot fail closed about its own absence:
# a missing script exits 2 by CPython accident, a missing interpreter 127, an ImportError 1,
# a lost executable bit 126 — and Claude Code reads every non-2 exit as a non-blocking error,
# which is permission. Every fault this script can see before the launcher runs prints its own
# token, so the refusal is attributed rather than inferred; Codex downgrades an exit 2 with
# empty stderr to a plain failure, so the reason is part of the contract and not a courtesy.
#
# **Exit 2 is shared with the platform, and that is inherent rather than guarded.** A 2 the
# dispatcher produced is a handler's deny and passes through untouched, so this script cannot
# tell it apart from a 2 CPython produced below it and does not pretend to. What it owns is the
# set of faults it can reach *first* — no policy argument, no interpreter, a launcher it cannot
# read, a project root it cannot enter — and each of those prints a token. An exit 2 carrying no
# token is therefore a deny or a fault beneath this script, which is a narrower promise than
# "never inferred" and is the one the code keeps.
#
# **Every value read here is asked one question: is it a destination, or does it choose a
# program or the provenance of what runs?** `config/machine.py` gives the project's ruling on
# the second kind, because a committed `.claude/settings.json` `env` block applies without a
# trust prompt in a non-interactive session: "Gating one of a pair of equivalent inputs is not a
# partial defence, it is a redirect with a longer name." So the launcher is derived from this
# script's own path, the interpreter list is honoured only from an interactive terminal, `git` is
# chosen from absolute paths *and* asked with an allowlisted environment, and
# `CLAUDE_PROJECT_DIR` stays a destination — but a destination that cannot be entered is a token
# rather than silence.
#
# **`PATH` is the chooser the tty gate did not close, and it is contained rather than dropped.**
# The last candidate below is bare `python3`, resolved through `PATH`, and an `env` block can set
# `PATH` — so gating `STAYFIXED_PYTHON_CANDIDATES` alone moved the choice from one variable to
# another. Dropping the entry is not the answer: a spike measured the need for this last-resort
# fall-through, and a machine whose Python lives under `pyenv`, `nix` or `asdf` has none at any
# of the four absolute paths. What a hostile clone can actually stage is narrower than "any
# `PATH`" — a shipped interpreter plus a `PATH` entry naming its own tree — so **no candidate
# that resolves inside the project root is used**, which costs those installations nothing
# because their interpreter is never under the checkout. It is the containment `setup` applies
# to a recorded overlay root, one layer down. The residue is the case this accepts: a genuinely
# vendored in-tree toolchain refuses under `closed` and degrades under `open`, and `doctor`'s
# wrapper row names it.
#
# **A containment is worth no more than the anchor it measures against, and this one has two.**
# `CLAUDE_PROJECT_DIR` is read out of the same environment a committed `env` block writes to —
# Claude Code 2.1.288 set the real project root over the block's value on the hooks
# `docs/cli.md` records it measured on, but that is one harness's answer on some events, not a
# guarantee this file can lean on — and `git` was a name resolved through the `PATH` that block
# can set — so measuring against either one alone was a redirect with a longer name for the third
# time in this file. Measured:
# `PATH=<clone>` with `CLAUDE_PROJECT_DIR=<outside the clone>` made the clone's own `python3`
# "outside the project root" and it ran the launcher; and on the Codex path, where
# `CLAUDE_PROJECT_DIR` is unset, a clone shipping a `git` had that binary executed on every hook
# invocation, before any guard, with its stdout becoming the anchor. So `git` is now picked from
# absolute paths, and a candidate is refused if it lies under *either* anchor.
#
# **The `/bin/sh` shebang is load-bearing on macOS.** `/bin/sh` is SIP-protected, so `DYLD_*`
# variables are stripped from its environment and never reach the interpreter below. Measured
# with an ad-hoc-signed copy of `/bin/bash` running this file: `DYLD_INSERT_LIBRARIES` reached
# both the probe and the launcher, `-I` notwithstanding. Keep the shebang a protected shell.
#
# **No program this file runs is found through `PATH`, but the interpreter it contains.** Claude
# Code applies a committed `env` block's `PATH` to every hook, and resolves a relative entry against
# the project (measured on 2.1.293), so a command named bare here is one the clone can ship.
# Measured before this rule: a clone's `fakebin/dirname` and `fakebin/env` ran on every hook. So
# every other command below is a shell builtin, the two programs this file needs are named by
# absolute path — `git` from the list below, and `/usr/bin/env`, which every supported system has
# — and `dirname`'s answer is a parameter expansion.
#
# **No function the environment exports stands in for a command this file runs.** bash imports a
# function from every variable named `BASH_FUNC_<name>%%`, in POSIX mode too, so wherever `/bin/sh`
# is bash — macOS, Fedora, Arch — any environment that reaches a hook can define one. A function
# wins over a regular builtin. Measured
# through this file on bash 3.2.57 as `/bin/sh`: a `BASH_FUNC_pwd%%` naming a program in the clone
# ran it five times per hook, past the terminal gate and the containment, with no `PATH` entry at
# all and the hook's answer unchanged; bash 5.2.37 run as `sh` imports the same functions. So the
# first statement removes the function of every name this file runs that is not a special builtin,
# `python3` among them because `command -v` answers a function's bare name and the probe would run
# it, and `command_not_found_handle`, which bash 4 and later call unasked. `unset` itself cannot be
# replaced: in POSIX mode a special builtin is found before any function, and a `BASH_FUNC_unset%%`,
# like one for `set`, `export`, `exit` or `shift`, was measured never to run. The functions defined
# below replace an imported namesake, each before its first use. `[` is spelled `test` throughout,
# because bash 3.2 in POSIX mode refuses `unset -f [` as not a valid identifier, and an imported `[`
# then ran on every test. dash, busybox ash, ksh93 and zsh import no functions and the line removes
# nothing; stderr is discarded because native zsh names each absent one. What the shell acts on
# before this line, `SHELLOPTS` with `PS4` or a loader variable, no line here can refuse, and it is
# the harness's to filter (`SECURITY.md`).
unset -f cd command command_not_found_handle echo printf pwd python3 read test true 2>/dev/null
set -u

refuse() { echo "stayfixed: $1; refusing" >&2; exit 2; }
degrade() { echo "stayfixed: $1; continuing open" >&2; exit 0; }

# Before `set -u` can speak for us. An entry that lost its policy argument would otherwise die
# with the shell's own "unbound variable" and exit 1 — measured as exit 1 with no token on
# /bin/sh (bash 3.2.57), and exit 0 under `zsh --emulate sh`, so the mapping is not even
# portable. A disarmed guard must say so.
test $# -ge 1 || refuse "SF_ARGV no policy argument"
policy="$1"
shift

fail() {
  if test "$policy" = closed; then refuse "$1"; fi
  degrade "$1"
}

# The launcher is derived from this script's own path and never re-read from the environment.
# The harness substitutes the plugin root into the *command string* of `hooks/hooks.json`, so
# the wrapper that runs is always the plugin's own — but a variable of that name reaching this
# process from somewhere else would choose the Python program we then execute, before any
# stayfixed guard runs. Whether a project `env` block can in fact shadow a plugin-provided
# variable is unmeasured, and this does not depend on the answer.
#
# `${0%/*}` is `dirname`'s answer for every path this file is run by, without running `dirname`; a
# bare `run-hook.sh`, given to `sh` or found through `PATH`, is in `.`, and one at `/` is in `/`.
case $0 in */*) here=${0%/*} ;; *) here=. ;; esac
launcher="$(CDPATH= cd -- "${here:-/}/.." && pwd)/scripts/stayfixed"

# Every entry but the dispatcher's relies on `--root` defaulting to the current directory, and
# no harness promises to launch a hook inside the project. Resolved here, once, rather than
# threaded through each entry's argv: CLAUDE_PROJECT_DIR is Claude Code's (Codex sets no such
# name, measured), and `git` answers for both. **Before the interpreter probe**, because the probe
# refuses a candidate that lies inside this root and cannot ask that question before it has one.
#
# **`git` is a program this file chooses, not a destination it is handed.** The containment below
# rests on its answer, so it gets the interpreter's treatment: a fixed list of absolute paths,
# never a `PATH` lookup. This is the Codex hot path, where `CLAUDE_PROJECT_DIR` is unset and
# `git` is the only anchor — and measured there, a clone that ships a `git` and sets `PATH` to
# its own tree had that binary executed on every hook invocation, before any guard of ours, with
# its stdout becoming the root every entry then runs against.
#
# The same list, in the same order, is `stayfixed.gitenv.GIT_CANDIDATES`, where every `git` a hook
# asks inside stayfixed comes from (the launcher's marker, below); `tests/test_git_run.py` holds
# the two equal.
# The machine owner's own installs come before `/usr/bin/git`, so the macOS shim answers only where
# nothing else is installed. No `$HOME`-relative entry (`~/.nix-profile/bin/git`): `HOME` is
# environment-chosen too, so that would be the same hole one directory along.
#
# The first candidate that exists is *the* git. Trying the next one when it answers nothing would
# be shopping for a repository until some program says yes, which is a worse rule than having no
# answer. A machine with `git` at none of these paths has no `git` this process can trust, and
# takes the answer the code already gives for a root it cannot trust: a token, `open` degrading
# and `closed` refusing.
#
# `/usr/bin/env -i` with a *fixed* PATH, and the password database's home as HOME —
# `gitenv.GIT_ENV_KEEP` minus the locale names this query has no use for, and minus the inherited
# `PATH`, which no longer chooses the binary and has no further business here. `HOME` chooses git's
# global configuration, which names programs git runs, and direnv, mise or a devcontainer can set
# it to a directory the clone commits, so it is the home `stayfixed.gitenv.hook_home` hands every
# `git` stayfixed runs below: the database's entry for this user, asked through the shell's own
# `~name` for the name `id -un` gives. `id` is taken as `git` is, from absolute paths and never
# through `PATH`: the system's own, then NixOS's, which has no `/usr/bin/id`. With `/usr/bin/id`
# alone, NixOS got no home, and with it lost a global `safe.directory` and so git's anchor for a
# checkout another user owns. A name that is not a plain one, a user the database lists no
# absolute home for, or a system with `id` at none of these paths gets no `HOME`, never the
# inherited one.
#
# zsh, which `/bin/sh` may be on macOS, expands `~name` from a variable called `name` holding an
# absolute path before it asks the database, as `sh` too, so a variable in the hook's environment
# named for the user chose this home. The lookup therefore runs in a subshell that first unsets
# the variable of that name, spliced into the `eval` so the name is expanded before the unset, and
# the subshell keeps a name equal to one of this file's own variables from touching it. A name no
# variable can have, one with a `.` or a `-` or a leading digit, is not unset: dash and zsh end
# the subshell on `unset` of a name that is not an identifier, which measured as no `HOME` for
# every such user.
#
# `gitenv._git_toplevel` scrubs the identical `env -i` call one layer down and names the failure
# verbatim: an inherited `GIT_DIR` or `GIT_WORK_TREE` makes git answer for a different repository,
# and every `--root`-defaulting entry then reads that repository's `stayfixed.toml`, budgets and
# note store. Measured: `cd repoA; GIT_DIR=repoB/.git GIT_WORK_TREE=repoB <wrapper>` put the
# launcher in repoB.
#
# Asked **here**, in the directory the harness launched us in, and never after the `cd` below:
# with `CLAUDE_PROJECT_DIR` naming a tree elsewhere, a `git` asked from inside that tree would
# answer for it, and the second anchor would be the first one wearing a different hat.
#
# Written out in the `for` rather than held in a variable, unlike the interpreter list below,
# which has to be one because `STAYFIXED_PYTHON_CANDIDATES` replaces it. An unquoted variable is
# not word-split by zsh outside `sh` emulation, so a list in a variable is one long word there
# and no candidate matches; measured under native `zsh`, which refused with `SF_NO_GIT` — safe,
# since the containment still refused and nothing ran, but the wrong reason. Literal words in a
# `for` are words in all five shells this file is verified against.
git_bin=
for g in /opt/homebrew/bin/git /usr/local/bin/git /home/linuxbrew/.linuxbrew/bin/git \
  /run/current-system/sw/bin/git /usr/bin/git /bin/git; do
  if test -x "$g"; then
    git_bin="$g"
    break
  fi
done
test -n "$git_bin" || fail "SF_NO_GIT no git at any absolute candidate path, so no project root this wrapper can trust"
git_home=
git_user=
for i in /usr/bin/id /bin/id /run/current-system/sw/bin/id; do
  if test -x "$i"; then
    git_user=$("$i" -un 2>/dev/null) || git_user=
    break
  fi
done
case $git_user in
  '' | -* | *[!A-Za-z0-9._-]*) ;;
  [0-9]* | *[.-]*) git_home=$(eval "h=~$git_user" 2>/dev/null && printf '%s' "$h") || git_home= ;;
  *) git_home=$(eval "unset -v $git_user && h=~$git_user" 2>/dev/null && printf '%s' "$h") || git_home= ;;
esac
case $git_home in /*) ;; *) git_home= ;; esac
git_root=$(/usr/bin/env -i PATH=/usr/bin:/bin ${git_home:+"HOME=$git_home"} "$git_bin" rev-parse --show-toplevel 2>/dev/null || true)

# `CLAUDE_PROJECT_DIR` still decides the *destination*, which is the question it is allowed to
# answer; what it no longer does is decide it alone for the containment.
root="${CLAUDE_PROJECT_DIR:-}"
test -n "$root" || root="$git_root"
# A root that could not be *resolved* is not fatal: the command finds no configuration and emits
# nothing, which is the correct open degradation. A root that was resolved and cannot be entered
# is a different state and used to be silent — the process stayed in the harness's cwd, and if
# that was another stayfixed project every entry read *its* configuration, with no token and
# nothing in the sink. One token, and `doctor`'s wrapper row surfaces it.
#
# `pwd -P` and not `$root`: the comparison below needs the *resolved* root, or a project reached
# through a symlink is one spelling on one side and another on the other, and the containment
# reads as "outside" for every candidate in it.
#
# `CDPATH=` and `--`, which the other two `cd`s in this file take and this one did not. Measured:
# with `CDPATH` set and a relative root, `cd` **writes the destination it chose to stdout** —
# ahead of anything the launcher prints, and a hook's stdout is a contract the harness parses —
# and lands in a `CDPATH`-chosen directory, so the `pwd -P` below then measures the wrong tree
# and the containment is anchored on it. A root beginning with `-` is parsed as an option
# without the `--`.
project=
if test -n "$root"; then
  CDPATH= cd -- "$root" 2>/dev/null || fail "SF_NO_ROOT the project root this entry was given cannot be entered"
  project=$(pwd -P)
fi

# The second anchor, resolved by the same question so the comparison below is between two
# physical paths. Empty when `git` named nothing, which is simply one anchor fewer. It is not
# compared on its own: it is the first member of the checkout list below, because a checkout is
# what it names.
git_project=
test -z "$git_root" || git_project=$(CDPATH= cd -- "$git_root" 2>/dev/null && pwd -P)

# **Every checkout of this repository, and not only the one the hook runs in.** Both anchors
# above name a single checkout, and a clone's committed bytes reach every checkout of it: inside
# a linked worktree `--show-toplevel` answers the worktree, so the main checkout's own tree --
# and its committed `bin/python3` -- was "outside the project root", reachable through a `PATH`
# entry of `${CLAUDE_PROJECT_DIR}/../../bin` from the same committed `env` block. `setup` already
# holds this rule one area over ("a worktree is not a different repository, and a clone ships
# its own tree into all of them"); this is the wrapper's copy of it. Answered by the same pinned
# `git`, so no new trusted input arrives; one physical path per line, resolved by the same
# question as `project`, and a worktree whose directory is gone contributes nothing.
#
# A function and not a bare substitution: a `case` inside `$( )` is a parse error on the
# `/bin/sh` macOS ships (bash 3.2), which this file has to run under.
list_checkouts() {
  /usr/bin/env -i PATH=/usr/bin:/bin ${git_home:+"HOME=$git_home"} "$git_bin" -C "$git_root" worktree list --porcelain 2>/dev/null |
    while IFS= read -r line; do
      case "$line" in
        "worktree "*)
          tree=$(CDPATH= cd -- "${line#worktree }" 2>/dev/null && pwd -P) && printf '%s\n' "$tree"
          ;;
      esac
    done
}
#
# `git_project` is the list's first member, written here rather than compared separately in
# `in_project`: whenever `git worktree list` answers at all its output contains this path too,
# so a second arm for it was a branch no test could redden -- coverage advertised and not held,
# which is the shape `mutations/` exists to catch (it did: the arm survived its own
# mutation). Kept as a line of its own all the same, because it is the one git anchor that does
# not depend on `worktree list` answering: a `git` that resolves `--show-toplevel` and cannot
# list worktrees must not cost the containment its git anchor entirely. The declared mutation is
# therefore on the list, which a linked worktree can tell apart from this line.
git_checkouts=
test -z "$git_root" || git_checkouts=$(
  printf '%s\n' "$git_project"
  list_checkouts
)

# Whether a resolved interpreter path lies inside the project root. Both sides resolved, which
# is the whole of the care here: `command -v` answers `./python3` for a `.` in `PATH` and
# `<root>/./python3` for a `PATH` entry naming the tree, `<root>/../<root>/bin` is a legal
# spelling of a directory in it, and a `PATH` entry may be a symlink — so the candidate's
# directory is entered and `pwd -P` asked, the same question `project` was built with. The
# directory and not the leaf: a symlink *at* the leaf lives in the tree whoever it points at,
# and the tree is what the clone controls.
#
# **The UNION of the two anchors, and not either one of them** — the destination
# `CLAUDE_PROJECT_DIR` named, and every checkout the pinned `git` names, which is where git's
# own answer enters rather than as a comparison of its own. `CLAUDE_PROJECT_DIR` reaches this
# process from a committed `.claude/settings.json` `env` block — the very channel this
# containment exists to defeat — so measuring against it alone let a clone set `PATH` to its own
# tree *and* name a root outside that tree, and the tree's own `python3` was then "outside the
# project root". Against the union an attacker has to move both anchors at once, and after the
# pinning above one of them is the answer of a binary they do not choose.
#
# **Not a disagreement check**, which is the other shape this could take: refusing when the two
# anchors name different trees. It has no answer when `git` returns nothing — every project that
# is not a git repository — and the only fallback available there is to accept the remaining
# variable on its own, which is this hole again under a longer name. A union needs no fallback,
# because an anchor that is missing simply contributes nothing to it.
#
# **No anchor at all means the candidate stands.** There is nothing to compare against: no
# `CLAUDE_PROJECT_DIR` and no `git` answer is not a project this process can name, and refusing
# every candidate on the strength of a question it could not ask would turn an unresolvable root
# into no hooks at all.
under_root() {
  test -n "$2" || return 1
  test "$1" = "$2" && return 0
  test "${1#"$2"/}" != "$1" && return 0
  return 1
}

in_project() {
  case $1 in */*) dir=${1%/*} ;; *) dir=. ;; esac
  dir=$(CDPATH= cd -- "${dir:-/}" 2>/dev/null && pwd -P) || return 1
  test -n "$dir" || return 1
  under_root "$dir" "$project" && return 0
  # One checkout per line, `git_project` among them: `IFS` is a newline for this split and is
  # restored after it. The only caller is the candidate loop below, which runs under `set -f`,
  # so a `*` in a checkout's path is a character here and not a pattern.
  saved_ifs=$IFS
  IFS='
'
  for tree in $git_checkouts; do
    if under_root "$dir" "$tree"; then
      IFS=$saved_ifs
      return 0
    fi
  done
  IFS=$saved_ifs
  return 1
}

# The probe runs code rather than matching a path: bare `python3` in a hook subprocess can
# resolve to macOS's 3.9, and a path list alone would fall through to it on a machine with no
# python.org or Intel-Homebrew install (a spike measured exactly that fall-through).
#
# `STAYFIXED_PYTHON_CANDIDATES` names the *program* this script executes, and the probe asks it
# only to exit 0 for a trivial `-I -c` — so unguarded it is a redirect with a longer name, and the
# repository-planted interpreter was measured running `<plugin>/scripts/stayfixed hook PreToolUse`
# on every tool call. It is therefore honoured exactly where `config/machine.py` honours
# `STAYFIXED_CONFIG`: from an interactive terminal. A hook's stdin is the harness's JSON payload
# on a pipe and `doctor` hands its own probe `/dev/null`, so neither path can be redirected by an
# `env` block, while a machine owner debugging the probe by hand still gets their list.
#
# The containment is asked **before** the version probe and not after, because the version probe
# *is* an execution: `"$c" -I -c …` runs the candidate, so a candidate that failed the containment
# afterwards would already have run. This is the same order the launcher check follows, and the
# reason the original defect was reachable with three lines of `sh`.
#
# Every execution of a candidate is `-I`, the probe included, because the probe is an execution
# for the reason above: otherwise a `PYTHONPATH` or user site the environment names is imported
# before our first line. `-I` exists in every CPython since 3.4, so a below-floor interpreter still
# reaches the version check rather than an option error. The contract, and the loader variables
# `-I` cannot reach: `docs/cli.md`, "The chosen interpreter starts isolated".
candidates='/Library/Frameworks/Python.framework/Versions/3.13/bin/python3 /opt/homebrew/bin/python3 /usr/local/bin/python3 /usr/bin/python3 python3'
if test -t 0 && test -n "${STAYFIXED_PYTHON_CANDIDATES:-}"; then candidates="$STAYFIXED_PYTHON_CANDIDATES"; fi
p=
skipped_in_project=
# `set -f` for the split: a candidate is a program name or a path, never a pattern, and without
# it a `*` in `STAYFIXED_PYTHON_CANDIDATES` would expand against the cwd before `command -v` saw
# it. It also covers `in_project`'s split of the checkout list. Restored after the loop so
# nothing below inherits the setting.
set -f
for c in $candidates; do
  resolved=$(command -v "$c" 2>/dev/null) || continue
  test -n "$resolved" || continue
  if in_project "$resolved"; then
    skipped_in_project=1
    continue
  fi
  if "$resolved" -I -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' >/dev/null 2>&1; then
    p="$resolved"
    break
  fi
done
set +f
# Silent on a skipped candidate, and named here: a token printed while a later candidate still
# answers would be read by `doctor`'s wrapper row as a refusal that exited 0. This is the one
# message a vendored in-tree toolchain gets, so it says what happened rather than only that
# nothing was found — and the two states really are different states, with different remedies.
#
# They used to share one byte-identical string while this comment claimed otherwise. A developer
# with an in-tree `.venv` and no system 3.11 read "none among the candidates", which is false —
# one *was* found, and deliberately not run — and the one remedy that exists was named only in
# `docs/cli.md` and the changelog, neither of which is where they are standing. So the in-tree
# arm names it here.
if test -z "$p"; then
  if test -n "$skipped_in_project"; then
    fail "SF_NO_PY every python3 candidate found is inside the project root, which this wrapper never runs; install a python3 3.11 or newer outside the checkout, or put one on PATH from outside it"
  fi
  fail "SF_NO_PY no python3 of 3.11 or newer among the candidates"
fi

# Readable and not merely present. `-f` alone let a launcher at mode 000 reach CPython, which
# printed its own `Permission denied` and exited 2 with no token of ours — the unattributed exit
# 2 this file's header is about, and a state `doctor`'s wrapper row read as green because it
# keys on finding a token (measured with `chmod 000`).
test -f "$launcher" && test -r "$launcher" || fail "SF_NO_LAUNCHER launcher missing or unreadable at ${launcher}"

# **The launcher is told this file launched it**, and only then does stayfixed take every `git` it
# runs from the list above, with a fixed `PATH` (`stayfixed.gitenv.git_program`): a `stayfixed`
# run anywhere else, at a terminal or in a CI step, keeps the `git` on its `PATH`. Set here, over
# whatever value was inherited, so an `env` block or a parent that presets it cannot turn that
# off; set anywhere else, it can only make stayfixed's `git` stricter, never looser.
export STAYFIXED_HOOK_WRAPPER=1
# `-I` for the reason the probe takes it.
"$p" -I "$launcher" "$@"
rc=$?
case "$rc" in
  0|2) exit "$rc" ;;
  *) fail "SF_RC stayfixed exited rc=$rc" ;;
esac
