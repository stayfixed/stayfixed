The reusable workflow `check.yml` no longer resolves the base and the project root in a shell
step of its own: each of its two gate steps hands `stayfixed gate` the platform's values as they
are, and `stayfixed gate` checks them itself, through four new flags, `--pr-base`, `--base-input`,
`--default-branch` and `--path`. A caller's `with:` lines do not change. A `path:` may now hold a
space or a name outside ASCII, which the old step refused. A `path:` with a `..` component is
still refused, and so now is an absolute one, such as `/sub` or `.//sub`, which the old step
admitted as a directory inside the checkout. A refused `base:` or `path:`, or a base with no name,
now fails the gate step itself with exit code 2 where the step named "The base ref and the project
root", which is gone, exited 1, and the reason is printed as a plain line on the step's error
output rather than as an `::error::` annotation on the pull request. Run locally,
`stayfixed gate --pr-base=BRANCH --base-input=BRANCH --default-branch=BRANCH` reproduces CI's
choice of base: the three are passed together or not at all, and never beside `--base`.
