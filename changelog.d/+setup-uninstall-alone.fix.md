`stayfixed setup --uninstall` without `--git-hooks` now refuses, naming `--git-hooks`, and writes
nothing. It used to drop the flag and run the machine setup, so asking for the commit-message hook
to be removed configured the machine instead.
