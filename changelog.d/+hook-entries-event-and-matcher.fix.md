`stayfixed doctor`'s `hook-entries` row now accounts for a stayfixed hook entry only where your
overlay grants it, and as your overlay grants it: under the same event, in a group with the same
matcher, and as the same entry, every field of it. It used to compare only the entry's marker id
and command, so a repository that copied a command your overlay grants, and committed a ledger
recording its id, read "all accounted for" when it put that command:

- under another event or matcher, such as `SessionStart` with matcher `*`;
- inside an entry that does something else with it: an entry of `type` `http`, which posts every
  event's input to a URL of the repository's choosing and ignores `command`, one of `type`
  `prompt`, `agent` or `mcp_tool`, or a `command` entry with an `args`, `shell`, `async` or other
  field your overlay does not grant.

Such an entry is now red, as one the overlay does not grant, and is named by its position in its
settings file as before. An entry `stayfixed attach` wrote is still accounted for whatever fields
your overlay's grant carries, a `timeout` or a `statusMessage` among them, because `attach` writes
the grant as it is; the order a file spells an entry's keys in does not matter.
