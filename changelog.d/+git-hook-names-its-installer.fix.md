The `prepare-commit-msg` hook that `stayfixed setup --git-hooks` installs no longer says, in its
own comment, that no `stayfixed` subcommand installs it: it names `stayfixed setup --git-hooks`,
and `stayfixed setup --git-hooks --uninstall` as the way to remove it. A hook an earlier release
installed keeps working and is still recognised as stayfixed's; run `stayfixed setup --git-hooks`
again to replace its text with the new one.
