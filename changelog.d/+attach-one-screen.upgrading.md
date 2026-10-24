`stayfixed attach` takes no `--yes`: what your overlay grants is yours, so `attach` no longer
refuses a run that adds allow rules. It proceeds and prints one screen below its line: the binding
(the binding id's first eight characters, the project it is recorded under and this checkout's
`origin`, with one more line when a re-attach moves the binding to another project), each hook
entry, skill and agent the render adds or removes against the last one, and each allow rule it
merges; `--json` carries the same lists as `hooks_added`, `hooks_removed`, `skills_added`,
`skills_removed`, `agents_added`, `agents_removed` and `allow_added`. A script or skill that passed
`attach --yes` now gets exit 2 for an unrecognised argument and must drop the flag. `attach --check
--json` no longer carries `widens`.
