`stayfixed plan check`, the `plan` gate, `stayfixed docs check`'s links in the always-loaded
document and `stayfixed memory refs` now find a document's fenced code blocks in time linear in its
length, with the same blocks as before. They were found by a pattern that scanned the rest of the
document again from every line opening a fence no later line closes, and from a long run of
backticks at every length down to three: a document of 4,000 unclosed fences took a third of a
second, and each doubling of it four times as long.
