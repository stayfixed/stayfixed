`stayfixed attach` no longer prints or records the credentials an `origin` URL can carry: the
userinfo of `https://user:token@host/…` is taken out before the origin is shown on the attach
screen or in the note naming both remotes, and before it is written into this machine's binding
record or the overlay's `projects/<name>/project.toml`. An ssh URL keeps its user and loses only a
password.
