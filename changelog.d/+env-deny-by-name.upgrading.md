The deny rules `stayfixed setup` writes now name the common env files one by one in place of the
`.env*` masks, and `setup` takes the old masks back out of `~/.claude/settings.json`: an env file
under any other name, such as `.env.secrets`, is no longer refused to an agent. Run `stayfixed
setup` once after upgrading, and add a `Read(...)` deny rule of your own for any such file.
