The note after a failing test run now comes from the profile of the stack whose runner failed, so
a repository in several languages gets the right advice with no configuration. Python's note
(stale bytecode, a dirty tree) reads as before; `stayfixed test hygiene --json` lists its counts
per profile.
