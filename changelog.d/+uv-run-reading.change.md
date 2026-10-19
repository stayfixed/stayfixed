The note after a failed test run reads `uv run` without a list of uv's options: the command starts
at the first word a runner adapter recognises, so an option uv adds needs no new stayfixed, and a
runner named as an option's value before the real command (`uv run --with pytest echo`) is read as
the command. The `bg-cleanup` hints no longer read through `uv run`, so a backgrounded
`uv run sleep 30` gets no hint.
