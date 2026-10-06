`stayfixed doctor`'s `hook-entries` row now warns about each project skill whose
`.claude/skills/<name>/SKILL.md` frontmatter declares hooks, saying the row does not judge them.
Claude Code 2.1.288 was measured (macOS, 2026-10-06) running a hook a project skill declared once
the skill was invoked, and the row reads settings files alone, so it used to answer "all accounted
for" beside such a skill. The skill is found by a `hooks:` key at the start of a line between the
frontmatter's two `---` lines, and nothing else of the YAML is parsed. A `SKILL.md` the row cannot
read, a link to a device among them, is named as one it cannot say anything about. Both are
warnings: neither makes the row red nor changes the report's exit code.
