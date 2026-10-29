With the platform's base (`--pr-base`, `--base-input` and `--default-branch`, the form the reusable
workflow `check.yml` uses), a project in a subdirectory is always read as that subdirectory of the
checkout `stayfixed gate` was given: git is asked once at `--root` for its checkout's top, every
other `git` the run asks names that checkout's repository instead of finding one from the project's
directory, and the release tags are listed from the checkout's top. A `--path` through a symbolic
link to a directory is refused, out of the checkout as well as inside it; one to a file or to
nothing still fails.
