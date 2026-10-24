`stayfixed uninstall` run in a linked worktree of an attached repository refuses and says to run
`stayfixed detach` first, as it does in the main checkout: `attach` keeps its ledger in the main
checkout whichever worktree it ran from, and the worktree's uninstall used to proceed.
