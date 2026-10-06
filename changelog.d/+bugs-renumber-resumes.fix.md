`stayfixed bugs renumber OLD NEW` killed part-way is now finished by running the same command
again. Before, the re-run refused because `NEW` already had an entry file, and `stayfixed bugs
check` reported only a stale index, whose remedy (`stayfixed bugs index`) turned the check green
over two live entries for one bug or over mentions of `OLD` the move never rewrote. The re-run
recognises the move's own half-done state — `NEW` holding exactly `OLD`'s text with its `id:`
rewritten, or `OLD` already the pointer to `NEW` — makes the writes still missing, and leaves
the tree an uninterrupted run would have. Any other entry already at `NEW` is still refused. A
re-run of a move that finished now rewrites any mention of `OLD` written since, where it used to
refuse.
