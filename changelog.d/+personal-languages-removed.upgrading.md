`[personal] reply_language` and `artifact_language` are gone: nothing read them, and `setup` no
longer writes them or offers them as plugin options. Delete both lines from your machine file,
`~/.config/stayfixed/config.toml`. Until you do, a command that reads it prints one note per key on
stderr ("[personal] has a key this stayfixed does not read: … it is ignored"), a session opens with
a warning that the machine file could not be used whole, and `stayfixed doctor`'s `preferences` row
is a warning. Nothing is refused.
