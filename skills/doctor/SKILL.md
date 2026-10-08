---
name: doctor
description: Diagnose a stayfixed installation — hooks, memory store, budgets, overrides and trust. Use when a hook is silent, memory does not arrive, a gate fails unexpectedly, or the user asks whether stayfixed is set up correctly.
---

# Diagnosing an installation

1. Run `stayfixed doctor --json` and read the report: seventeen checks, each with a status, a
   detail and a remedy. Between them they answer whether the repository is initialised, whether
   the hook wrapper can reach stayfixed at all, whether this checkout is attached and what shape
   its memory path has, every hook entry with its provenance, each budget the preset clamps, a
   bundle that does not fit its slots, the last reasons a hook failed, an environment variable
   that is set and ignored, and whether a hook can make the harness memory link.
2. Relay each finding with the remedy the report names, verbatim. Do not change settings or
   hook entries on the user's behalf — name the command that would.
3. A `skip` is not a fault, and it is not always harmless either. One check cannot be
   answered by this build at all — whether a hook is trusted on Codex. Nine more skip on a
   state of the machine or of the repository: `wrapper` and `files`
   when no plugin root can be vouched for, `files` again on a build with no release record,
   `attached` when no overlay is recorded or the overlay cannot be asked, `pre-commit` with no
   overlay root recorded, `overlay-requires` with no overlay root recorded or no requirement
   declared — and those last two also skip when the overlay root this machine records is not a
   directory any more, which is the one overlay skip that carries a remedy (put the overlay
   back, or record where it is now), because the note store is broken with it — `bundles` and `store-debris` when the note store does not resolve,
   `diagnostics` with no harness data root set, and `ci-ref` when the repository records no
   `[ci] ref` — which `stayfixed init` writes once a released stayfixed exists to pin, so that
   row's skip says "nothing recorded here", not "this build cannot answer". Each says which
   kind it is in its own detail. Report the one as "nothing to answer here"; report the nine as
   the state they name, and relay the remedy where the row carries one.
4. **`files` and `wrapper` skipping together is the report's loudest finding, and it is not
   red.** It means this process could not find the plugin — so no hook entry reaches stayfixed
   on this machine, and nothing else in the report can say so. Lead with it, and relay the
   remedy both rows carry.
5. When `not-initialised` is red, every other row skips against it. Relay the red row and stop;
   the fifteen skips below it are not fifteen problems.
