`stayfixed overlay upgrade` no longer renames an overlay's plugin back to `stayfixed-overlay`.
`overlay init` names the three plugin manifests after your account so that two people's overlays
installed side by side do not collide, and an `upgrade` run after it rewrote them from the
template, putting back the shared name and the `your-account` placeholder. A refresh now writes
the template under the name the manifests already carry, so `upgrade` right after `init` changes
nothing, and a release that does change a manifest updates it without losing your name.

`stayfixed overlay init` also no longer stops part-way. A manifest it cannot write is named with a
`cannot be written` line and the others are still renamed and recorded, where before the run
ended with an internal error and every later `upgrade` treated the renamed manifests as
hand-edited. When it replaces `common/memory/README.md` with `_README.md` and cannot write the new
file, or cannot read the template it comes from, it says so and keeps `common/memory/` instead of
removing it as empty, and the old file's record no longer stays behind. It no longer says it
removed a file that was already gone. A refusal over a symlinked directory now names that
directory by its place under the directory being checked (`passes through a symlink at 'skills'`)
rather than by its absolute path on your machine, in every command that reports one.
