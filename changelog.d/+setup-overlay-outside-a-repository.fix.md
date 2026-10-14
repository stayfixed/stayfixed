`stayfixed setup --overlay` now judges where an overlay may live against the repository `--root` is
in. `stayfixed setup --overlay create:<owner>/<name> --yes` run in a home directory that is not a
repository (no `.git` at or above it) is no longer refused for creating the overlay inside it, and
neither is the same command run again over the clone it made: a `create:` destination is the one
overlay exempt from the comparison with a `--root` in no repository, because the run makes it. An
overlay already on disk inside, around or equal to such a `--root` is still refused, because a
project downloaded as an archive, or a checkout of another version control system, can ship one.
Run in a home that is a git work tree with its `.git` there, such as a dotfiles clone, `create:` is
still refused before anything is created on GitHub. A home whose dotfiles repository keeps its git
directory elsewhere, reached through `--git-dir` and `--work-tree`, and one another version control
system tracks, have no other checkouts compared. Inside a checkout, a `git` that exits non-zero, is
ended by a signal or prints nothing is now a refusal, where it was read as no repository and the
project's other checkouts went uncompared. An overlay inside a checkout of any other repository,
including a checkout of its own nested inside one, is now refused wherever `--root` is, and so is
a linked worktree of the overlay's own repository nested in another checkout of it, in words that
say it is the overlay's own repository.
