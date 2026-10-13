`stayfixed memory index` and `stayfixed detach` no longer end in an internal error on Python 3.11
and 3.12 where `MEMORY.md` or a group's link under `paths.memory` is a symlink loop, which a clone
can commit there. The index link is refused like any link that reaches no place in this project's
share of the overlay, and `detach` leaves the looping link standing, as it leaves any link that
points elsewhere.
