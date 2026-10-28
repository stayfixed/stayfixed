`stayfixed doctor`'s `hook-entries` row reads settings files and nothing else. It no longer walks
the project's skills, commands and agents for frontmatter that declares hooks, so it no longer
names them in a line of information, and `doctor` asks `git` one question fewer. An entry that
carries stayfixed's marker is now counted as stayfixed's in whichever settings file it sits: the
row is no longer red for one in `.claude/settings.local.json` or `~/.claude/settings.json`, no
longer warns for one in a committed settings file, and no longer names entries by their position.
A settings file nested deeper than the check can follow is now a warning in every file, as one it
cannot read already was.
