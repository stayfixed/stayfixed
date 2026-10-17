`stayfixed setup --approval-boundary` prints what keeps an agent's shell out of the trust record
under Claude Code, for you to set, and writes nothing: the `permissions.deny` rule over the
record's directory, `sandbox.enabled = true`, and the managed settings that keep a repository from
turning the sandbox off. An approval holds against what a repository ships; against the session's
own agent the harness's sandbox is the boundary, which stayfixed does not check.
