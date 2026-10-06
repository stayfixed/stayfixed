`stayfixed bugs renumber OLD NEW` killed part-way is now finished by running the same command
again. Before, the re-run refused because `NEW` already had an entry file, and `stayfixed bugs
check` reported only a stale index, whose remedy (`stayfixed bugs index`) turned the check green
over two live entries for one bug or over mentions of `OLD` the move never rewrote. The re-run
recognises the move's own half-done state — `NEW` holding exactly `OLD`'s text with its `id:`
rewritten, or `OLD` the void pointer the move writes to `NEW`, byte for byte but for the rest of
a title that starts `renumbered to NEW — ` — makes the writes still missing, and leaves the tree
an uninterrupted run would have, even when `NEW` was retitled in between. Any other entry already at
`NEW` is still refused, and the refusal says how to finish by hand a move whose `NEW` was edited
after it was interrupted. `stayfixed bugs renumber X X` is refused outright. A
re-run of a move that finished, while `OLD` is still the pointer the move left, now rewrites any
mention of `OLD` written since, where it used to refuse.
