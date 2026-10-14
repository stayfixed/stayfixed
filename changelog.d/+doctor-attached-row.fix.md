`stayfixed doctor`'s `attached` row now reads a checkout's harness memory link the way `stayfixed
attach` writes it, and reads one machine state the same way from every checkout. A linked worktree
attached the ordinary way read red, "a link to a directory that is not this project's note store",
because `attach` points every checkout's link at the main checkout's tree and the row compared it
with the worktree's own; a link to either is now recognised. A link that reaches nothing is red from
every checkout: with the main checkout's link tree gone, the main checkout used to warn while a
worktree said red. Where `attach` took the `autoMemoryDirectory` fallback beside a real directory at
the harness memory path, the row reads the fallback as in place only while the store's approval
holds, and warns otherwise, as `attach` withdraws the key there: after one changed note, or for a
store nobody approved whose clone commits the key, the harness reads notes nobody approved, and the
row said ok. The value is compared exactly as written with the one directory `attach` writes there,
the main checkout's store, and never with a checkout's own `paths.memory`: a branch that commits
that path as a link beside a key naming where it leads is red, not ok. Where there is no such
fallback, the remedy says to move that directory aside, as `attach` does, instead of removing it,
since it can hold notes the harness wrote. With no harness link in place, an approval that lapsed
now warns with the way to re-approve, instead of reading green as though the store had never been
approved, and a linked worktree asks about the main checkout's store, as `attach` does, instead of
its own. Beside an attach ledger whose note store does not resolve, the row warns instead of reading
green and names the cause: a link tree that is gone is one `stayfixed attach` puts back, and
anything else is for `stayfixed memory index --check` to explain. Where, from a linked worktree, the
main checkout's `paths.memory` cannot be asked where it leads (reached through a symlink, a symlink
loop, or a fault the system names), and where this machine's trust record cannot be read, the row
warns and says which, instead of "this check could not run".
