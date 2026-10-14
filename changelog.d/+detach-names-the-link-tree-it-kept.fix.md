`stayfixed detach` run in the main checkout while a linked worktree is still attached now says it
kept this checkout's link tree, which the worktree's harness memory link points at, beside the
exclude block it already said it kept, and `--json` reports it as `link_tree_kept`. Before, the
line named the block alone, and the tree a detach had left on purpose read as one it forgot.
