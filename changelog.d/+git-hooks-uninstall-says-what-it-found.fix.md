`stayfixed setup --git-hooks --uninstall` now says what it found. It printed `removed
<hook>; there was no foreign hook to restore` whether it removed stayfixed's hook, found no hook
at all, or found a hook stayfixed did not write, which it rightly left in place; in that last case
both halves of the line were false. It now prints `there is no stayfixed hook at <hook>; nothing
was removed` when there is none, and `left <hook> as it was: it is not stayfixed's hook; nothing
was removed` when the hook there is not stayfixed's. `--json` gains `found`: `removed`, `absent`
or `foreign`. The exit code is `0` in each of these cases, as before.

A hook at that path that cannot be read is no longer read as a foreign one, and a FIFO there is
no longer waited on: `setup --git-hooks` and `--uninstall` hung on a FIFO, `--uninstall` said
"it is not stayfixed's hook" of stayfixed's own hook at mode 000, and `setup --git-hooks` renamed
that hook to `prepare-commit-msg.local` and chained it. Both now refuse (exit `2`) with `<hook>
could not be read (<reason>)`, and leave the hook where it is.
