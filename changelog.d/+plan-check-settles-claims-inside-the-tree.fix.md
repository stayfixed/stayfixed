`stayfixed plan check`, the `plan` gate, `stayfixed docs check`'s link check over the always-loaded
document and `stayfixed memory refs` settle a path only inside the repository, by where it really
leads: a path reached through a committed symlink that points out of the tree is no longer checked
against the filesystem, as one spelled with `..` or an absolute path already was not. Before, such
a symlink let a plan, a link or a note ask whether any file on the machine exists, and read the
answer off the findings. A symlink that stays inside the tree is still followed. A path too long
for the filesystem to name, which crashed each of them on Python 3.11 to 3.13, is now reported as
a dead reference or a missing link.
