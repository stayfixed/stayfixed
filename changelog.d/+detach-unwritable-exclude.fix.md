`stayfixed detach` now refuses (exit `2`), before it withdraws anything, where this user cannot
write the directory that holds `.git/info/exclude`, naming the file as `stayfixed attach` does.
Before, it found out by writing the file, after the settings file, the `.codex/rules/` copies and
the link tree were withdrawn, and stopped there with the ledger and the exclude block still in
place.
