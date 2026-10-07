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

`--check` also asks everything else the run asks before its first write, through the run's own
code, so wherever the run fails or refuses there, `--check` ends with the same code and the same
line, where it used to leave the file unread, report a clean diff and exit `0`:

- an existing `.stayfixed/local/attach.json` that is not valid JSON, past the 64 MiB read cap or
  otherwise unreadable fails (exit `1`), and one naming what `attach` never writes, or one that is
  itself a link, is refused (exit `2`);
- an overlay Codex rule file that is not UTF-8 fails (exit `1`);
- a `~/.claude` that is a symlink, as a dotfiles manager leaves it, a `trust.json` that does not
  parse, an `origin` URL that is not UTF-8, a `.gitignore` that is not UTF-8 or holds the
  `stayfixed:ignore` region twice, an exclude file that holds the `stayfixed:attach` block twice or
  sits in a `.git/info` you cannot write, and a `.claude` linked in from elsewhere when the overlay
  grants something to merge into it, are refused (exit `2`).

A `memory.groups` entry that leaves this project's share of the overlay, which `--check` refused
in other words, is refused in the run's. Where the run refuses before the rest, at a checkout with
no `origin` or a memory group that never moved, `--check` still reports it and exits `1`, and asks
nothing after it.

A refusal that names an event prints it escaped when it holds a line break or a control
character, as other names a repository chose already print.
