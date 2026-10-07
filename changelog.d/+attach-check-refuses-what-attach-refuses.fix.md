`stayfixed attach --check` now refuses, with exit `2` and the words `attach` uses, every
`.claude/settings.local.json` that `attach` itself refuses. Before, `--check` read the file's
allow list and hook table with filters of its own, reported a clean diff and exited `0`, and
`attach --yes` then refused the same file. These shapes were the difference:

- `"permissions": null`, or `"allow": null` inside it;
- an event under `hooks` whose value is `null` or is not a list;
- an entry group that is not an object, or whose `hooks` is `null` or is not a list;
- an entry that is not an object.

`null` is now read the same way wherever `attach` reads a settings document: as a value that is
not the object or list that goes there, and never as an absent key. So your overlay's own grant
files are refused by both commands too, where both read them as granting nothing:

- a `permissions.json` under `common/claude/` or a project's `claude/` whose `"permissions"` or
  `"allow"` is `null`;
- a `hooks.json` there with an entry group whose `hooks` is `null`.

For a repository already attached under an overlay whose `hooks.json` holds such a group,
`stayfixed doctor`'s `hook-entries` row now warns that the overlay could not be asked which entries
it grants, where it judged the entries against the rest of the file. Remove the `null` key, or give
it `{}` or `[]`, and `stayfixed attach --check` names the clause until you do.

`--check` also reads an existing `.stayfixed/local/attach.json` the way the run does, so a ledger
the run cannot take ends both with one code and one line: one that is not valid JSON, past the
64 MiB read cap or otherwise unreadable fails (exit `1`), and one naming what `attach` never writes,
or one that is itself a link, is refused (exit `2`). `--check` used to leave the ledger unread and
exit `0` over it.

A refusal that names an event prints it escaped when it holds a line break or a control
character, as other names a repository chose already print.
