The Claude Code plugin is now installed from `stayfixed/stayfixed-plugin`, at the release's tag: a
repository holding only what the plugin runs — its two manifests, the hooks and their wrapper, the
launcher, the `stayfixed` package, the skills, the agents, the README and the licence — where the
plugin used to be this whole repository, tests, plans and tooling included. The marketplace stays
in `stayfixed/stayfixed`, so the install commands do not change. Each release attests the plugin
tree it publishes, and its GitHub Release carries that tree's manifest, `plugin-tree.txt` — one
line per file with its mode, its sha256 and its path — so the plugin repository's tag can be
compared with what the release built.
