`stayfixed setup --git-hooks --uninstall` now says what it found. It printed `removed
<hook>; there was no foreign hook to restore` whether it removed stayfixed's hook, found no hook
at all, or found a hook stayfixed did not write, which it rightly left in place; in that last case
both halves of the line were false. It now prints `there is no stayfixed hook at <hook>; nothing
was removed` when there is none, and `left <hook> as it was: it is not stayfixed's hook; nothing
was removed` when the hook there is not stayfixed's. `--json` gains `found`: `removed`, `absent`
or `foreign`. The exit code is `0` in each of these cases, as before.

A hook at that path that cannot be read, one at mode 000, stayfixed's own or anyone's, is no
longer read as stayfixed's or as a foreign one. `setup --git-hooks` used to rename it to
`prepare-commit-msg.local` and chain it, and `--uninstall` reported it as removed while leaving it
in place, or restored it when it had been chained. Both commands now refuse it (exit `2`) with
`<hook> could not be read (<reason>)`, and leave it where it is.

A FIFO or a directory at that path is not a hook stayfixed wrote, which is always a regular file.
`--uninstall` now leaves it in place and says it is not stayfixed's hook (exit `0`), where it hung
on a FIFO and reported a directory as removed. `setup --git-hooks` refuses a FIFO (exit `2`) with
`<hook> could not be read (not a regular file)`, where it hung, and refuses a directory, saying it
is a directory, as before.

A regular file there longer than the 64 MiB read cap is not stayfixed's hook, which is a couple of
kilobytes, so it is still treated as a foreign one: `setup --git-hooks` keeps it as
`prepare-commit-msg.local` and chains it, and `--uninstall` leaves it in place.
