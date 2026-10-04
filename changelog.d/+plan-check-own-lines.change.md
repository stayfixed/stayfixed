`stayfixed plan check`, run without naming a plan, and the `plan` gate now check a backticked path
only on the lines the change adds or rewrites. A delivered plan is a record, and the files it
names move on; before, a pull request that edited one line of an old plan — an `Interfaces:`
block, say — failed on every path in it that no longer exists, and the only way through was to
rewrite the plan's history. A new plan is still checked in full, and naming a plan
(`stayfixed plan check PATH`) still checks every reference in it.
