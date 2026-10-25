`stayfixed uninstall` run in a linked worktree of an attached repository detaches the main checkout
first, as it does in the main checkout itself: `attach` keeps its ledger in the main checkout
whichever worktree it ran from, and the worktree's uninstall used to take its own scaffold and
leave the main checkout's delivery in place with nothing recording it.
