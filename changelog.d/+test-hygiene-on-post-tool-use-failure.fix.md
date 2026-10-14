The red-run note now reaches a failed test run on Claude Code. Claude Code reports a `Bash` command
that exits non-zero on its `PostToolUseFailure` hook event, never on `PostToolUse`, and the note was
registered on `PostToolUse` alone, so it never spoke after a red run there. The plugin's
`hooks/hooks.json` gains a `PostToolUseFailure` entry for `Bash`, which runs the same note: once per
session, from the exit code at the head of the failure's `error`, saying nothing when the `error`
does not begin with one, or begins with a run of more than nine digits, which no exit code has. The
`PostToolUse` entry stays as a placeholder for parity with Codex: no measured harness delivers an
exit code on that event, and Codex delivers a failed command there with none, so the note does not
speak there. The two share one once-per-session delivery, so a session gets at most one note,
whichever event carries it. Codex reads the same file and ignores the new key.
