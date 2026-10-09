`stayfixed attach` and `attach --check` now refuse (exit `2`) an overlay whose root, or whose
`projects/`, is a file rather than a directory, or a symbolic link that names nothing, as a damaged
overlay: the refusal names that path and asks for the overlay to be repaired. Before, both failed
(exit `1`) on the operating system's error for a file inside it, such as `[Errno 20] Not a
directory` beside a path under `projects/` or `common/`, which did not say what was wrong.
`stayfixed doctor`'s `attached` row names the same path and says to repair the overlay, where it
said the overlay had no binding for the project and offered to remove the ledger; it is still a
warning. With `projects/` a file, `hook-entries` now judges the checkout's entries against what
`common/` grants every project, so an entry `common/` grants reads as accounted for, where the row
warned that the overlay could not be asked; with the overlay root a file, it still warns so.
