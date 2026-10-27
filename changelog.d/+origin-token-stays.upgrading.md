`stayfixed attach` now takes the credentials out of an `origin` URL before it records it, but it
never rewrites the remote an overlay's `projects/<name>/project.toml` already records. A token
0.3.1 recorded there from an `https://user:token@host/…` origin stays in that file, and in the
overlay's git history, until you remove it: edit the file by hand, and revoke the token if the
overlay was ever pushed.
