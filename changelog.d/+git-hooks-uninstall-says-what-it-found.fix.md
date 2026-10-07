`stayfixed setup --git-hooks --uninstall` now says what it found. It printed `removed
<hook>; there was no foreign hook to restore` whether it removed stayfixed's hook, found no hook
at all, or found a hook stayfixed did not write, which it rightly left in place; in that last case
both halves of the line were false. It now prints `there is no stayfixed hook at <hook>; nothing
was removed` when there is none, and `left <hook> as it was: it is not stayfixed's hook; nothing
was removed` when the hook there is not stayfixed's. `--json` gains `found`: `removed`, `absent`
or `foreign`. The exit code is `0` in each of these cases, as before.

A hook at that path that cannot be read is no longer read as stayfixed's or as a foreign one,
and a FIFO there is no longer waited on. Both commands now refuse (exit `2`), with `<hook> could
not be read (<reason>)`, and leave what is there where it is:

- a FIFO, on which `setup --git-hooks` and `--uninstall` used to hang;
- stayfixed's own hook at mode 000, which `--uninstall` used to report as removed while leaving it
  in place, and `setup --git-hooks` renamed to `prepare-commit-msg.local` and chained;
- a directory, which `--uninstall` used to report as removed (exit `0`); `setup --git-hooks`
  already refused one, saying it is a directory.

A regular file there longer than the 64 MiB read cap is not stayfixed's hook, which is a couple of
kilobytes, so it is still treated as a foreign one: `setup --git-hooks` keeps it as
`prepare-commit-msg.local` and chains it, and `--uninstall` leaves it in place.
