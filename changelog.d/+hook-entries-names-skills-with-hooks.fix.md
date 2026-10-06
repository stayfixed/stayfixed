`stayfixed doctor`'s `hook-entries` row now warns about each skill, command or agent file whose
frontmatter declares hooks, saying the row does not judge them. Claude Code 2.1.288 was measured
(macOS, 2026-10-06) running a hook a project skill declared once the skill was invoked, and the row
reads settings files alone, so it used to answer "all accounted for" beside such a file. It reads:

- every `SKILL.md` below the project's `.claude/skills`, at any depth, and below a
  `.claude/skills` anywhere else in the repository, which Claude Code loads once a session reads a
  file in that directory; in a git work tree these are the files git lists, tracked or untracked,
  and those each checked-out submodule commits, so a skill inside a directory git ignores, such as
  an installed dependency's, is not named;
- every `*.md` below `.claude/commands` and `.claude/agents`, at any depth.

A file is named when the frontmatter between its two `---` lines holds a top-level `hooks` key,
spelled bare, quoted either way, behind a tag or an anchor, or as a key of a frontmatter written as
a flow mapping such as `{name: x, hooks: {...}}`; nothing else of the YAML is parsed. A file or
directory the row cannot read, a FIFO among them, is named as one it cannot say anything about. A
link inside those directories that leads out of the checkout, as a dotfiles setup's does, is not
followed and is named as one that leads out, which marks no fault; a link that names no directory
to look in is passed over. Names are compared without case. Outside a git work tree, looking for
nested `.claude/skills` walks the tree instead, skipping `.git` and following no link, up to
500,000 directory entries; a walk that stops there says so. Each of these is a warning: none makes
the row red or changes the report's exit code.
