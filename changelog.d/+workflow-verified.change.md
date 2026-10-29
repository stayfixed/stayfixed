`stayfixed assess` splits a `CODEOWNERS` line as GitHub does before it counts `.github` as
owned: on ASCII spaces and tabs, with `.github` in the pattern and an owner after it. A line such
as `/.github/ @owner` with a no-break space before the owner, which GitHub reads as one pattern
with no owner, and a line that names `/.github/` with no owner, now report `codeowners` where
before they silenced it. The reusable workflow's reference now says to require `check / gates` on
the gate branch alone: a pull request green there and retargeted to another branch keeps that
check, judged against the gate branch's configuration, and a pull request opened into another
branch that requires it can never merge. The header comment of the workflow `stayfixed init`
writes says the same, so `stayfixed upgrade` refreshes `.github/workflows/stayfixed.yml` where
you have not edited it.
