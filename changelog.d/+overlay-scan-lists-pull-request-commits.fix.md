The `scan` workflow in a new overlay now grants `pull-requests: read` beside `contents: read`. On a
pull request the gitleaks action lists the pull request's commits through
`GET /repos/{owner}/{repo}/pulls/{n}/commits` to find what to scan, and GitHub documents that
endpoint as needing the "Pull requests: read" permission on a private repository, which an overlay
is; with `contents: read` alone the token has no such scope, so the scan of a pull request in an
overlay created from an earlier template was likely to fail for want of it (stayfixed did not
observe that failure). `stayfixed overlay upgrade` adds the line to an untouched `scan.yml`; in a
file you or Dependabot have edited, add `pull-requests: read` under `permissions:` yourself.
