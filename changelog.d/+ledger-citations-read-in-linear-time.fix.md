`stayfixed bugs check`, the `bugs` gate and `stayfixed bugs index` now read citations of the
ledger's entry files, and the generated index's marker, in time linear in a file's length, with the
same findings. A file of 160,000 citations took 36 s, since each one's line was counted from the
file's start; a run of 8,000 `../` before no citation took 0.7 s; a marker of 16,000 `index` words
that no backtick closes took 2.6 s; each doubling took four times as long. A citation behind a
million path segments also took 140 MiB more memory to read; it now takes none.
