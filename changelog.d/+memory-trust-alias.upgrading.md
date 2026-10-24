`stayfixed memory trust --in-repo-memory` is now the old spelling of `stayfixed trust approve
memory`; run that instead. The old spelling says so after it runs and is removed in 0.5.0. Its `--json` carries the
new command's keys, `kind` and `approved`, and keeps its old ones beside them with their old
meanings until then: `was_trusted`, `trusted` and `digest`.
