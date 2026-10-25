`stayfixed setup` without `--git-hooks` now refuses `--root`, exit `2`, with nothing written:
`--root` names the repository `--git-hooks` installs into, and machine setup reads no repository.
It used to take the flag, read nothing of it and configure the machine. Drop `--root` from a
machine setup's command line; `stayfixed setup --git-hooks --root PATH` takes it as before.
