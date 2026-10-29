`stayfixed assess` counts a `CODEOWNERS` line as covering `.github` only when, split on spaces and
tabs, its first field holds `.github` and another field follows. A line that joins the pattern to
its owner with a no-break space in place of the space, which GitHub reads as one pattern with no
owner, and a line that is `/.github/` alone now report `codeowners` where before they silenced it.
The probe still reads neither GitHub's owner syntax nor inline comments nor which line matches
last. The reusable workflow's reference now says to require `check / gates` only on the branches
the caller gates: a pull request green on the gate branch and retargeted to another branch keeps
that check, judged against the gate branch's configuration, and a pull request opened into
another branch that requires the check cannot join that branch's merge queue while no run reports
it. The header comment of the workflow `stayfixed init` writes is corrected to match, so
`stayfixed upgrade` refreshes `.github/workflows/stayfixed.yml` where you have not edited it.
