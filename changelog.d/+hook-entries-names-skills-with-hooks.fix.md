`stayfixed doctor`'s `hook-entries` row now warns about each skill, command or agent file whose
frontmatter declares hooks, saying the row does not judge them. Claude Code 2.1.288 was measured
(macOS, 2026-10-06) running a hook a project skill declared once the skill was invoked, and the row
read settings files alone, so it answered "all accounted for" beside such a file. It reads:

- every `SKILL.md` below the project's `.claude/skills`, at any depth, and below a
  `.claude/skills` anywhere else in the repository, which Claude Code loads once a session reads a
  file in that directory; in a git work tree these are the files git lists, tracked or untracked,
  and those in each checked-out submodule's index, staged or committed, so a skill inside a
  directory git ignores, such as an installed dependency's, is not named;
- every `*.md` below `.claude/commands` and `.claude/agents`, at any depth.

A file is named when the frontmatter between its two `---` lines holds a top-level `hooks` key,
bare, quoted, behind a tag or an anchor, or as a flow mapping's key, `{hooks: {...}}`. Claude Code
2.1.293 ends a frontmatter at a `---` within a line and reads one indented by tabs throughout, so
the row reads it those ways too. It says a file declares none only for plain YAML it reads exactly:
`key: value` lines with plain keys, values on the key's line, block scalars, flow lists of scalars,
nested lines indented by spaces, `- ` entries, comments and blank lines. Any other frontmatter in
which it finds no `hooks` key is named as one it cannot tell about, a description carried on below
its key among them, and so is one of more than 10,000 lines or ending more than 8,388,608
characters into the file, which the row does not read. A file or directory the row cannot read, a
FIFO among them, is named as one it can say nothing of.
A link inside those directories, or a nested `.claude` that is one, is read where it leads inside
the checkout, to a directory or to a `*.md` or `SKILL.md` file. One that leads out of the checkout,
as a dotfiles setup's does, is not followed and is named as one that leads out, which marks no
fault. A link to a file the row would not read, a dangling link and a link that loops are passed
over. Names are compared without case.
Outside a git work tree, looking for nested `.claude/skills` walks the tree instead, skipping
`.git`, up to 500,000 directory entries; the walk follows no link but a nested `.claude/skills` or
`.claude` that is one, and a walk that stops at the bound says so. These are warnings: none makes
the row red or changes the exit code.
