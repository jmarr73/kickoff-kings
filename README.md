# Kick Off Kings — NFL Picks (Public Template)

Self-hosted weekly picks with token links, game auto-locking, results, and season totals (regular + playoffs). Multi-user ready via `.env`.

## Interactive Setup
```bash
./setup.sh
# prompts: domain, season year/type, user list; writes .env and prints login URLs
```

## Run
```bash
docker compose -f docker-compose.basic.yml up -d --build
# or
docker compose -f docker-compose.caddy.yml up -d --build  # (update Caddyfile domain or set via setup.sh)
```

## Configure Users
- Edit `.env`:
  - `USERS=alice,bob,charlie`
  - Add tokens: `TOKEN_ALICE=...`, `TOKEN_BOB=...`, etc.
- Login URL format: `/login/<user>/<token>`

Data persists in `./data/`. Results and schedules are cached. Click **Refresh Results** on the week page to bypass cache on demand.
