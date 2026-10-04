"""`doctor`: what an installation looks like from the outside.

This area **reports and never repairs.** Every other area in this package writes something;
this one reads.

**It runs several subprocesses, and every one of them only asks.** The count used to be given
here as "exactly two" and that was wrong: besides stayfixed's own hook wrapper with `--version`
and `git ls-remote --exit-code` over the public repository's tags, which is how `[ci] ref` is
judged, `pre-commit` asks
`guards.api.hooks_dir` where the overlay keeps its hooks, `attached` reaches `read_binding`,
which asks `git` for `origin`, and resolving the note store in overlay mode asks again — once for
`attached` and once for the store's own two rows, because each delivery area resolves the store for
its own rows.

**Five launches on the green end-to-end fixture, measured — and the sixth is the one that
leaves.** The five are the wrapper probe and four `git` questions;
`tests/test_install_path.py::test_doctor_launches_the_number_of_subprocesses_it_says_it_does`
counts them through a patched `Popen` and answers `ci-ref` through the `Runner` seam instead, so
the number it pins is the number a run makes *besides* that row. On a repository that records a
`[ci] ref` the real count is six. What is true of all of them is the part that matters: none
writes, and only one, the `ci-ref` row's `git ls-remote`, leaves this machine.

**Two of them read something the environment named, and neither trusts it.** `wrapper`
executes only the plugin root this process derived from its own module path, because a root a
variable named is a script a repository can choose (`checks.plugin_root`); `diagnostics` reads
the sink's log through `${CLAUDE_PLUGIN_DATA}` and prints a count and not one byte of it,
because nothing here can establish who wrote that file (`checks._diagnostics`).

A check that cannot be answered says `skip` and names what a measurement would need, because a
check that returned green because it could not look would be strictly worse than one that admits
it. **One is the floor and not the count**, and `doctor/commands.py` has the whole of it: one
check cannot be answered by this build at all — the Codex hook-trust hash — nine more rows skip
on a state of the machine or of the repository, and `run_checks` skips fifteen at once when
`stayfixed.toml` is missing or will not load. `ci-ref` was counted with the Codex hash and is not
any more: `init` writes `[ci] ref`, so "no ref recorded" is a state, and whether it is the
ordinary state depends on whether a release exists to pin rather than on anything here. One of
the nine is easy to meet by hand: `diagnostics` skips whenever no harness data root is set,
which is every `stayfixed doctor` run from a terminal rather than from a hook.
"""
