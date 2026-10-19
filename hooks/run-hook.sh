#!/bin/sh
# stayfixed hook wrapper: runs the launcher beside it under the `python3` on PATH, with `-I`.
# Any fault, the launcher's non-zero exit included, is exit 0 with one line on stderr, so a session
# never dies of stayfixed's own fault. `/bin/sh` is SIP-protected on macOS, so `DYLD_*` variables
# never reach the interpreter below; keep the shebang a system shell.
skip() { echo "stayfixed: $1; continuing open" >&2; exit 0; }

case $0 in */*) here=${0%/*} ;; *) here=. ;; esac
launcher="$(CDPATH= cd -- "${here:-/}/.." && pwd)/scripts/stayfixed"
test -f "$launcher" && test -r "$launcher" || skip "no readable launcher at $launcher"

# An inherited GIT_DIR or GIT_WORK_TREE would make every git answer about another repository.
unset GIT_DIR GIT_WORK_TREE
# Every entry but `hook` reads its `--root` default, the directory it runs in, as the project, and
# a version manager's `python3` answers for the directory it runs in, so both are asked from there.
root=${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null)}
test -z "$root" || CDPATH= cd -- "$root" 2>/dev/null || skip "cannot enter the project root $root"

python=$(command -v python3) || skip "no python3 on PATH"
"$python" -I -c 'import sys; sys.exit(sys.version_info < (3, 11))' >/dev/null 2>&1 ||
  skip "$python is not python 3.11 or newer"
"$python" -I "$launcher" "$@" || skip "stayfixed exited $?"
