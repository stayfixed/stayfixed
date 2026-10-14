`stayfixed setup` now refuses a `--home` that cannot take what it writes there before it writes
anything, naming the directory you cannot write into. A home it makes nothing in, such as one
holding a writable `.claude` already, is not refused. A home under a read-only directory used to end
in `internal error: PermissionError`, and a read-only home had the machine configuration file
written first and was then refused in words about a symlink that was not there. A `--settings`
directory you cannot write into is now refused the same way, before anything is written, and so is a
directory the settings write opens to read and you cannot read, such as a `.claude` at mode 300. So
is every other path `setup` cannot ask about before its first write, naming it: an `--overlay`, a
`--root` or a `--settings` directory below a directory nobody may search, and an existing `--overlay
create:` destination that cannot be searched, each used to end in an internal error. A regular file
at `<home>/.claude`, or a directory at `<home>/.claude/settings.json`, is refused too, before
anything is written, where the machine configuration file was written and reading the settings file
then failed (exit `1`).
