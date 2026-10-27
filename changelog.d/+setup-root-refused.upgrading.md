`stayfixed setup` refuses flags it used to drop, exit `2`, with nothing written:

- without `--git-hooks`, `--root`, which names the repository `--git-hooks` installs into while
  machine setup reads no repository; it used to take the flag, read nothing of it and configure the
  machine. Drop `--root` from a machine setup's command line; `stayfixed setup --git-hooks --root
  PATH` takes it as before;
- without `--git-hooks`, `--uninstall`, naming `--git-hooks`; asking for the commit-message hook to
  be removed used to configure the machine instead;
- with `--git-hooks`, `--overlay`, as it already refused `--preset`, where it used to drop it and
  install the hook, and `--plugin`, which is new in this release.
