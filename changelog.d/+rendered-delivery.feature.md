`stayfixed attach` delivers the hooks, skills and agents you keep in your overlay to Claude Code as
a local plugin. Every run renders them into `~/.local/share/stayfixed/delivery/<id>/`, a
marketplace and a plugin named by the checkout's binding id, and installs it with `claude plugin
marketplace add … --scope local` and `claude plugin install … --scope local`, run from the main
checkout so every worktree gets it; a call that does not succeed fails the attach (exit 1), and the
next `attach` installs again; a session runs the plugin from that directory, so an edit in the
overlay reaches the next session after the next `attach`, with no reinstall; each render is the
overlay as it is, written whole and swapped into place; a copied file keeps its mode, so a skill's
script stays executable. `attach` refuses when the main checkout tracks
`.claude/settings.local.json`, where the install writes, or its `.gitignore` re-includes it, and
in a worktree of a bare repository, which has no main checkout. Codex gets the overlay's rules,
copied into `.codex/rules/`, and none of its hooks, skills or agents.

`stayfixed detach` withdraws the plugin: from the main checkout it runs `claude plugin uninstall
overlay-<id>@stayfixed-delivery-<id> --scope local` where that checkout's
`.claude/settings.local.json` names the plugin, and `claude plugin marketplace remove
stayfixed-delivery-<id>` where it names the marketplace, and removes
`~/.local/share/stayfixed/delivery/<id>/`. The binding id and this machine's record of it stay, so
a later `attach` binds the same checkout again. The line says when the plugin was withdrawn, and
`--json` carries `delivery_removed`. While the settings file still names a `stayfixed-delivery-`
marketplace once the calls ran, the detach fails (exit 1), naming the key left, and keeps the
exclude block, the ledger and the render, so the file stays hidden; running `detach` again
finishes the withdrawal.
