The Claude Code plugin now comes from `stayfixed/stayfixed-plugin` (Changed, "The Claude Code
plugin is now installed from `stayfixed/stayfixed-plugin`"). To move an existing install to this
release:

  - If you added the marketplace without a tag (`/plugin marketplace add stayfixed/stayfixed`), run
    `claude plugin marketplace update stayfixed-marketplace`, then
    `claude plugin update stayfixed@stayfixed-marketplace`.
  - If you added it at a release tag (`stayfixed/stayfixed@vX.Y.Z`), add it again at this
    release's tag, `/plugin marketplace add stayfixed/stayfixed@vX.Y.Z` as the README's Install
    section names it, which points the marketplace you have at the new tag, then run
    `claude plugin update stayfixed@stayfixed-marketplace`. Do not remove the marketplace first:
    that uninstalls the plugin and deletes the options you saved for it.
