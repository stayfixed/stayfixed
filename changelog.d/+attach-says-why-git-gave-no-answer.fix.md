`stayfixed attach`, and every command that asks which checkout owns a worktree, no longer reports
a `git` question that ran out of time, or one asked in a worktree removed while the command ran, as
a `git` that cannot run. The refusal now names the checkout and the cause: a question that ran out
of time on a heavily loaded machine says to run the command again. `attach` skips a worktree that
disappeared after `git worktree list` named it, instead of failing the whole run and leaving every
later worktree unlinked.
