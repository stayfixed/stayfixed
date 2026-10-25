`stayfixed setup --uninstall` without `--git-hooks` now refuses, naming `--git-hooks`, and writes
nothing. It used to drop the flag and run the machine setup, so asking for the commit-message hook
to be removed configured the machine instead. In the other direction, `stayfixed setup --git-hooks`
now refuses `--overlay` as it already refused `--preset`, where it used to drop it and install the
hook, and it refuses `--plugin`, which is new in this release, the same way.
