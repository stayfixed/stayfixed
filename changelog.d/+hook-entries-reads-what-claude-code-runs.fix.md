`stayfixed doctor`'s `hook-entries` row now judges the hook entries in a settings file that opens
with a UTF-8 byte-order mark, or whose `hooks` section holds, beside valid entries, a value that is
not a list where an event's list goes, a group that is not an object, a group whose `hooks` is not
a list, or an entry that is not an object. Claude Code 2.1.288 was measured (macOS, 2026-10-05)
running the valid hooks of each such file, so a stayfixed-marked entry there that nothing records
or grants is red, as anywhere else. The row used to read each of these files as one it could not
read, a warning, so a repository could commit one stray value beside a forged entry and keep the
report at exit `0`. This reverses the earlier reading of a byte-order mark, decided before the
measurement, as a file Claude Code could not load. A file that is not valid JSON, and one whose
misplaced value is an object or a list that could hold a command, are still reported as files the
row could not read.
