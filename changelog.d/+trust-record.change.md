The machine's trust record, `~/.config/stayfixed/trust.json`, is now a versioned record of every
approval you gave, each with its kind, its subject, the digest approved and when, where it used to
be a flat map of note stores to digests. Your existing approvals are kept: the old file reads as
approvals of committed notes, and the first write after the upgrade rewrites it in the new
shape. A `0.3.x` stayfixed reading the new file finds no approval in it and asks you again rather
than trusting anything it cannot read; approving there rewrites the file in the old shape with
that one approval, so the others are asked for again after you return to this version. A record
that is neither shape — one whose `version` no release writes, or one holding approvals with no
`version`, included — or one a later version wrote, is refused and never overwritten; for a later
version's, the refusal says to update stayfixed rather than delete the file, whose approvals that
release still holds.
