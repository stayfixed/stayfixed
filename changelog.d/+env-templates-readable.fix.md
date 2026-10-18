An agent can read and edit an env file's template again: `.env.example`, `.env.dist`,
`.env.sample` and the rest. The deny rules `stayfixed setup` wrote refused every file whose name
began with `.env`, templates included, and an allow rule cannot override a deny rule, so nothing
could let a template through. `setup` now denies the common env file names one by one (`.env`,
`.env.local`, `.env.*.local`, `.env.dev`, `.env.development`, `.env.prod`, `.env.production`,
`.env.stage`, `.env.staging`, `.env.test`) and takes the old `Read(.env*)` and `Read(**/.env*)`
masks back out of `~/.claude/settings.json`, so run `stayfixed setup` once after upgrading;
`stayfixed doctor`'s new `retired-deny` row says so while a mask is still there. An env file under
any other name is no longer refused.
