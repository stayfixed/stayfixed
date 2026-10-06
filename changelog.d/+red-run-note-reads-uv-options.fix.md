The note after a failing test run now reaches a run started through `uv run` with uv's own
options, such as `uv run --locked pytest`, the command the README and the `attribute-failure`
skill suggest, and `uv --quiet run pytest` or `uv run -- pytest`. Before, only the bare `uv run
pytest` was read through, so a failing `uv sync --locked && uv run --locked pytest …` got no note
at all, not even the line about uncommitted changes. uv's options are read by uv's own list of
them, and a `uv` command carrying an option outside that list still gets no note, so a value such
as the package in `uv run --with pytest echo` is never taken for the program.
