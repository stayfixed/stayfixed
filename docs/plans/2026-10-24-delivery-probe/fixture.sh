#!/bin/sh
# Build the probe's fixture under $H: one plugin `sf-deliv` in a directory marketplace `sf-hs2`
# whose SessionStart hook logs where it ran from and returns a canary as additionalContext.
set -eu
H="$HOME/.cache/stayfixed-spikes/hs2"; M="$H/market"
rm -rf "$M" "$H/marks"; mkdir -p "$M/.claude-plugin" "$M/sf-deliv/.claude-plugin" "$M/sf-deliv/hooks" "$H/marks" "$H/req"
printf '%s\n' '{"name": "sf-hs2", "owner": {"name": "spike"}, "plugins": [{"name": "sf-deliv", "source": "./sf-deliv", "description": "HS2 probe fixture."}]}' >"$M/.claude-plugin/marketplace.json"
printf '%s\n' '{"name": "sf-deliv", "version": "0.0.1", "description": "HS2 probe fixture."}' >"$M/sf-deliv/.claude-plugin/plugin.json"
printf '%s\n' '{"hooks": {"SessionStart": [{"hooks": [{"type": "command", "command": "${CLAUDE_PLUGIN_ROOT}/hooks/start.sh"}]}]}}' >"$M/sf-deliv/hooks/hooks.json"
cat >"$M/sf-deliv/hooks/start.sh" <<HOOK
#!/bin/sh
cat >/dev/null
printf 'root=%s project=%s rev=%s\n' "\$CLAUDE_PLUGIN_ROOT" "\${CLAUDE_PROJECT_DIR:-\$PWD}" "\$(cat "\$CLAUDE_PLUGIN_ROOT/REV")" >>"$H/marks/start.log"
printf '{"hookSpecificOutput":{"hookEventName":"SessionStart","additionalContext":"SF-CANARY rev %s"}}\n' "\$(cat "\$CLAUDE_PLUGIN_ROOT/REV")"
HOOK
chmod +x "$M/sf-deliv/hooks/start.sh"; echo r1 >"$M/sf-deliv/REV"
cp "$(dirname "$0")/stub.py" "$(dirname "$0")/cc.sh" "$(dirname "$0")/dontask.exp" "$H/"
