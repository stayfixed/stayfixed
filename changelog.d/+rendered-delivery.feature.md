`stayfixed attach` delivers the hooks, skills and agents you keep in your overlay as a local
plugin. Every run renders them into `~/.local/share/stayfixed/delivery/<id>/`, a marketplace and a
plugin named by the checkout's binding id, and the first attach installs it with
`claude plugin marketplace add … --scope local` and `claude plugin install … --scope local`, run
from the main checkout so every worktree gets it; a session runs the plugin from that directory, so
an edit in the overlay reaches the next session after the next `attach`, with no reinstall. No
hook entry goes into `.claude/settings.local.json` any more: it keeps only the allow rules `attach`
merges, and the entries an earlier release merged there are taken back, the ones its ledger
records and no other. `attach --check` and `--json` no longer report `added_hooks`, and `--yes` now
confirms added allow rules alone. A repository whose `memory.mode` is not `overlay` is attached
too, with no note links; and since Claude Code writes the plugin's entry into
`.claude/settings.local.json`, a `.claude` linked in from elsewhere is now refused on every run.
