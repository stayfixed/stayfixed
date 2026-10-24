`stayfixed memory index` no longer writes into notes. A note with no `index:` line is rendered with
its `metadata.index` or its description on every run, so an edit to either reaches the index, and a
provisional line an earlier release wrote into a note is read as no line. The one line still written
into a note is the one the harness's memory writer appended to `MEMORY.md`, harvested so it is not
lost. The render now sits between two marker lines in `MEMORY.md`, and only lines outside them are
harvested, so the render's own lines are never read back into a note: a second run, after an edit
or not, leaves every note and its reviewed status as it was. The command's line no longer names
notes it gave a provisional line; `--json`'s `provisional` still lists the notes whose line is
rendered that way.
