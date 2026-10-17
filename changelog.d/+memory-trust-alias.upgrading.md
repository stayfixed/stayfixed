`stayfixed memory trust --in-repo-memory` is now the old spelling of `stayfixed trust approve
memory`, and it needs a terminal too: a script or an agent that ran it with no terminal on standard
input now gets exit 2 and nothing approved. Run `stayfixed trust approve memory` yourself, in a
terminal. The old spelling says so after it runs and is removed in 0.5.0. Its `--json` carries the
new command's keys, `kind` and `approved`, and keeps its old ones beside them with their old
meanings until then: `was_trusted`, `trusted` and `digest`.
