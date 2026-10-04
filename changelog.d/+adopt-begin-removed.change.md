`stayfixed adopt begin` is gone. `stayfixed adopt promote` already moved a project from
`initialised` itself, so the minimal path is `stayfixed init`, then `stayfixed assess`, then
`stayfixed adopt promote` as each gate passes. A project `0.2.0` left in `adopting` keeps working.
