The Claude Code plugin now comes from `stayfixed/stayfixed-plugin` (Changed, "The Claude Code
plugin is now installed from `stayfixed/stayfixed-plugin`"). How an existing install moves to this
release depends on how its marketplace was added:

  - Added without a tag (`/plugin marketplace add stayfixed/stayfixed`), it follows the
    repository's default branch and moves with an update:
    `claude plugin marketplace update stayfixed-marketplace`, then
    `claude plugin update stayfixed@stayfixed-marketplace`.
  - Added at a release tag (`stayfixed/stayfixed@v0.2.0`, say), adding it again at this
    release's tag over the marketplace you have is refused. Remove the marketplace, add it at
    this release's tag, `stayfixed/stayfixed@vX.Y.Z` as the README's Install section names it,
    and install the plugin again: `claude plugin marketplace remove stayfixed-marketplace`, then
    `claude plugin marketplace add stayfixed/stayfixed@vX.Y.Z`, then
    `claude plugin install stayfixed@stayfixed-marketplace`. Removing the marketplace uninstalls
    the plugin and deletes the options you saved for it, so set them again after the install.
