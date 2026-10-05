`stayfixed doctor`'s `hook-entries` row now accounts for a stayfixed hook entry only where your
overlay grants it: under the same event, in a group with the same matcher. It used to compare only
the entry's marker id and command, so a repository that copied a command your overlay grants under
another event or matcher, such as `SessionStart` with matcher `*`, and committed a ledger recording
its id, read "all accounted for". Such an entry is now red, as one the overlay does not grant, and
is named by its position in its settings file as before.
