`stayfixed attach` and `attach --check` now fail (exit `1`) when the overlay's `common/codex/` or
`projects/<name>/codex/` directory cannot be listed by the user running them, or holds entries that
cannot be asked about, naming the directory and saying nothing was written. Before, both ended in
`internal error: PermissionError` (exit `2`), where a Codex rule file inside the directory that
cannot be read was already a failure naming the file. That file is now named as the directory is,
in quotes with any control character escaped, since the project's path carries `project.name`.
