`stayfixed init --local ID` in a repository that is already initialised is still refused, and the
refusal now says how to keep that file out of git instead: list its id under `[artifacts] local` in
`stayfixed.toml`, then run `stayfixed upgrade`. It used to point at `stayfixed upgrade` alone, which
has no `--local`.
