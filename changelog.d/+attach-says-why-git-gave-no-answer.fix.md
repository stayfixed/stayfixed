`stayfixed attach`, and every command that asks which checkout owns a worktree, no longer reports
a `git` question that ran out of time, a `git` a signal ended, or a question asked in a worktree
removed while the command ran, as a `git` that cannot run. The refusal now names the checkout and
the cause: a question that ran out of time on a heavily loaded machine, or a `git` ended by a
signal, says to run the command again, and only a `git` that cannot start or fails even
`git --version` says to check that `git` runs. A `git` a signal ended no longer reads as a worktree
that is its own main checkout, which had linked nothing into it without saying so. `attach` skips a
worktree that disappeared after `git worktree list` named it, instead of failing the whole run and
leaving every later worktree unlinked.
