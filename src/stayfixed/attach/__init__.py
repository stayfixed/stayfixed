"""Bind a repository to the machine owner's private overlay, and unbind it again.

An area, discovered by name: `commands.py` gives it the `attach` and `detach` groups and
`api.py` is what another area may import. It writes nothing a repository chose — the overlay
root comes from the machine file, the store is that overlay's own directory for this project,
and a write that would widen a permission refuses without an explicit confirmation.
"""

# The command that binds this checkout to its share of the overlay, which every remedy of this area
# names, so a reader is never sent to two spellings of one command. `<overlay>` and `<project>` and
# never `config.project.name`: the name is repository-authored, and a remedy is as much output as a
# detail is. Here and not in `doctor.py` because `hooks.py` names it too, and discovery imports
# `hooks.py` unguarded for every hook: an edge to the report's module would let a defect there stop
# every hook, and load the report on each one. `projects` is `memory.api.PROJECTS`, spelled out
# because this package is loaded by that same discovery and must not import the memory area;
# `tests/attach/test_hooks.py` holds the two equal. Not annotated `Final`: an area's `__init__.py`
# imports nothing, `typing` included (`tests/test_surfaces.py`).
ATTACH_STORE = "stayfixed attach --store <overlay>/projects/<project>/memory"
