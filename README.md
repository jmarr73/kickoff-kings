# Kick Off Kings — NFL Picks (Flask + Docker)

Self-hosted web app for making weekly NFL picks with friends or family.  
Pulls schedules/scores from ESPN’s public feed, lets each player lock picks, and tallies wins/losses.  
Flat-file JSON storage. Easy to run locally or on a small VPS.

<p align="center">
  <b>Features:</b> multi-user support, token login links, auto game lock at kickoff, weekly & season totals (regular + playoffs), caching, one-click “Refresh Results”
</p>

---

## Demo (Screens)
- **Home**: select a week, view available weeks, quick links to results
- **Week**: radio buttons for each game, Save Draft or Submit (lock)
- **Results**: per-player breakdown, team abbreviations shown for picks/winners
- **Season totals**: regular season + postseason roll-up

---

## Quick Start (Docker)

```bash
git clone https://github.com/<your-username>/kickoff-kings.git
cd kickoff-kings
```

### 1) Create .env with generated secrets/tokens
```bash
cat > .env << 'EOF'
FLASK_SECRET=$(openssl rand -hex 32)
TOKEN_USER1=$(openssl rand -hex 24)
TOKEN_USER2=$(openssl rand -hex 24)
NFL_YEAR=2025
NFL_SEASONTYPE=2
BUILD_ID=localdev
EOF
```

### 2) Option A — Local test (no HTTPS)

```bash
docker compose -f docker-compose.basic.yml up -d --build
```

#### *open* http://localhost:8000/login/user1/$TOKEN_USER1

### 3) Option B — HTTPS with Caddy (requires a domain)

#### Set your DNS (e.g., picks.yourdomain.com -> server IP)

```bash
docker compose -f docker-compose.caddy.yml up -d --build
```

#### *open* https://picks.yourdomain.com/login/user1/$TOKEN_USER1

---

## Environment Variables

| Name             | Default | Notes                                                  |
| ---------------- | ------- | ------------------------------------------------------ |
| `FLASK_SECRET`   | (none)  | Long random string for Flask sessions                  |
| `TOKEN_USER1`    | (none)  | Token for `user1` login URL                            |
| `TOKEN_USER2`    | (none)  | Token for `user2` login URL                            |
| `NFL_YEAR`       | `2025`  | Season year                                            |
| `NFL_SEASONTYPE` | `2`     | 1 = Preseason, **2 = Regular**, 3 = Postseason         |
| `BUILD_ID`       | (none)  | Optional; used for cache busting and `/healthz` output |

#### Login URLs

```
/login/user1/$TOKEN_USER1
/login/user2/$TOKEN_USER2
```

#### Example: Generate secure secrets/tokens

```bash
# Flask secret (64 hex chars)
openssl rand -hex 32

# User tokens (48 hex chars each)
openssl rand -hex 24
openssl rand -hex 24

# Or with Python
python -c "import secrets; print(secrets.token_hex(32))"   # Flask secret
python -c "import secrets; print(secrets.token_hex(24))"   # User token
```

---

## Data Persistence

All saved under `./data/` on the host (mounted into the container):

* Picks: `picks-<year>-<week>.json`
* Cached schedules: `schedule-<year>-<week>-t<type>.json`
* Cached results: `results-<year>-<week>-t<type>.json`

---

## Refresh Results

On a week’s Results page, click **🔄 Refresh Results** to bypass cache and fetch live scores.

---

## VPS Deployment (Example: Linode, Ubuntu 22.04)

Steps:

1. Create a Linode (Ubuntu 22.04, 1GB Nanode is enough).
2. In DNS (e.g., Namecheap), add an **A record**: `picks.yourdomain.com` → VPS IP.
3. Paste the `cloud-init-linode.yaml` contents into **User Data** when creating the Linode.
4. Edit placeholders (`GIT_REPO`, `DOMAIN`, `.env` values) before use.
5. After 1–2 minutes, visit `https://picks.yourdomain.com`.

---

## Development

* App entrypoint: `app.py`
* Static assets: `static/` (includes `favicon.svg` football icon)
* Run locally without Docker (dev only):

  ```bash
  pip install -r requirements.txt
  python app.py
  ```

---

## Notes

* Uses ESPN’s public scoreboard JSON (no API key required).
* Default setup provides 2 players (`user1`, `user2`), but you can add more in `.env`.
* Works for regular season and postseason.

---

## License

MIT — see [LICENSE](LICENSE).

---

### Acknowledgements

* ESPN public scoreboard JSON for schedules & results
* [Caddy](https://caddyserver.com/) for painless HTTPS with Let’s Encrypt

```
```
