The README now says, per agent, what stayfixed enforces where: on Claude Code the session guards
block, on Codex they do not run (Codex ran none of the plugin's hooks when measured), and the
repository gates hold in CI for both. `stayfixed doctor`'s `codex-trust` row says the same when
`[stayfixed] agents` lists `codex`: its detail now names the session guards and session notices
as not running on Codex and the repository gates as holding in CI. The row is still a skip.
