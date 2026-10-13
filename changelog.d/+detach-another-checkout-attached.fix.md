`stayfixed detach` no longer leaves another attached checkout of the same repository half
attached. With the main checkout and a linked worktree both attached, a detach in either one took
every checkout's link tree, so the other kept its ledger and lost its notes, and the harness memory
link through which Claude Code reads them pointed at nothing. While another checkout still holds
an attach ledger, `detach` now withdraws only its own checkout's harness memory link, settings, rule
copies and ledger, and its link tree unless it is the main checkout, whose tree every checkout's
harness memory link points at; the last checkout to detach takes back the rest, as before. A linked
worktree's harness memory link, which `attach` points at the main checkout's tree, is now
recognised and withdrawn instead of being left behind dangling.
Where a `paths.memory` a harness memory link is compared with cannot be asked where it leads,
`detach` refuses before it withdraws anything and says whether it is the main checkout's or a linked
worktree's, and why: a symlink loop there was an internal error on Python 3.11 and 3.12.
