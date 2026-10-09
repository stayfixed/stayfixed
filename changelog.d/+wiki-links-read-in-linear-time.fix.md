`stayfixed memory refs` now reads a note's `[[links]]` in time linear in the note's length, and the
gap between two links in bounded memory, with the same notices. A run of `[` no link closes was read
again from every `[[` in it, 16,000 of them in half a second and four times as long at each
doubling, and a mebibyte of blanks between two links took 154 MiB more memory, over notes a
repository commits.
