The note after a failing test run now comes from the profile of the stack whose runner failed, so
a repository in several languages gets the right advice with no configuration. Python's note
(stale bytecode, a dirty tree) reads as before. `stayfixed test hygiene` now reports per profile:
its summary names each finding as `<profile>: <note>` (for example `python: 2 .pyc file(s) whose
recorded source mtime no longer matches their source, …`), and a clean tree reads `tree is clean;
the python profile has nothing to report`. In `--json`, the top-level `stale` and `roots` keys are
gone; the counts sit under `profiles`, by profile name (`{"dirty": 0, "profiles": {"python":
{"stale": 0, "roots": 2}}}`). A profile is listed when its markers sit at the repository root,
or wherever it has something to report.
