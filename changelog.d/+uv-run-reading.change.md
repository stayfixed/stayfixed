The note after a failed test run reads `uv run` without a list of uv's options: the command starts
at the first word naming a test runner stayfixed recognises (`stayfixed prove`'s), so an option uv
adds needs no new stayfixed, and a runner named before the real command (`uv run --with pytest
echo`, `uv run grep -m pytest x`) is read as the command. The `bg-cleanup` guard no longer reads
through `uv run`: a backgrounded `uv run sleep 30`, which 0.3.1 refused, runs with no hint, and an
`echo` behind `uv run` is no longer read as an echo by the exit-echo hint.
