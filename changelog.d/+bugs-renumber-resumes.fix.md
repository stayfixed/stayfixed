`stayfixed bugs renumber OLD NEW` killed part-way is now finished by running the same command
again. Before, the re-run refused because `NEW` already had an entry file, and `stayfixed bugs
check` reported only a stale index, whose remedy (`stayfixed bugs index`) turned the check green
over two live entries for one bug or over mentions of `OLD` the move never rewrote. The re-run
recognises the move's own half-done state: `NEW` holding exactly `OLD`'s text with its `id:`
rewritten, or `OLD` the void pointer the move writes to `NEW`, byte for byte except for the rest
of a title that starts `renumbered to NEW — `. It makes the writes still missing and leaves the
tree an uninterrupted run would have, even when `NEW` was retitled in between. Any other entry
already at `NEW` is still refused, and the refusal says how to finish by hand a move whose `NEW`
was edited after it was interrupted. A re-run of a move that finished changes nothing and says
so, leaving any mention of `OLD` written since as it was. `stayfixed bugs check` now names that
re-run, `stayfixed bugs renumber OLD NEW`, rather than `stayfixed bugs index`, when the stale
index is the one an interrupted move left, including after the move had already rewritten another
entry's title: a void pointer an earlier move left toward `OLD`, or a title that names `OLD`. A
write of the move's own that fails, such as an index in a directory that cannot be written, ends
the command with exit `1`, naming the file and that re-run, where it was an internal error with
exit `2`. `stayfixed bugs renumber X X` is refused outright.
