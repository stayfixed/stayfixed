`stayfixed bugs new` no longer fetches from the remotes of a project's submodules. The
`git fetch` it runs before allocating an identifier now passes `--no-recurse-submodules`: it needs
only the project's own refs, and under git's default `fetch.recurseSubmodules=on-demand` it also
asked the remote of each checked-out submodule whose recorded commit the fetch brought in, so a
submodule remote that could not be reached failed the fetch and printed a warning that
identifiers might collide.
