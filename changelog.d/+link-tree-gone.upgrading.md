`stayfixed attach` no longer builds the link tree under `paths.memory` in each checkout, no longer
makes the harness memory link `~/.claude/projects/<slug>/memory`, and the `SessionStart` step that
linked a worktree is gone: in `overlay` mode the harness, and now stayfixed's own `memory` commands
and bundles, read the composed store `~/.local/share/stayfixed/stores/<id>/` that
`autoMemoryDirectory` in the main checkout's `.claude/settings.local.json` names. `attach` and
`detach` act on the main checkout whichever worktree they run from: its settings file, its
`.codex/rules/` copies and its ledger, so a worktree needs no step of its own and `detach` has no
"another checkout is still attached" case left. A memory group still sitting as a real directory
under `paths.memory` no longer refuses `attach`, and `attach --check` no longer reports
`real_directories` or exits `1` for one, since nothing reads that directory in `overlay` mode;
`attach`'s `--json` loses `links_created` and `links_revoked`, and `detach`'s `links_revoked`,
`exclude_block_kept` and `link_tree_kept`. `doctor`'s `attached` row reads the pointer from the
main checkout's settings file in place of judging the harness memory path. Neither `attach` nor
`detach` removes what an earlier release placed: delete the links under `paths.memory` in each
checkout, and `~/.claude/projects/<slug>/memory` for each, by hand, and detach a checkout an
earlier release attached from a linked worktree before upgrading, since its ledger is that
worktree's. In `overlay` mode the `memory` commands no longer read `--store`, so a script that
pointed them at another directory there now reads the composed store; in every other mode
`--store` works as before.
