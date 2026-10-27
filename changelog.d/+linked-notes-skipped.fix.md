A note file that is a symbolic link is skipped in every memory store: it reaches no session and
`stayfixed memory inventory` counts it as `skipped`. A repository could commit such a link to put a
file from outside it into every session. A group directory that is a link is still followed.
