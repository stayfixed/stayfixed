The `bg-cleanup` guard's `PreToolUse` hook now blocks the tool call when it cannot answer at all —
it runs past its timeout, or its wrapper cannot start — where Claude Code used to let the call
through. This needs Claude Code 2.1.295 or later, and a session whose hook cannot start then runs
no `Bash` call until the plugin is repaired. The Read, Edit and Write tools still work there, and
`/plugin` turns the plugin off meanwhile; `docs/cli.md` under "Hooks" names the other way out.
