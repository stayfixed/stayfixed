An agent can read and edit `.env.example`, `.env.sample` and `.env.template` again. The deny
rules `stayfixed setup` writes refused every file whose name began with `.env`, templates included,
and an allow rule cannot override a deny rule, so nothing could let a template through. `setup` now
denies the common env file names one by one (`.env`, `.env.local`, `.env.*.local`, `.env.dev`,
`.env.development`, `.env.prod`, `.env.production`, `.env.stage`, `.env.staging`, `.env.test`) and
takes the old `Read(.env*)` and `Read(**/.env*)` masks back out of `~/.claude/settings.json`, so run
`stayfixed setup` once after upgrading. A new session guard, `env-reads`, refuses a `Read` or `Grep`
of an env file under any other name on Claude Code, and of a link to one; `env_reads = false` under `[guards]` in the
machine file switches it off. Which names count as env files is the same for the guard and for the
inventory's `tracked-env` item, which now matches them case-insensitively.
