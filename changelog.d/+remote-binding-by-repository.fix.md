A repository bound to the overlay over ssh now binds a clone of it made over https, and the other
way round: `git@host:owner/repo`, `ssh://git@host/owner/repo` and `https://host/owner/repo`, each
with or without `.git`, are one remote when the host and the path agree (the host in any case,
and on github.com the path too). A second machine or a teammate who cloned over https used to be
refused as a different remote and told to pass `--trust-remote`, which then rewrote the record to
that form. `attach`, `attach --check`, `doctor`, the memory commands and the session-start line all
apply the rule, and the record keeps the form it was written in. A different owner, repository,
host, port or user is still a different remote.
