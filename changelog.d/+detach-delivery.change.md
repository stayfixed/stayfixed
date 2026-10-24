`stayfixed detach` withdraws the overlay's rendered plugin: from the main checkout it runs `claude
plugin uninstall overlay-<id>@stayfixed-delivery-<id> --scope local` where that checkout's
`.claude/settings.local.json` names the plugin, and `claude plugin marketplace remove
stayfixed-delivery-<id>` where it names the marketplace, and removes
`~/.local/share/stayfixed/delivery/<id>/` where it is there, unless another checkout of the
repository is still attached. The directory comes from the binding id, never from the ledger. The
binding id and this machine's record of it stay, so a later `attach` binds the same checkout again.
The line says when the plugin was withdrawn, and `--json` carries `delivery_removed`. While the
settings file still names a `stayfixed-delivery-` marketplace once the calls ran, the binding id
read or not, the detach fails (exit 1), naming the key left, and keeps the exclude block, the ledger
and the render, so the file stays hidden; running `detach` again finishes the withdrawal. In a
worktree of a bare repository, `detach` withdraws that checkout's own parts.
