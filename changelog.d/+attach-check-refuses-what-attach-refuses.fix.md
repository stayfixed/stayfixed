`stayfixed attach --check` now refuses, with exit `2` and the words `attach` uses, every
`.claude/settings.local.json` that `attach` itself refuses. Before, `--check` read the file's
allow list and hook table with filters of its own, reported a clean diff and exited `0`, and
`attach --yes` then refused the same file. These shapes were the difference:

- `"permissions": null`, or `"allow": null` inside it;
- an event under `hooks` whose value is `null` or is not a list;
- an entry group that is not an object, or whose `hooks` is `null` or is not a list;
- an entry that is not an object.

`null` is now read the same way wherever `attach` reads a settings document: as a value that is
not the object or list that goes there, and never as an absent key. So the overlay's own
`common/claude/hooks.json` or a project's `hooks.json` with an entry group whose `hooks` is `null`
is refused by both commands too, where both read it as granting nothing. A refusal that names an
event prints it escaped when it holds a line break or a control character, as other names a
repository chose already print.
