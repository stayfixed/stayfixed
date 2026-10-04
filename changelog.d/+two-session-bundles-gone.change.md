The README now says, per agent, what stayfixed enforces where: on Claude Code the session guards
block, on Codex they do not run (Codex ran none of the plugin's hooks when measured), and the
repository gates hold in CI for both.

Two session-start bundles are gone: `preset-rules`, which no shipped preset filled after 0.2.0,
and `index`, which only Codex asked for, and Codex does not run plugin hooks. `memory
session-context --bundle` accepts `standing-rules` and `volatile-notes`; a session starts with
four fewer hook commands.
