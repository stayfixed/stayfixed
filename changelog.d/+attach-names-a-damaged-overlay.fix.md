`stayfixed attach` and `attach --check` now refuse an overlay whose root, or whose `projects/`,
is a file rather than a directory, or a symbolic link that names nothing, as a damaged overlay: the refusal names that path and asks for
the overlay to be repaired. Both used to blame the project's `[project] name` and tell you to
choose another one, even for a project the overlay had bound. `stayfixed doctor`'s `attached` row
names the same path and says to repair the overlay, where it said the overlay had no binding for
the project and offered to remove the ledger; it is still a warning, and the rest of the report
reads as before.
