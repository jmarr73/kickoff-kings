#!/usr/bin/env python3
# Kick Off Kings — Public Template (multi-user, caching, refresh)
from flask import Flask, request, session, redirect, url_for, render_template_string, abort, send_from_directory
import os, json, pathlib, datetime, requests, time

APP_DIR = pathlib.Path(__file__).resolve().parent
DATA_DIR = APP_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

YEAR = int(os.environ.get("NFL_YEAR", "2025"))
SEASONTYPE = int(os.environ.get("NFL_SEASONTYPE", "2"))

# Players: comma-separated, e.g. "joe,tom"
PLAYERS = [p.strip().lower() for p in os.environ.get("USERS", "user1,user2").split(",") if p.strip()]

def token_for(player: str) -> str:
    env_key = f"TOKEN_{player.upper()}"
    return os.environ.get(env_key, f"{player}_TOKEN")

SECRET_KEY = os.environ.get("FLASK_SECRET", "dev-secret")
BUILD_ID = os.environ.get("BUILD_ID") or datetime.datetime.utcnow().strftime("%Y%m%d%H%M%S")

app = Flask(__name__)
app.secret_key = SECRET_KEY

# ---------------- Utility ----------------
def render_page(body_tpl: str, **ctx):
    ctx.setdefault("build_id", BUILD_ID)
    body_html = render_template_string(body_tpl, **ctx)
    return render_template_string(TPL_BASE, body=body_html, **ctx)

def _load_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return default

def _save_json(path, obj):
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, ensure_ascii=False)
    os.replace(tmp, path)

def _iso_to_dt(s):
    return datetime.datetime.fromisoformat(s.replace("Z", "+00:00"))

def get_now_utc():
    return datetime.datetime.now(datetime.timezone.utc)

# ---------------- Storage helpers ----------------
def schedule_path(year, week, seasontype):
    return DATA_DIR / f"schedule-{year}-{week}-t{seasontype}.json"

def results_path(year, week, seasontype):
    return DATA_DIR / f"results-{year}-{week}-t{seasontype}.json"

def picks_path(year: int, week: int):
    return DATA_DIR / f"picks-{year}-{week}.json"

# ---------------- Schedules ----------------
def fetch_week_schedule(year: int, week: int, seasontype: int):
    url = "https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard"
    params = {"year": year, "week": week, "seasontype": seasontype}
    r = requests.get(url, params=params, timeout=20)
    r.raise_for_status()
    data = r.json()
    games = []
    for ev in data.get("events", []):
        comp = (ev.get("competitions") or [{}])[0]
        competitors = comp.get("competitors") or []
        if len(competitors) < 2:
            continue
        home = next((c for c in competitors if c.get("homeAway") == "home"), competitors[0])
        away = next((c for c in competitors if c.get("homeAway") == "away"), competitors[-1])
        start = comp.get("date") or ev.get("date")
        gid = ev.get("id") or comp.get("id")
        games.append({
            "id": str(gid),
            "start": start,
            "venue": (comp.get("venue") or {}).get("fullName"),
            "home": {
                "id": str(((home.get("team") or {}).get("id") or "")),
                "abbr": ((home.get("team") or {}).get("abbreviation") or ""),
                "name": ((home.get("team") or {}).get("displayName") or ""),
            },
            "away": {
                "id": str(((away.get("team") or {}).get("id") or "")),
                "abbr": ((away.get("team") or {}).get("abbreviation") or ""),
                "name": ((away.get("team") or {}).get("displayName") or ""),
            },
        })
    sched = {"year": year, "week": week, "seasontype": seasontype, "games": games}
    _save_json(schedule_path(year, week, seasontype), sched)
    return sched

def get_week_schedule(year: int, week: int, seasontype: int):
    path = schedule_path(year, week, seasontype)
    if path.exists():
        return _load_json(path, {})
    return fetch_week_schedule(year, week, seasontype)

# ---------------- Results (with caching + optional force refresh) ----------------
def fetch_results_for_week(year: int, week: int, seasontype: int):
    url = "https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard"
    params = {"year": year, "week": week, "seasontype": seasontype}
    r = requests.get(url, params=params, timeout=20)
    r.raise_for_status()
    data = r.json()
    winners = {}
    all_final = True
    for ev in data.get("events", []):
        comp = (ev.get("competitions") or [{}])[0]
        gid = str(ev.get("id") or comp.get("id"))
        st = (comp.get("status") or {}).get("type") or {}
        completed = bool(st.get("completed"))
        if not completed:
            all_final = False
        winner = None
        if completed:
            for c in (comp.get("competitors") or []):
                if c.get("winner"):
                    tid = str(((c.get("team") or {}).get("id") or ""))
                    winner = tid
                    break
        winners[gid] = winner
    return winners, all_final

def get_results_cached(year: int, week: int, seasontype: int, max_age_seconds: int = 900, force_refresh: bool = False):
    path = results_path(year, week, seasontype)
    now = time.time()

    if path.exists() and not force_refresh:
        cache = _load_json(path, {})
        if cache:
            if cache.get("complete") or (now - cache.get("fetched_at", 0) <= max_age_seconds):
                return cache.get("winners", {}), cache.get("complete", False)

    winners, complete = fetch_results_for_week(year, week, seasontype)
    _save_json(path, {"winners": winners, "complete": complete, "fetched_at": now})
    return winners, complete

# ---------------- Picks & Tally ----------------
def get_week_picks(year: int, week: int):
    return _load_json(picks_path(year, week), {})

def save_week_picks(year: int, week: int, data):
    _save_json(picks_path(year, week), data)

def is_game_locked(game):
    start = _iso_to_dt(game["start"])
    return get_now_utc() >= start

def tally_week(year: int, week: int, seasontype: int, force_refresh: bool = False):
    sched = get_week_schedule(year, week, seasontype)
    winners, _complete = get_results_cached(year, week, seasontype, force_refresh=force_refresh)
    picks = get_week_picks(year, week)

    team_abbr = {}
    for g in sched.get("games", []):
        team_abbr[g["away"]["id"]] = g["away"]["abbr"]
        team_abbr[g["home"]["id"]] = g["home"]["abbr"]

    scoreboard = {}
    for p in PLAYERS:
        psel = (picks.get(p) or {}).get("selections", {})
        wins = 0; losses = 0; pending = 0; pushes = 0
        game_rows = []
        for g in sched.get("games", []):
            gid = g["id"]
            mypick = psel.get(gid)
            win = winners.get(gid)

            status = "PENDING"
            if win is None:
                pending += 1
            else:
                if not mypick:
                    losses += 1; status = "LOSS (no pick)"
                elif mypick == win:
                    wins += 1; status = "WIN"
                else:
                    losses += 1; status = "LOSS"

            game_rows.append({
                "gid": gid,
                "away": g["away"]["abbr"],
                "home": g["home"]["abbr"],
                "pick": mypick,
                "pick_abbr": team_abbr.get(mypick, "-") if mypick else "-",
                "win": win,
                "win_abbr": team_abbr.get(win, "-") if win else "-",
                "status": status,
            })
        scoreboard[p] = {"wins": wins, "losses": losses, "pending": pending, "pushes": pushes, "games": game_rows}
    return winners, scoreboard

# ---------------- Auth & Routes ----------------
def ensure_player():
    player = session.get("player")
    return player if player in PLAYERS else None

@app.get("/login/<player>/<token>")
def login(player, token):
    player = (player or "").strip().lower()
    if player not in PLAYERS:
        abort(404)
    if token_for(player) != token:
        abort(403)
    session["player"] = player
    return redirect(url_for("choose_week"))

@app.get("/logout")
def logout():
    session.clear()
    return redirect(url_for("choose_week"))

@app.get("/")
def choose_week():
    player = ensure_player()
    weeks = list(range(1, 19))
    return render_page(TPL_HOME, player=player, weeks=weeks, year=YEAR, players=PLAYERS)

@app.get("/week/<int:week>")
def view_week(week: int):
    player = ensure_player()
    if not player:
        return redirect(url_for("choose_week"))
    sched = get_week_schedule(YEAR, week, SEASONTYPE)
    picks = get_week_picks(YEAR, week)
    my = picks.get(player, {"locked": False, "selections": {}})
    locks = {g["id"]: is_game_locked(g) for g in sched.get("games", [])}
    return render_page(TPL_WEEK, player=player, year=YEAR, week=week, sched=sched, my=my, locks=locks)

@app.post("/submit/<int:week>")
def submit_week(week: int):
    player = ensure_player()
    if not player:
        abort(403)
    action = request.form.get("action", "lock")
    sched = get_week_schedule(YEAR, week, SEASONTYPE)
    picks = get_week_picks(YEAR, week)
    me = picks.get(player, {"locked": False, "selections": {}})

    if me.get("locked"):
        return redirect(url_for("view_week", week=week))

    selections = {}
    for g in sched.get("games", []):
        gid = g["id"]
        val = request.form.get(f"pick_{gid}")
        if val and not is_game_locked(g):
            selections[gid] = val

    existing = me.get("selections", {})
    existing.update(selections)
    me["selections"] = existing

    if action == "lock":
        me["locked"] = True
        me["locked_at"] = datetime.datetime.utcnow().isoformat() + "Z"

    picks[player] = me
    save_week_picks(YEAR, week, picks)
    return redirect(url_for("view_week", week=week))

@app.get("/results/<int:week>")
def view_results(week: int):
    player = ensure_player()
    if not player:
        return redirect(url_for("choose_week"))
    force = request.args.get("refresh") == "1"
    winners, board = tally_week(YEAR, week, SEASONTYPE, force_refresh=force)
    return render_page(TPL_RESULTS, player=player, year=YEAR, week=week, board=board, players=PLAYERS)

@app.get("/season")
def season_totals():
    player = ensure_player()
    if not player:
        return redirect(url_for("choose_week"))

    phases = [
        {"label": "Regular Season", "seasontype": 2, "weeks": list(range(1, 19)), "wklabel": lambda w: f"Week {w}"},
        {"label": "Postseason", "seasontype": 3, "weeks": list(range(1, 5)),
         "wklabel": lambda w: {1: "Wild Card", 2: "Divisional", 3: "Conference", 4: "Super Bowl"}[w]},
    ]

    total = {p: {"wins": 0, "losses": 0, "pending": 0, "pushes": 0} for p in PLAYERS}
    phases_out = []

    for ph in phases:
        rows = []
        for w in ph["weeks"]:
            try:
                _, board = tally_week(YEAR, w, ph["seasontype"])
            except Exception:
                continue
            row = {"label": ph["wklabel"](w),
                   "per_player": {p: {"wins": board[p]["wins"], "losses": board[p]["losses"]} for p in PLAYERS}}
            rows.append(row)
            for p in PLAYERS:
                for k in total[p]:
                    total[p][k] += board[p][k]
        phases_out.append({"label": ph["label"], "rows": rows})

    return render_page(TPL_SEASON, player=player, year=YEAR, totals=total, phases=phases_out, players=PLAYERS)

@app.get("/healthz")
def healthz():
    return {"ok": True, "build": BUILD_ID, "players": PLAYERS}, 200

@app.get("/static/<path:path>")
def static_file(path):
    return send_from_directory(str(APP_DIR / "static"), path)

# ---------------- Templates ----------------
TPL_BASE = r"""
<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Kick Off Kings</title>
  <link rel="icon" href="{{ url_for('static_file', path='favicon.svg') }}?v={{ build_id }}" type="image/svg+xml">
  <style>
    body { font-family: system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif; margin: 24px; }
    .nav a { margin-right: 12px; }
    table { border-collapse: collapse; width: 100%; }
    th, td { border: 1px solid #ddd; padding: 8px; }
    th { background: #f5f5f5; text-align: left; }
    .locked { color: #a00; font-weight: 600; }
    .ok { color: #0a0; font-weight: 600; }
    .muted { color: #666; font-size: 0.9em; }
    .btn { padding: 8px 12px; border: 1px solid #ccc; background: #fafafa; cursor: pointer; text-decoration: none; display: inline-block; }
    .btn-primary { background: #e8f0fe; border-color: #90caf9; }
    .grid { display: grid; gap: 8px; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); }
    .card { border: 1px solid #ddd; border-radius: 12px; padding: 12px; display: flex; align-items: center; justify-content: space-between; gap: 12px; }
    .card .title { font-weight: 600; }
    .actions { display: flex; gap: 8px; flex-wrap: wrap; }
  </style>
</head>
<body>
  <div class="nav">
    {% if player %}
      Logged in as <b>{{player}}</b> |
      <a href="{{ url_for('choose_week') }}">Home</a>
      <a href="{{ url_for('season_totals') }}">Season totals</a>
      <a href="{{ url_for('logout') }}">Logout</a>
    {% else %}
      <span class="muted">Not logged in. Use your login link.</span>
    {% endif %}
  </div>
  {{ body|safe }}
</body>
</html>
"""

TPL_HOME = r"""
  <h1>NFL Picks — {{year}}</h1>
  {% if not player %}
    <p>Use your login link.</p>
  {% endif %}
  <div class="grid">
  {% for w in weeks %}
    <div class="card">
      <div class="title">Week {{w}}</div>
      <div class="actions">
        <a class="btn btn-primary" href="{{ url_for('view_week', week=w) }}">Open</a>
        <a class="btn" href="{{ url_for('view_results', week=w) }}">Results</a>
      </div>
    </div>
  {% endfor %}
  </div>

  <h3>Players</h3>
  <ul>
    {% for p in players %}<li>{{ p }}</li>{% endfor %}
  </ul>
"""

TPL_WEEK = r"""
  <h2>Week {{week}} — {{year}}</h2>
  <form method="post" action="{{ url_for('submit_week', week=week) }}">
  <table>
    <thead>
      <tr><th>Kickoff (UTC)</th><th>Away</th><th>Home</th><th>Your pick</th><th>Status</th></tr>
    </thead>
    <tbody>
      {% for g in sched.games %}
      {% set gid = g.id %}
      {% set mypick = my.selections.get(gid) %}
      {% set locked = locks.get(gid) %}
      <tr>
        <td>{{ g.start }}</td>
        <td>{{ g.away.abbr }}</td>
        <td>{{ g.home.abbr }}</td>
        <td>
          <label><input type="radio" name="pick_{{gid}}" value="{{ g.away.id }}" {% if mypick == g.away.id %}checked{% endif %} {% if locked or my.locked %}disabled{% endif %}> {{ g.away.abbr }}</label>
          <label><input type="radio" name="pick_{{gid}}" value="{{ g.home.id }}" {% if mypick == g.home.id %}checked{% endif %} {% if locked or my.locked %}disabled{% endif %}> {{ g.home.abbr }}</label>
        </td>
        <td>
          {% if my.locked %}<span class="locked">WEEK LOCKED</span>
          {% elif locked %}<span class="locked">LOCKED (kickoff)</span>
          {% else %}<span class="ok">OPEN</span>{% endif %}
        </td>
      </tr>
      {% endfor %}
    </tbody>
  </table>
  {% if not my.locked %}
    <div style="margin-top:12px;">
      <button class="btn" name="action" value="save" type="submit">Save (draft)</button>
      <button class="btn btn-primary" name="action" value="lock" type="submit">Submit (lock week)</button>
    </div>
  {% else %}
    <p class="muted">Your picks are locked for this week.</p>
  {% endif %}
  </form>
"""

TPL_RESULTS = r"""
  <h2>Results — Week {{week}} ({{year}})</h2>
  <p><a class="btn" href="{{ url_for('view_results', week=week) }}?refresh=1">🔄 Refresh Results</a></p>
  {% for p, row in board.items() %}
    <h3>{{p}} — {{row.wins}}-{{row.losses}}{% if row.pushes %} ({{row.pushes}} pushes){% endif %}{% if row.pending %} — {{row.pending}} pending{% endif %}</h3>
    <table>
      <thead><tr><th>Game</th><th>Pick</th><th>Winner</th><th>Status</th></tr></thead>
      <tbody>
      {% for g in row.games %}
        <tr>
          <td>{{ g.away }} @ {{ g.home }}</td>
          <td>{{ g.pick_abbr }}</td>
          <td>{{ g.win_abbr }}</td>
          <td>{{ g.status }}</td>
        </tr>
      {% endfor %}
      </tbody>
    </table>
  {% endfor %}
"""

TPL_SEASON = r"""
  <h2>Season totals — {{year}}</h2>
  <table>
    <thead><tr><th>Player</th><th>Wins</th><th>Losses</th><th>Pushes</th><th>Pending</th></tr></thead>
    <tbody>
      {% for p, t in totals.items() %}
      <tr><td>{{p}}</td><td>{{t.wins}}</td><td>{{t.losses}}</td><td>{{t.pushes}}</td><td>{{t.pending}}</td></tr>
      {% endfor %}
    </tbody>
  </table>

  {% for ph in phases %}
    <h3>{{ ph.label }}</h3>
    <table>
      <thead>
        <tr>
          <th>Round / Week</th>
          {% for p in players %}<th>{{ p }}</th>{% endfor %}
        </tr>
      </thead>
      <tbody>
      {% for row in ph.rows %}
        <tr>
          <td>{{ row.label }}</td>
          {% for p in players %}
            <td>{{ row.per_player[p].wins }}-{{ row.per_player[p].losses }}</td>
          {% endfor %}
        </tr>
      {% endfor %}
      </tbody>
    </table>
  {% endfor %}
"""

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "5000")), debug=True)
