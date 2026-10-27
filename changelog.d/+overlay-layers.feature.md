A session reads two more layers of preferences, between the repository's `stayfixed.toml` and the
machine file: the overlay's `common/stayfixed.toml`, for every checkout, and
`projects/<name>/stayfixed.toml`, for a checkout this machine binds to `<name>` with `stayfixed
attach`. Each may set a personal value, a guard switch, `[memory] mode`, `groups` and
`index_extra`, `[stayfixed] profile` and a session budget; the project file wins over the common
one and the machine file over both, and a gate's input or a fact about the repository written
there is never taken from it. `stayfixed attach`, `attach --check`, `detach` and the `memory`
commands read the same two layers, so an overlay that sets `[memory] mode = "overlay"` gets its
store built by the next `attach`. `stayfixed doctor`'s new `preferences` row names every value a
session resolves, the session budgets among them, with the layer it came from.
