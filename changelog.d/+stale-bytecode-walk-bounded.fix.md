The Python profile's check for stale bytecode now stops after listing 500,000 directory entries
under `[ledger] code_roots`, or after reading 20,000 of the `.pyc` files it listed, and says it
could not tell rather than giving a count. The walk had no limit of its own: over a large enough
tree the note delivered after a failed `pytest` run outlasted the hook's 10-second timeout, so it
was never delivered and the same walk ran again after every later failed run. When the walk
stops early, that note says whether stale bytecode was imported could not be told, and
`stayfixed test hygiene` exits 2, saying the Python profile could not tell and the tree cannot be
judged, instead of naming a count or calling the tree clean.
