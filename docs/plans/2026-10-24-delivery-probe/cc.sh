#!/bin/sh
# cc.sh CFG_NAME -- claude args...   : run Claude Code against the stub, isolated config and home.
H="$HOME/.cache/stayfixed-spikes/hs2"; cfg="$H/cfg-$1"; shift; [ "$1" = "--" ] && shift
mkdir -p "$cfg" "$H/home"
exec env -i PATH="/usr/bin:/bin:/usr/sbin:/sbin:$HOME/.local/bin" HOME="$H/home" TERM="${TERM:-xterm-256color}" LANG=en_US.UTF-8 \
  CLAUDE_CONFIG_DIR="$cfg" ANTHROPIC_API_KEY=sk-ant-stub-000 ANTHROPIC_BASE_URL=http://127.0.0.1:8787 \
  CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1 DISABLE_AUTOUPDATER=1 \
  "$HOME/.local/bin/claude" "$@"
