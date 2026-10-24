Where no layer sets `[memory] mode`, memory is now the coding agent's own: the new mode `harness`
is the default, the preset no longer chooses `local-only`, and stayfixed resolves no store, injects
no `standing-rules` or `volatile-notes` bundle and links nothing into a worktree. A repository that
relied on the old default and keeps notes under `.stayfixed/local/memory/` sets `mode =
"local-only"` under `[memory]` in its `stayfixed.toml`; nothing migrates it. `stayfixed init
--questions` offers `harness` as the memory mode's default.
