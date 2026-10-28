`stayfixed doctor`'s `hook-entries` row reads settings files and nothing else. It no longer walks
the project's skills, commands and agents for frontmatter that declares hooks, so it no longer
names them in a line of information, and `doctor` asks `git` one question fewer. The row now
counts the hook entries in the settings files with no claim about who wrote them: it no longer
splits them into stayfixed's and foreign ones by the `# stayfixed:` marker, is no longer red or a
warning for a marked entry in any file, and no longer names entries by their position. A settings
file nested deeper than the check can follow is now a warning in every file, as one it cannot read
already was.
