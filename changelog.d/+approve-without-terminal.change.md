`stayfixed trust approve` records the approval and prints the kind, subject and digest it recorded
from wherever it is run, and no longer refuses when standard input is not a terminal: an approval
holds against what a repository ships, not against an agent in the session, whose shell can write
the record anyway. `stayfixed memory trust --in-repo-memory` behaves the same. The README's table
of what each agent enforces now says what an attach delivers to Codex: the overlay's rules, through
`.codex/rules/`, and none of its hooks, skills or agents.
