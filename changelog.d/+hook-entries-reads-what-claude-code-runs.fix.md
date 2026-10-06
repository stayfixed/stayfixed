`stayfixed doctor`'s `hook-entries` row now judges the hook entries in a settings file that opens
with a UTF-8 byte-order mark, or whose `hooks` section holds, beside valid entries, a value that is
not a list where an event's list goes, a group that is not an object, a group whose `hooks` is not
a list, or an entry that is not an object. Claude Code 2.1.288 was measured (macOS, 2026-10-05)
running the valid hooks of each such file, so a stayfixed-marked entry there that nothing records
or grants is red, as anywhere else. The row used to read each of these files as one it could not
read, a warning, so a repository could commit one stray value beside a forged entry and keep the
report at exit `0`. A file that is not valid JSON is still reported as one the row could not
read. So is one whose misplaced value is an object or a list
that could hold a command, but the entries beside that value are now judged too, so such a file
can turn the row red where it used to warn. Codex's `.codex/hooks.json`, which nobody measured, is
read as strictly as before, and `stayfixed assess`'s `foreign-hooks` item now reads Claude Code's
settings files the way `doctor` does.
A command claiming the stayfixed marker inside such an object or list, or in an entry object
written where a group goes, is now red rather than a warning; that is a conservative reading, since
whether Claude Code runs it was not measured. And an entry is named by its place among every
element of its list, so one beside skipped values is named where you find it.
