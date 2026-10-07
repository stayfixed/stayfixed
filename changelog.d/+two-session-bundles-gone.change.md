Two session-start bundles are gone: `preset-rules`, which no shipped preset has filled since
0.2.0, and `index`, which only Codex asked for, and Codex does not run plugin hooks. `memory
session-context --bundle` accepts `standing-rules` and `volatile-notes`, and a session starts with
four fewer hook commands. Two things a script may depend on change with them:

- `memory session-context --bundle index` and `--bundle preset-rules` now exit `2` with a refusal
  naming the bundles that remain (`{"error": "refused", ...}` under `--json`), where they used to
  exit `0`, or `1` where no `stayfixed.toml` loaded or the note store did not resolve;
- the `bundles` object `memory fit --json` prints has lost its `index` and `preset-rules` keys.

A session that was already running when stayfixed was upgraded in place, from a local marketplace
or `--plugin-dir`, can still hold 0.2.0's list of session-start commands, and run through this
release each of those four exits `2`: restart such sessions after upgrading.
