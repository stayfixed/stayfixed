0.4.0 and 0.5.0 were never published: this release carries what both were to ship, so every entry
under it is a change from 0.3.1. No code migrates an installation. On a machine whose checkouts
0.3.1 attached to an overlay, take these steps in this order; each is described in its own entry
below.

1. Before upgrading, run `stayfixed detach` in a checkout an earlier release attached from a linked
   worktree: its ledger is that worktree's, which this release no longer reads.
2. Upgrade the command with `uv tool upgrade stayfixed`. A plugin added from the marketplace at an
   earlier release's tag, such as `@v0.3.1`, cannot be added again at the new one (Claude Code refuses a source that differs from
   the one its settings record), so remove the marketplace, which uninstalls the plugin and its
   saved options, and add it again:
   `/plugin marketplace remove stayfixed-marketplace`, then
   `/plugin marketplace add stayfixed/stayfixed@vX.Y.Z` and
   `/plugin install stayfixed@stayfixed-marketplace`.
3. Add `stayfixed-overlay.toml` at the overlay's root, holding `requires = ">=0.1.0"` and
   `layout = 1`, then run `stayfixed overlay upgrade --root <overlay>`, with `--dry-run` first,
   which removes the overlay's retired `hooks/hooks.json` or names it where you edited it.
4. Delete the links under `paths.memory` in each checkout and `~/.claude/projects/<slug>/memory`
   for each, and the `reply_language` and `artifact_language` lines under `[personal]` in
   `~/.config/stayfixed/config.toml`.
5. Run `stayfixed setup --overlay <overlay>`, which records the overlay, installs its commit-time
   secret scan and copies your personal values into the plugin options the removal took; then
   `stayfixed attach` once in each checkout, which gives it a binding id.
6. Read your notes, then run `stayfixed memory promote --changed` once to keep them as standing
   rules.
7. Run `stayfixed upgrade` in each repository whose `stayfixed doctor` warns on its `versions` row.

New for a project to opt into: a fixed bug entry can name a test under `regression`, which
`stayfixed bugs regressions` runs as a custom gate (under Added); the entry on `regression` below
says which stayfixed can read such an entry.
