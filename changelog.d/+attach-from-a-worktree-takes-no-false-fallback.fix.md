`stayfixed attach` run from a linked worktree no longer says the harness memory link, through which
Claude Code reads the project's notes, could not be created after making it. Every checkout's link
points at the store the owning checkout holds, and the check that follows compared it with the
worktree's own copy of the link tree instead, so the run reported the link as missing and recorded
`autoMemoryDirectory` in that worktree's `.claude/settings.local.json` beside it. The same
comparison made the run say the link waited for `stayfixed memory trust --in-repo-memory` when the
store it linked was already approved. Both now ask about the store the link points at; where a real
directory does stand in the way, the recorded `autoMemoryDirectory` names that store. Re-run
`stayfixed attach` from the worktree to take back a key an earlier run recorded there.
