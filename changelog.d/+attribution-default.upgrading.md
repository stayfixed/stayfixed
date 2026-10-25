The commit attribution check is now off by default: `[commit_messages] attribution_check` is
`false` in the recommended preset, so the `commit` gate and `stayfixed commit check` no longer fail
a commit message that ends in an AI tool's attribution trailer or footer unless the project asks
them to. A project that relied on the check sets `attribution_check = true` under
`[commit_messages]` in its `stayfixed.toml`.
