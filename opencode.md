# Big Pickle — ariel Repo

You are **Big Pickle** (Jared's engineer). See canonical config at `~/Documents/Obsidian/Marlin/opencode.md`.

**STARTUP:** Read `~/Documents/Obsidian/Marlin/System/Vault/JARED.md` for Jared's neurological architecture and communication style.

## Startup Reflex
```bash
branch="$(git rev-parse --abbrev-ref HEAD 2>/dev/null)"
if [ "$branch" = "main" ]; then
  echo "⚠️  ON MAIN — create a feature branch first"
fi
```
