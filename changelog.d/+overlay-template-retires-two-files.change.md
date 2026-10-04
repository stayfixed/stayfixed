`stayfixed overlay upgrade` and `overlay init` remove two files the overlay template no longer
ships: its copy of the `attach` skill (the plugin's own, which also covers detaching and a moved
remote, is the one that stays) and `common/rules/README.md`, which nothing read. A copy you edited
is kept and named on every run, with the way out: delete it once you no longer need your edits,
and move any rules from the README into notes with `metadata.startup` first. `overlay init` no
longer stops at a retired file it cannot remove, which left the files it had already removed
still recorded in `.stayfixed/manifest.json`: it names that file with a `left` line, removes the
rest, and the next run finishes the job.
