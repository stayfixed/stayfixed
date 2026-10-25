`stayfixed uninstall` no longer refuses a repository attached to an overlay. 0.3.1 refused one and
told you to run `stayfixed detach` first; `uninstall` now runs `stayfixed detach` itself, before
its first write, which withdraws the overlay's plugin and the allow rules `attach` placed, and then
takes the scaffold back. From a linked worktree it detaches the main checkout, where `attach` now
keeps its ledger whichever worktree it ran from. Attached means `attach`'s ledger and the render
`attach` keeps outside the repository, which `detach` removes, so a ledger a clone committed
detaches nothing and is refused as a file `uninstall` would not remove. A `note:` line says the
repository was detached, and the dry run says it would be; a run whose plans refuse detaches
nothing and says nothing of detaching. After an `attach` or a `detach` that stopped part-way,
leaving the ledger without the render, `uninstall` refuses it the same way: run `stayfixed detach`,
which finishes from the ledger, then `uninstall`.
