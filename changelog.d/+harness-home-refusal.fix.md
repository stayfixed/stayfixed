A session in a worktree whose `~/.claude` cannot be used — a `~/.claude` on a volume that is not
mounted, a `~/.claude/projects` moved to another disk, an empty `HOME` — still gets that worktree's
notes. Only the harness memory link is skipped, and the model is told that, rather than that a
memory path was refused.
