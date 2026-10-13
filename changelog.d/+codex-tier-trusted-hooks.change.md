The README and `docs/cli.md` now state what was measured of Codex's hooks on the Codex CLI
`0.162.0-alpha.17.2`: Codex runs a plugin's hooks once they are trusted in `/hooks`, skips
untrusted ones without a message, and passes a blocking `PreToolUse` hook's reason to the model.
They no longer say Codex runs none of the plugin's hooks. stayfixed has not verified its own
session guards and notices end to end on Codex, so it claims no tier there: the README's table
and `stayfixed doctor`'s `codex-trust` row still list them as not running.
