Every file a repository commits that stayfixed reads is now read only up to 64 MiB, and a longer
one is refused as too large, as `stayfixed attach` already refused its own files. Before, these were
read to their end, whatever their size:

- `.gitignore`, which `stayfixed detach` reads to take out the region `attach` wrote there (a
  region `stayfixed init`'s footprint records is left in place, and the file is not read). A
  `.gitignore` past 64 MiB stops `detach` (exit `1`) before it removes anything, as it already
  stopped `attach`, with `.gitignore cannot be read (larger than this reader reads)`. The failure
  no longer prints the file's absolute path on this machine.
- `stayfixed.toml`, which most commands and every hook read first: one past the cap "cannot be read
  (larger than this reader reads)". A named pipe left there made every command and every hook wait
  for good; it is now refused at once, "cannot be read (not a regular file)".
- `.stayfixed/manifest.json`, which `init`, `upgrade`, `uninstall` and `detach` read: one past the
  cap is unreadable, and that refusal no longer prints the file's absolute path either.
- Each file `init` and `upgrade` would write: one past the cap is that artifact's refusal, and a
  named pipe left at its place is refused instead of waited on.
- `MEMORY.md`, which `memory index --check` reports as drifted when it is past the cap, and from
  which `memory index` then takes no entry.
- Each note `memory refs` reads a second time for its line numbers: one past the cap, or one
  removed or replaced between the walk and that read, is now named as a note that could not be
  read, with exit `1`, where it ended in an internal error.
- Each file the bug ledger's reference scan reads: one past the cap is named as a file that could
  not be read.
- The committed settings files `stayfixed assess` reads for its `foreign-hooks` finding: one past
  the cap is one it could not look at.

`CODEOWNERS`, which `assess` reads, and the configuration files a stack profile checks were already
held to bounds of their own by their size on disk. They are now held to them by the read itself, so
a file that grows while it is read cannot pass them.

The overlay's record of a project, `projects/<name>/project.toml`, which is yours and not the
repository's, is read up to 64 MiB as well, and a longer one stops `attach` as a record that cannot
be read.

A file stayfixed cannot read, write or remove is now said why in words, such as `Permission
denied`, `not a regular file` or `larger than this reader reads`, where the message named an error
class or quoted the error's raw text:

- `stayfixed.toml`, the machine configuration file and the overlay's project record say
  `(not a regular file)`, `(Permission denied)` or `(larger than this reader reads)` where they said
  `(IsADirectoryError)` or `(PermissionError)`;
- so do `stayfixed doctor`'s `ci-ref` and `diagnostics` rows;
- `stayfixed init`, `upgrade` and `overlay upgrade` name a file they cannot read relative to the
  tree they write, the project or the overlay, as in `AGENTS.md cannot be read: not a regular
  file`, where the refusal gave its absolute path twice and the error's raw text; this
  holds for a directory in the file's place, a file past the cap and one that is not UTF-8 text;
- `stayfixed uninstall` says why `.stayfixed/manifest.json`, `.stayfixed/assessment.json` or
  `.stayfixed/local/artifacts.json` could not be removed;
- every command that rewrites `stayfixed.toml` (`upgrade`, `init`, `adopt promote`) says why it
  could not be written;
- the refusal over a trust record that cannot be read names it once, with the reason in words.
