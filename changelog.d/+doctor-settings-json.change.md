`stayfixed doctor`'s settings-fallback row reads `.claude/settings.json` and
`.claude/settings.local.json` through the same JSON reader as every other stayfixed command. A key
given twice (the last one counts, as in Claude Code) and a `NaN` value no longer make the row say
the file could not be read.
