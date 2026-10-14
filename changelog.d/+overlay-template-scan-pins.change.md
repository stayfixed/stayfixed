A newly created overlay's secret scan now starts from current releases: its `scan` workflow pins
`actions/checkout` v7.0.1 and `gitleaks/gitleaks-action` v3.0.0, both of which declare the Node 24
runtime, and its pre-commit hook pins gitleaks v8.30.1, at a full commit sha, where it pinned the
tag v8.21.2. The workflow now runs that same gitleaks v8.30.1 (`GITLEAKS_VERSION`) rather than the
8.24.3 the action defaults to, and its checkout no longer persists the token. The workflow fetches
the full history and scans what the action's range covers: on a push, from the first to the last
commit in the push's payload (just that commit, if it holds one); on a pull request, from the
first to the last of the first 30 commits the action lists for it; on a manual run, all of the
history. It needs no licence key for an overlay on a personal account. In an overlay you already
created, `stayfixed overlay upgrade` brings an untouched `.github/workflows/scan.yml` and
`.pre-commit-config.yaml` along; a file you or Dependabot have edited is left alone and named, and
the overlay's own Dependabot configuration keeps the workflow's action pins current either way;
`GITLEAKS_VERSION` and the hook's `rev:` it does not move, so they are bumped by hand, together.
