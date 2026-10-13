`stayfixed setup` now refuses a `--home` that cannot take what it writes there before it writes
anything, naming the directory you cannot write into. A home it makes nothing in, such as one
holding a writable `.claude` already, is not refused. A home under a read-only directory used to end in `internal error:
PermissionError`, and a read-only home had the machine configuration file written first and was then
refused in words about a symlink that was not there.
