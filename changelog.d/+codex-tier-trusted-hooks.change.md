The README and `docs/cli.md` now state what was measured of Codex's hooks on the Codex CLI
`0.162.0-alpha.17.2`: Codex runs a plugin's hooks once they are trusted in `/hooks`, skips untrusted
ones without a message, and passes a blocking `PreToolUse` hook's reason to the model. stayfixed has
not verified its own session guards and notices end to end on Codex, so it claims no tier there, and
the README's table and `stayfixed doctor`'s `codex-trust` row say they are "not verified" on Codex.
