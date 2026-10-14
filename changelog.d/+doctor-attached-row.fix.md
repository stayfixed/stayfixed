`stayfixed doctor`'s `attached` row now reads a checkout's harness memory link the way `stayfixed
attach` writes it, and reads one machine state the same way from every checkout. A linked worktree
attached the ordinary way read red, "a link to a directory that is not this project's note store",
because `attach` points every checkout's link at the main checkout's tree and the row compared it
with the worktree's own; a link to either is now recognised. A link that reaches nothing is red from
every checkout, where the main checkout warned once its own link tree was gone. The row now reads
`autoMemoryDirectory` in `.claude/settings.local.json` beside whatever stands at the harness memory
path, since the harness reads the directory it names: a value other than the one `attach` writes
there, the main checkout's store exactly, is red beside a link, a real directory or nothing, where a
committed key read ok beside a link or nothing. A real directory at the harness memory path, always
red before, is in place beside the value `attach` writes while the store's approval holds, and warns
while it does not; with no such key it is still red, and the remedy now says to move the directory
aside, as `attach` does, instead of removing it, since it can hold notes the harness wrote. A link
to the store, read green whatever the trust record said, now warns where the approval lapsed, with
the way to re-approve, where none was given, and where this machine's trust record cannot be read;
with nothing in place, a lapsed approval warns too instead of reading as one never given, and a
linked worktree asks about the main checkout's store, as `attach` does, instead of its own. Beside
an attach ledger whose note store does not resolve, nothing in place warns instead of reading green
and names the cause: a link tree that is gone is one `stayfixed attach` puts back, and anything else
is for `stayfixed memory index --check` to explain. Where a linked worktree's main checkout's
`paths.memory` cannot be asked where it leads (reached through a symlink, a symlink loop, or a fault
the system names) the row warns and says why, and a trust record that cannot be read beside nothing
in place is a warning that says so, instead of "this check could not run".
