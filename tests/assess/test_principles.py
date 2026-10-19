"""Every principle a gate or a probe cites, pinned to the heading it names."""

from __future__ import annotations

from stayfixed.assess.gates import BUILTIN
from stayfixed.assess.probes import PROBES
from tests.test_documents import principle_sections


def test_each_gate_cites_the_principle_it_means() -> None:
    # A number alone would survive the principles being renumbered or retitled under it; the
    # title is what the citation means. `docs` checks budgets and links, which is no principle's
    # own rule, and neither is `commit`'s or `trail`'s. Mutations (advisory): `docs` citing 4,
    # and retitling heading 1 with every number left alone — each reddens.
    titles = {int(number): title for number, title, _body in principle_sections()}
    cited = {gate.name: titles[gate.principle] for gate in BUILTIN if gate.principle is not None}
    assert cited == {
        "bugs": "A bug is a file, and its index is a rendering",
        "plan": "An assertion nobody has watched fail advertises coverage it may not have",
    }


def test_each_probe_cites_the_principle_it_means() -> None:
    # The same pinning for the probes. `tracked-env`, `foreign-workflows` and `commit-types`
    # cite none: a committed secret, another workflow and a subject's type are no principle's
    # own rule. Mutations (advisory): `Probe("todo-markers", 99, ...)` -> a `KeyError`; citing 2
    # instead -> the title differs; each reddens.
    titles = {int(number): title for number, title, _body in principle_sections()}
    cited = {probe.id: titles[probe.principle] for probe in PROBES if probe.principle is not None}
    assert cited == {
        "todo-markers": "A bug is a file, and its index is a rendering",
        "memory-history": "A personal overlay is a versioned plugin, not a dotfiles sync",
        "foreign-hooks": "A repository is untrusted input",
        "codeowners": "Enforcement is earned, not declared",
    }
