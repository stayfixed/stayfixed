`stayfixed attach` delivers the hooks, skills and agents you keep in your overlay as a local plugin.
Every run renders them into `~/.local/share/stayfixed/delivery/<id>/`, a marketplace and a plugin
named by the checkout's binding id, and installs it with `claude plugin marketplace add … --scope
local` and `claude plugin install … --scope local`, run from the main checkout so every worktree
gets it; a call that does not succeed fails the attach (exit 1), and the next `attach` installs
again; a session runs the plugin from that directory, so an edit in the overlay reaches the next
session after the next `attach`, with no reinstall; each render is the overlay as it is, written
whole and swapped into place; a copied file keeps its mode, so a skill's script stays executable.
Run from a worktree, `attach` also refuses when the main checkout tracks
`.claude/settings.local.json`, where the install writes, or its `.gitignore` re-includes it, and
from a worktree of a bare repository, which has no main checkout. No hook entry goes into
`.claude/settings.local.json` any more: it keeps only the allow rules `attach` merges, and the
entries an earlier release merged there are taken back, the ones its ledger records and no other.
`attach --check` and `--json` no longer report `added_hooks`. A repository whose `memory.mode` is
not `overlay` is attached too, with no note links; and since Claude Code writes the plugin's entry
into `.claude/settings.local.json`, a `.claude` linked in from elsewhere is now refused on every
run.
