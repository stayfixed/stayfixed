`stayfixed memory index` and `stayfixed detach` no longer end in an internal error on Python 3.11
and 3.12 where they meet a symlink loop at or under `paths.memory`, which a clone can commit there.
A `paths.memory` that is itself a loop, in the checkout `detach` runs in or in the main checkout, is
refused before anything is withdrawn, the refusal saying whose `paths.memory` it is and that it is a
symlink loop. A `MEMORY.md` that loops is refused like any index link that reaches no place in this
project's share of the overlay, and a group's link that loops is left standing by `detach`, as it
leaves any link that points elsewhere.
