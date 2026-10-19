`stayfixed assess`'s `codeowners` probe no longer reimplements GitHub's CODEOWNERS pattern matching.
It is now advice, not a warning, given when there is no CODEOWNERS file or when no line outside a
comment holds `.github`, so a file whose only rule is `* @owner` gets the advice too. The `codeowners-scope` probe, which matched
every workflow against the file under a step budget, is gone.
