---
name: attach
description: Bind a repository to its private memory overlay and link the note store in, or detach it. Use when a session reports "not attached", a memory path is a real directory, or the user asks to attach or detach the overlay.
---

# Attaching the overlay

`PATH` below is always `<overlay>/projects/<project name>/memory`, where the name is the
`[project] name` in this repository's `stayfixed.toml`. Any other path is refused: the overlay
root comes from the machine configuration, not from what is typed here.

1. Run `stayfixed attach --store PATH --check` first. It reports whether this machine already
   binds this checkout (`bound` or `unbound`), and which allow rules would be added. It
   writes nothing. If the report counts memory groups that are real directories, stop: the
   notes have to move into the overlay first — each group to
   `<overlay>/projects/<name>/memory/<group>`, the shared group to `common/memory`. Say the
   count and wait; moving notes is the owner's act, never yours.
2. Relay that diff to the user and wait for an answer. The command itself refuses to widen a
   permission without `--yes`, so this step is how a person comes to give it — not what stands
   in for it. Once they agree, run `stayfixed attach --store PATH --yes`; it merges the rules,
   installs the overlay's hooks, skills and agents as this checkout's local plugin, links the
   notes into this checkout and every worktree, and prints what it wrote. An overlay
   that grants nothing attaches without the flag, and that is the command's decision rather
   than a judgement to make here.
3. If the report or the run names two remotes -- this checkout's `origin` is not the one the
   binding or the overlay records -- relay that line. It refuses nothing: the binding is an id
   this machine keeps, never the remote. Never print or relay more of the binding id than the
   eight characters the command prints.
4. `stayfixed detach` removes the merged rules, the Codex rule files, the note links and the
   local ledger, and leaves the overlay's project record untouched. Relay what it removed.
5. Personal rules, notes and permissions live in the overlay and nowhere else. Never copy one
   into the project repository, and never widen a permission on the user's behalf.
