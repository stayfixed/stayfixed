`stayfixed attach --trust-remote` is gone, and `attach --check` no longer reports a `mismatch` or
`no-origin` state or exits 1 for one: the remote no longer decides the binding. A script that
passed the flag must drop it. A checkout attached by an earlier release has no binding id, so its
store reads as not attached until `stayfixed attach` runs in it once more.
