A `[budgets]` value in `stayfixed.toml` above the preset's, which 0.3.1 ignored, is now in force:
every command and gate that reads the budget applies the number written there, and `stayfixed
doctor`'s `budgets` row names it as raised. A pull request that raises a budget above the base
branch's is now refused by `stayfixed gate`, where 0.3.1 read both sides at the preset's value and
saw no change.
