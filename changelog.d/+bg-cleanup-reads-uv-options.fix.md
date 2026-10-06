The background guard now reads a command started through `uv run` with uv's own options, as the
note after a failing test run does: a backgrounded command that begins with `uv run <options>
sleep`, such as `uv run --no-project sleep 30`, is refused as a backgrounded `sleep` is, where
before it was allowed, while `uv run -m sleep` and `uv run --script sleep`, which run a module or
a file of that name, are not. Its advice about a backgrounded chain ending in `; echo` reads the
same way: it sees an echo uv launches past its options and no longer takes one for the command the
echo hides, so `pytest -q; uv run --no-project echo done` now gets it (`stayfixed guard
bg-cleanup` exits `1`) and `uv run --frozen echo hi; echo done` no longer does (exit `0`).
