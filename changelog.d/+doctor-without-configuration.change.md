`stayfixed doctor` no longer calls a repository with no `stayfixed.toml` broken. It used to answer
one red row, "the plugin's hooks are silent in this repository", and skip everything else; the
`not-initialised` row is now a warning that the session guards and `doctor` work without one and
that `stayfixed init` adds the rest, every other row is still checked, and the rows that need the
project's configuration say there is none. `doctor` reads `stayfixed.toml` the way a session does,
so a file a newer stayfixed wrote is a warning naming the first few of the settings that were
ignored or put back to the preset's, by key, and counting the rest, and only a file the session
cannot use at all is red. A machine file that does not load no longer hides the report: the new
`preferences` row is red, naming it, as every command refuses it, and the rows that read the overlay
root say they could not read it rather than that none is recorded; one that loads with keys this
stayfixed cannot use is a warning naming them. That row, after `budgets`, names the layer each
preference and each of the machine owner's settings came from (the preset, the repository or the
machine file), with its value only where it is a boolean, a number or one of stayfixed's own words.
