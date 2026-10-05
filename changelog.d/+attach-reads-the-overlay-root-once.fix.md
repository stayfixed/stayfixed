`stayfixed attach`, `attach --check` and `stayfixed doctor`'s `attached` row now read the overlay
root out of the machine configuration once when they check the `--store` a run names. They read
it a second time for the binding itself, so a machine file changed between the two reads could have
the store checked against one overlay and the binding read from another.
