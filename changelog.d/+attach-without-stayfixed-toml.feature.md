`stayfixed attach` now binds a repository that has no `stayfixed.toml`, such as a public clone you
cannot commit to. The project is the one `--project NAME` names, else the one this machine's binding
already records, else the one overlay project whose `project.toml` records the same `origin`, else
the last segment of `origin`'s path, lower-cased. A choice that is ambiguous is refused with
`--project` as the way out, and `--project` beside a `stayfixed.toml` is refused, since the file
names the project.
