---
id: BR-003
title: Renumbering BR-009 must carry this reference along
status: partial
severity: high
area: ledger
found: 2026-09-03
source:
fixed_in:
related: [BR-009]
---

- **Found:** 2026-09-03
- **Where:** `src/write.py`, the sweep

This entry names BR-009 in its title, its `related` list and here, so a move of BR-009 rewrites
all three.

**Suggested fix:** sweep every entry but the two the move writes.

**What this evidence does not establish:** whether a reference outside the ledger is swept the
same way.
