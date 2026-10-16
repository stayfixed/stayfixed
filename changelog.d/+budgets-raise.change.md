A budget is now the value you set, above the preset or below it. A `[budgets]` value above the
preset's used to be ignored, so the number in `stayfixed.toml` was silently not the one in force;
now the base branch's `stayfixed.toml` may raise any budget and the machine file a session's
budget, and `stayfixed doctor`'s `budgets` row names each one raised or lowered. A pull request
still only lowers a gate's budget: `stayfixed gate` refuses a raise against the base branch's
value. `stayfixed gate` now judges a key by what it is: a pull request may change a preference
such as `[memory] mode` or a session's budget whatever the base enforces, since no gate reads
them, and may add to `[ledger] code_roots` and `evidence_boundary_required_for`, while removing an
entry from either is refused while a gate enforces.
