`stayfixed attach` no longer writes anything into `.gitignore`. The attach ledger,
`.stayfixed/local/attach.json`, is now hidden from git by the same block in the repository's own
`.git/info/exclude` that hides everything else `attach` places, so an attach leaves `git status`
as it found it and changes no file a collaborator gets. Once that block is written, `attach` asks
git whether each path it places is ignored and refuses, naming the path, when a `.gitignore`
re-includes one with a `!` line. Before writing anything, it also refuses, naming it, any path it
places that the repository tracks, in any ASCII case or as the same file as one the repository
tracks in that directory, so that a tracked `.CLAUDE/Settings.Local.json`, or on macOS
`.claude/ſettings.local.json`, counts where the filesystem folds names; `attach --check` refuses it
too.
`stayfixed detach` no longer touches `.gitignore` either, and its `--json` no longer reports
`ignore_region_removed`: a `stayfixed:ignore` region an earlier `attach` wrote stays until you
remove it, and the region `stayfixed init` writes is unaffected.
