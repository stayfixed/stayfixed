The release record `hooks/hashes.json` is gone, and with it the `hashes` command of the
repository's own `scripts/release.py`; `scripts/release.py check` no longer reports release record
drift. `stayfixed doctor`'s `files` row now checks only that `hooks/run-hook.sh` is executable: it
no longer reports a stale `hooks/hooks.json`, an edited wrapper that still runs or a changed
`scripts/stayfixed`, and it no longer skips on a plugin that carries no record.
