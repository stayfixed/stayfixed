stayfixed no longer takes your home directory from `HOME` to find the files it keeps for you, at a
terminal or not. A tool that applies a file the repository commits, such as direnv, mise or a
devcontainer, can set `HOME` for a hook, and a hook runs inside the project, so `HOME=fakehome`
named a directory the repository ships: a `trust.json` committed there approved the repository's
own notes as standing rules with no `stayfixed memory trust` from you. Claude Code's own
`.claude/settings.json` `env` block cannot set `HOME`. The home directory is now the one the
password database records for your user, which no environment variable moves.

- `~/.config/stayfixed/config.toml` and `~/.config/stayfixed/trust.json` are found under that
  home by every command, `stayfixed setup` and `stayfixed memory trust` included, so the file
  you write from a terminal is the one a hook reads. A `~` in `[overlay] root` means that home
  too.
- From your own terminal, `HOME` still decides `--home`'s default and where `stayfixed attach`
  puts the harness memory link, the link under `~/.claude/projects/` through which Claude Code
  reads the project's notes. A `HOME` that is set and empty names no home: there `attach` and
  `stayfixed detach` refuse and `stayfixed setup` fails, saying so.
- Where `HOME` is not the database's home, an empty one included, as in some containers and
  home-manager setups, nothing else is refused, and `stayfixed doctor`'s `ignored-env` row warns
  and names the directory your machine files are under. `stayfixed memory trust` and
  `stayfixed setup` say which directory they wrote under.
- In that case a hook gives no sign that a file under `HOME` is no longer read: approved notes
  stop being injected and `[personal]` falls back to the preset. Move a `config.toml` or
  `trust.json` you kept under `HOME`'s `.config/stayfixed` to the database's home **before**
  running `stayfixed setup` or `stayfixed memory trust`, or merge them afterwards. Move only
  files you put there yourself.
- In that case too, a hook makes no harness memory link, since the harness finds its memory
  through `HOME`; the session is told so and what makes the link, and `stayfixed doctor`'s new
  `harness-link` row says the same. `stayfixed attach` run without a terminal, by an agent say,
  makes none either, says so and what makes one, and does the rest of its work, exiting `0`, and
  `stayfixed doctor`'s `attached` row run there says the same. A link to the store under `HOME`
  is still removed when the store's approval lapses, and `stayfixed detach` removes one under
  either home.
- A user the database lists no home for reads no machine file and no trust record off
  `--machine`. `stayfixed setup` and `stayfixed memory trust` fail and ask for `--machine`, and a
  hook makes no harness memory link. A database home that cannot be written fails the same two
  commands naming the directory.
