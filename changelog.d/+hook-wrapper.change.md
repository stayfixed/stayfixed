The hook wrapper now runs the `python3` on your `PATH`, if it is 3.11 or newer, and stayfixed runs
the `git` on your `PATH` in a hook as it does at a terminal, with your `HOME`. The wrapper asks for
`python3` from the project root, so a pyenv, asdf or mise shim answers for the project. A `git`
from nix, MacPorts or mise, or a `python3` only in a virtual environment, used to stop every `Bash`
call or every hook; now it simply answers. `STAYFIXED_PYTHON_CANDIDATES` is no longer read. A fault
of stayfixed's own in a hook — no suitable `python3`, a launcher it cannot read, an internal error,
any non-zero exit — now lets the call through with one line on stderr instead of blocking it, and
`stayfixed doctor`'s `wrapper` row goes red on that line.
