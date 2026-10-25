`stayfixed setup --uninstall` without `--git-hooks` now refuses, naming `--git-hooks`, and writes
nothing. It used to drop the flag and run the machine setup, so asking for the commit-message hook
to be removed configured the machine instead. In the other direction, `stayfixed setup --git-hooks`
now refuses `--overlay` and `--plugin` as it already refused `--preset`, where it used to drop them
and install the hook.
