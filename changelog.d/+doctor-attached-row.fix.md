`stayfixed doctor`'s `attached` row now reads a checkout's harness memory link the way `stayfixed
attach` writes it. A linked worktree attached the ordinary way read red, "a link to a directory
that is not this project's note store", because `attach` points every checkout's link at the main
checkout's tree and the row compared it with the worktree's own; a link to either is now
recognised, and one that reaches nothing is still red. Where `attach` took the
`autoMemoryDirectory` fallback beside a real directory at the harness memory path, the row reads
the fallback as in place instead of red; where it did not, the remedy says to move that directory
aside, as `attach` does, instead of removing it, since it can hold notes the harness wrote. Beside
an attach ledger whose note store does not resolve, the row now warns instead of reading green when
no harness link is there, and names the cause: a link tree that is gone is one `stayfixed attach`
puts back, and anything else is for `stayfixed memory index --check` to explain.
