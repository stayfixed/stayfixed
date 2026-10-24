`stayfixed detach` withdraws the overlay's rendered plugin: it runs `claude plugin uninstall
overlay-<id>@stayfixed-delivery-<id> --scope local` and `claude plugin marketplace remove
stayfixed-delivery-<id>` from the main checkout and removes `~/.local/share/stayfixed/delivery/<id>/`,
where that directory is there and no other checkout of the repository is still attached. The
directory comes from the binding id, never from the ledger. The binding id and this machine's
record of it stay, so a later `attach` binds the same checkout again. The line says when the plugin
was withdrawn, and `--json` carries `delivery_removed`. A `claude plugin` call that does not
succeed fails the detach (exit 1), naming the call and its exit code, and keeps the exclude block,
the ledger and the render, so `.claude/settings.local.json`, which names the binding id, stays
hidden; running `detach` again finishes the withdrawal.
