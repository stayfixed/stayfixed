`[stayfixed] state` is removed, and `[stayfixed] enforced` is the one adoption key: a gate enforces
when that list names it, and nothing else says so. A `stayfixed.toml` that still has a `state` line
no longer loads (`[stayfixed] has unknown key(s): state`), so delete the line and list in
`enforced` each gate that enforces. Where it said `state = "installed"`, which meant every gate,
list every gate the project runs, as `enforced = ["docs", "bugs", "plan", "commit", "trail"]` for
the built-ins, with your custom gates beside them; a gate added later is advisory until you list
it, which `stayfixed gate` admits in the pull request that adds it. Where it said `initialised` or
`adopting`, keep the list as it is, or leave it out when it was empty. A base branch whose copy
still has the old line fails `stayfixed gate` on every pull request, since that copy governs the
run, so push the new spelling to the base branch directly. `stayfixed adopt promote` writes
`enforced` alone. The JSON fields `state` (in `stayfixed assess --json` and
`.stayfixed/assessment.json`, now format `2`), `config.base_state` (in `stayfixed gate --json`) and
`before` and `after` (in `stayfixed adopt promote --json`) are gone, and the summary lines of
`assess` and `adopt promote` no longer name a state.
