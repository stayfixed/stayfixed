The note after a failing test run now comes from the profile of the stack whose runner failed, so
a repository in several languages gets the right advice with no configuration. After a failing
pytest run the note reads as before: stayfixed's own line about uncommitted changes, which comes
with any failing test run a profile recognises, then Python's line about stale bytecode.
A failing command the hook cannot split into words (an unbalanced quote, say) no longer gets
the note: before, any such command containing the word `pytest` did, and now that each stack's
profile recognises its own runner, guessing from a substring would put one stack's advice on
another stack's run.
`stayfixed test hygiene` now reports per profile: its summary names each finding as
`<profile>: <note>` (for example `python: 2 .pyc file(s) whose recorded source mtime no longer
matches their source, …`), and a clean tree reads `tree is clean; the python profile has nothing
to report`. In `--json`, the top-level `stale` and `roots` keys are gone; the counts sit under
`profiles`, by profile name (`{"dirty": 0, "profiles": {"python": {"stale": 0, "roots": 2}}}`). A
profile is listed when its markers sit at the repository root, and also, whether or not they do,
when it has something to report. `stayfixed test hygiene` refuses (exit 2), naming the profile,
when a shipped profile's hint cannot be loaded or answers in something other than text.
