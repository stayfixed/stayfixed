`stayfixed setup --git-hooks --uninstall` now says what it found. It printed `removed
<hook>; there was no foreign hook to restore` whether it removed stayfixed's hook, found no hook
at all, or found a hook stayfixed did not write, which it rightly left in place; in that last case
both halves of the line were false. It now prints `there is no stayfixed hook at <hook>; nothing
was removed` when there is none, and `left <hook> as it was: it is not stayfixed's hook; nothing
was removed` when the hook there is not stayfixed's. `--json` gains `removed` and `foreign`. The
exit code is `0` in every case, as before.
