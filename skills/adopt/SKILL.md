---
name: adopt
description: Take a repository that has run init to its gates enforced — assess it, asking before any command of its own runs, brainstorm and write the adoption's design and plan, and hand over the promotion. Use right after init, in a later session that carries an adoption on, or in a clone of a repository that has adopted stayfixed.
---

# Adopting stayfixed

For a repository `init` has taken onto stayfixed, in this session or an earlier one, in this
checkout or a clone of it: no step below relies on what an earlier command printed.

1. Assess the repository, running none of its own commands first: run
   `stayfixed assess --builtin`, which runs the built-in gates and the probes and no custom
   gate. When its summary has a `not run, as --builtin asked` line, `stayfixed.toml`
   configures custom gates, and the assessment without the flag runs their commands. Name
   those gates to the user, say that the next command runs their commands on this machine,
   and ask for an explicit yes. **Silence, a timeout or an empty answer is a no.** On a yes,
   run `stayfixed assess`. On a no, keep the `--builtin` result. A no holds for the whole
   adoption: every later command that runs gates takes `--builtin` too. With no such line
   there is nothing to ask, and the `--builtin` result is the whole assessment.

   Either way, relay the summary: its table of gates, its table of items when there are any,
   and every `note:` line. The whole list is in `.stayfixed/assessment.json`. Use it for the
   next step, and never paste it wholesale.
2. Brainstorm the adoption with the user, through a brainstorming skill if the harness has
   one, otherwise one question at a time:
   - which gates the project runs: the built-in ones it keeps, and any command of its own
     added as a custom gate under `[gates]` in `stayfixed.toml`;
   - which gates to enforce first;
   - which findings to fix, and which to file as ledger entries through the `file-bug` skill;
   - what the project deliberately does differently.
3. Put the adoption in writing: the design in the `[paths] specs` directory as
   `<date>-stayfixed-adoption-design.md`, and the plan directly in `[paths] plans` as
   `<date>-stayfixed-adoption.md`; a second adoption, such as a subproject's, adds a slug:
   `<date>-stayfixed-adoption-<slug>.md`. No command requires the plan, and it is still the
   habit to keep: it is what the user and later sessions read to know which gate comes next.
   Give the plan the `**Scope:**` line `stayfixed plan check` requires, and a `**Premise:**`
   line if it claims to fix a ledger entry. Run `stayfixed plan check <plan>` until it passes.
4. Bring the roadmap's trail up to date, or the `trail` gate fails the next check. In the
   `trail.toml` beside the roadmap, under `[states]`, give both documents a state — the key is
   the listing's row, the last segment of `[paths] specs` or `plans`, a slash and the file name
   (`specs/<file>`, not `docs/specs/<file>`), the value one line such as `in progress`:
   unset, a new document is listed `delivered` before anything was built. Stage both documents
   (the listing reads only tracked files), run `stayfixed docs trail`, then
   `stayfixed docs trail --check`.
5. End with one message saying:
   - what was written, and what was skipped and why;
   - how many findings the plan covers;
   - to commit `stayfixed.toml`, `.stayfixed/manifest.json`, the scaffold, the design, the plan,
     `trail.toml` and the roadmap together, first: CI checks out only what git tracks, so the
     `docs` and `trail` gates are not enforced while a file they read is outside git;
   - the next command, once that commit is made, `stayfixed adopt promote`, which enforces every
     gate that passes now and names the rest; run it again as the plan lands. After a no in
     step 1 it is `stayfixed adopt promote --builtin`: without the flag it runs the commands the
     user declined. Say that it promotes no custom gate, and that promoting one means running
     its command, which needs the user's explicit yes first;
   - the undo: `stayfixed uninstall`.

What this skill does not do: write a gate or edit `stayfixed.toml`. A gate the brainstorm settles
on is the user's to add, and `stayfixed adopt promote` is what moves `state` and `enforced`.
