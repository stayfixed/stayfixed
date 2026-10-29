The reusable workflow `check.yml` no longer resolves the base and the project root in a shell
step of its own: each of its two gate steps hands `stayfixed gate` the platform's values as they
are, and `stayfixed gate` checks them itself, through four new flags, `--pr-base`, `--base-input`,
`--default-branch` and `--path`. A caller's `with:` lines do not change. A `path:` may now hold a
space or a name outside ASCII, which the old step refused; a `path:` with a `..` component, or an
absolute one, is still refused. A refused `base:` or `path:`, or a base with no name, now fails
the step with exit code 2 where the shell step exited 1, and the step that fails is the gate step
rather than the one named "The base ref and the project root", which is gone. Run locally,
`stayfixed gate --pr-base=BRANCH --base-input=BRANCH --default-branch=BRANCH` reproduces CI's
choice of base: the three are passed together or not at all, and never beside `--base`.
