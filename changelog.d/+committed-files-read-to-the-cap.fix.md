Every file a repository commits that stayfixed reads is now read only up to 64 MiB, and a longer
one is refused as too large, as `stayfixed attach` already refused its own files. Before, these were
read to their end, whatever their size:

- `.gitignore`, which `stayfixed detach` reads to take its region out. A `.gitignore` past 64 MiB
  stops `detach` before it removes anything, as it already stopped `attach`, with
  `.gitignore cannot be read (larger than this reader reads)`. The refusal no longer prints the
  file's absolute path on this machine.
- `stayfixed.toml`, which most commands and every hook read first: one past the cap "cannot be read
  (TooLarge)". One that is a directory now says "cannot be read (NotRegularFile)" where it said
  `IsADirectoryError`.
- `.stayfixed/manifest.json`, which `init`, `upgrade`, `uninstall` and `detach` read: one past the
  cap is unreadable, and that refusal no longer prints the file's absolute path either.
- Each file `init` and `upgrade` would write: one past the cap is that artifact's refusal, and a
  named pipe left at its place is refused instead of waited on.
- `MEMORY.md`, which `memory index --check` reports as drifted when it is past the cap, and from
  which `memory index` then takes no entry.
- Each note `memory refs` reads a second time for its line numbers, and each file the bug ledger's
  reference scan reads: one past the cap is named as a file that could not be read.
- The committed settings files `stayfixed assess` reads for its `foreign-hooks` finding: one past
  the cap is one it could not look at.

`CODEOWNERS`, which `assess` reads, and the configuration files a stack profile checks were already
held to bounds of their own by their size on disk. They are now held to them by the read itself, so
a file that grows while it is read cannot pass them.
