---
name: house-style
description: "A standing rule, so the injection rows carry repository bytes instead of nothing"
metadata:
  type: project
  startup: -1
---

SMOKE-STANDING-RULE: this sentence is the fixture's standing rule. `scripts/smoke_hooks.py`
asserts it arrives inside a delimited region, which is what the six `memory session-context`
entries are for. Without a store the same rows exit 0 having emitted nothing at all.
