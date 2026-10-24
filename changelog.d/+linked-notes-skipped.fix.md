A note file that is a symbolic link is skipped in every memory store: it reaches no bundle, is never
counted as reviewed, and `stayfixed memory inventory` counts it as `skipped`. A repository could
commit such a link to put a file from outside it into every session, or to make a note you promoted
in another project a standing rule in its own. A group directory that is a link is still followed.
