`stayfixed memory index` now takes a note's index line from `metadata.index` when the note has no
top-level `index:`, ahead of a line `MEMORY.md` already lists for it and of its `description`.
Before, a note carrying its short line under `metadata:` got its description as its `index:` line,
or the description another writer had appended to `MEMORY.md`, recorded as `native`. The line is
written into the note as `index:` with `index_provenance: provisional`, as a line made from the
description is, so a later edit to `metadata.index` does not reach the index until that `index:`
line is changed or removed. The run's summary now names the notes it wrote a provisional line into.
A note the old behaviour already rewrote, with its description as a top-level `index:` line marked
`index_provenance: native`, is left as it is: delete that `index:` line and the next run takes
`metadata.index`.
