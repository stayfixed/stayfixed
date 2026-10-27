`stayfixed trust` lists and withdraws the approvals recorded on the machine, in
`~/.config/stayfixed/trust.json`, now a versioned record of each approval with its kind, its
subject, the digest approved and when; the one kind this release records is `reviewed`, from
`stayfixed memory promote`. `stayfixed trust list` lists every approval, each subject named escaped
and bounded, and from `~/` under the home. `stayfixed trust revoke KIND --subject KEY` withdraws
that approval and every other of its kind holding the same digest, from any directory, with no
terminal, and exits 1 listing what the kind has recorded when nothing matches. A record no release
writes, or one a later version wrote, is refused and never overwritten; for a later version's, the
refusal says to update stayfixed rather than delete the file.
