`stayfixed attach` and `stayfixed detach` now honour `--machine` wherever they run, as every other
command does, rather than refusing it outside an interactive shell: an agent passed that check
through a pseudo-terminal as easily as it passes the flag, so the refusal stopped no one.
