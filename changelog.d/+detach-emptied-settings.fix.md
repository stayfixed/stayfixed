`stayfixed detach` no longer leaves `.claude/settings.local.json` behind in a checkout that had none
before `attach`. Claude Code's `plugin uninstall` and `marketplace remove` leave the file holding
`enabledPlugins` and `extraKnownMarketplaces`, emptied, and once `detach` took its exclude block
away that file showed in `git status` as untracked, unless a global exclude of yours hid it. A file
holding only those two empty keys is now removed; one holding anything more stays as it is.
