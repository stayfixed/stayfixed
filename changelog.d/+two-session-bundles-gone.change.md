Two session-start bundles are gone: `preset-rules`, which no shipped preset filled after 0.2.0,
and `index`, which only Codex asked for, and Codex does not run plugin hooks. `memory
session-context --bundle` accepts `standing-rules` and `volatile-notes`; a session starts with
four fewer hook commands.
