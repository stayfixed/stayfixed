`stayfixed attach` binds a checkout by a random binding id it keeps in the repository's git
common directory, which every worktree of the repository shares, and records on this machine what
that id is bound to, in `~/.local/share/stayfixed/bindings/`. A clone never carries the id, so a
repository that names itself after one of your projects is not bound to it; the id never leaves
the machine and is printed only as its first eight characters. A checkout with no `origin`, or one
whose `origin` differs from the remote it was bound with, now attaches and keeps its notes: the
command and the session-start line say so, naming both remotes, and refuse nothing for it.
