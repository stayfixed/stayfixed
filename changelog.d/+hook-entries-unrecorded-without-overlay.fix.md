`stayfixed doctor`'s `hook-entries` row is red again for a hook entry that claims the stayfixed
marker and that no `.stayfixed/local/attach.json` records, on a machine where the private overlay
is not recorded or cannot be read. A repository could commit a marked entry in
`.claude/settings.json` beside a ledger recording some other entry, and on such a machine the row
withheld its whole provenance column, warned and left the exit code at 0. Whether the ledger
records an entry needs only the ledger, so only the comparison with what the overlay grants is
withheld now; an entry your own ledger records still reads as a warning while the overlay cannot
be asked.
