`stayfixed plan check` and the `plan` gate now read a plan's declaring lines (`- Create:`, `- Test:`,
`- Delete:`) and its premise marker in time linear in the plan's length, with the same findings.
A run of blank lines was read again from every one of them, 16,000 in a third of a second, and a
run of `**Premise` markers with no colon after them from every marker, 16,000 in half a second;
each doubling took four times as long, over a plan any change can commit.
