`--json` is read only before a bare `--` on the line: the words after `--` are a command's own,
so `stayfixed prove -- COMMAND --json` hands `--json` to `COMMAND` and prints the line.
