`stayfixed plan check` no longer reports the files a plan deletes as dead references once its
tasks have deleted them. A path the plan lists on a `- Delete:` line now counts as declared for
the whole plan, as a path on a `- Create:` or `- Test:` line already did, and a line marked
`(delete)` is exempt as one marked `(create)` is. Before, a finished plan that removed files
failed the check, and so did any later pull request that edited it.
