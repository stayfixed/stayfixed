`stayfixed setup` no longer installs plugins unasked. `setup --preset recommended` used to install
`superpowers` and `context7` on Claude Code on every run; it now installs a plugin only when
`--plugin NAME` names it, once per plugin, and `stayfixed init --questions` offers the two the
preset recommends (`[plugins] recommended`, which replaces `[plugins] install`). Run
`stayfixed setup --plugin superpowers --plugin context7` to install them as before; nothing
already installed is removed. `setup` also no longer overwrites a value in `pluginConfigs` in
`~/.claude/settings.json`: a value there, such as one set in Claude Code's plugin-config screen,
is kept, and a personal value is copied there only where none is. A personal value changed in the
machine file after the first `setup` is changed in `pluginConfigs` by hand too.
