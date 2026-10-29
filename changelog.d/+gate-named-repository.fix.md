With the platform's base (`--pr-base`, `--base-input` and `--default-branch`, the form the reusable
workflow `check.yml` uses), a project in a subdirectory is always read as that subdirectory of the
checkout `stayfixed gate` was given: every `git` the run asks names the checkout's own repository
instead of finding one from the project's directory, and a `--path` through a symbolic link is
refused wherever the link leads.
