`stayfixed doctor`'s `ci-ref` row now reads the workflow's `uses:` lines in time linear in the
file's length, with the same pins. A workflow of nothing but `uses:` repeated, at the 256 KiB the
row reads, took ten seconds, since each one was read on to the file's end.
