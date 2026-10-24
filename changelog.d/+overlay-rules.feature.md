Your overlay's rules now reach a bound checkout's sessions. Keep them as `*.md` files in
`common/claude/rules/` and `projects/<name>/claude/rules/`, a project file replacing the common one
of its name: a rule with no `paths:` frontmatter is a standing rule, given to every session at its
start; one with `paths:` (`paths: ["src/**/*.py"]`, relative to the checkout's root) is given the
first time a session reads, edits or writes a file its globs match, once per file in a session,
through a `PostToolUse` entry `stayfixed attach` adds to the rendered plugin only when such a rule
exists. The project is the one this machine's binding names, never the repository's own name for
itself, so an unbound checkout hears no rule.
