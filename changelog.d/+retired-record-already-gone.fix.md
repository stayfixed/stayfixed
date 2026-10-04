`stayfixed upgrade`, `stayfixed overlay upgrade` and `stayfixed overlay init` no longer keep the
record of a file they retire after you have already deleted it. Such a file was read as unchanged,
so `.stayfixed/manifest.json` carried its record into every later run. It is now listed as
`remove … (retired, already gone)` and its record is dropped, with nothing removed. In an overlay
whose old `common/memory/README.md` was deleted by hand, `overlay init` now also writes
`_README.md` in its place, as it does when it removes the old file itself.
