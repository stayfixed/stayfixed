`stayfixed plan check` and the `plan` gate settle a backticked path only inside the repository,
by where it really leads: a claim reached through a committed symlink that points out of the tree
is no longer checked against the filesystem, as one spelled with `..` or an absolute path already
was not. Before, such a symlink let a plan ask whether any file on the machine exists, and read
the answer off the findings. A symlink that stays inside the tree is still followed. A path too
long for the filesystem to name, which crashed the check on Python 3.11 to 3.13, is now reported
as a dead reference.
