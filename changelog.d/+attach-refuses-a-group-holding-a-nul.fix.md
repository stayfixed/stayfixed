`stayfixed attach` and `stayfixed attach --check` now refuse a `memory.groups` entry that holds a
NUL character, as they refuse one that leads out of the project's notes in the overlay, instead of
ending in an internal error. No path can hold that character, so the entry is refused before
anything is written, and it is never printed back.
