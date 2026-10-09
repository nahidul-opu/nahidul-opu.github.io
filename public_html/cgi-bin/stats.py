#!/usr/bin/python3
"""Private visitor statistics for https://home.cc.umanitoba.ca/~opumni/

Open https://home.cc.umanitoba.ca/~opumni/cgi-bin/stats.py and log in.
Set or change the password (run on the server, e.g. over ssh):
    python3 ~/public_html/cgi-bin/stats.py --set-password

Reads ~/site-data/visits.sqlite, which hit.py fills. Logging in also stops
counting your own visits in that browser.
"""
import getpass
import hashlib
import hmac
import html
import json
import os
import re
import secrets
import sqlite3
import sys
import time
from urllib.parse import parse_qs

os.environ["TZ"] = "America/Winnipeg"
time.tzset()

DATA_DIR = os.environ.get("SITE_DATA_DIR") or os.path.join(os.path.expanduser("~"), "site-data")
DB_PATH = os.path.join(DATA_DIR, "visits.sqlite")
SECRET_PATH = os.path.join(DATA_DIR, "secret.key")
CONFIG_PATH = os.path.join(DATA_DIR, "config.json")
COOKIE = "opumni_stats"
SESSION_SECONDS = 30 * 86400
RANGES = (("7", "7 days"), ("30", "30 days"), ("90", "90 days"), ("365", "1 year"), ("all", "All time"))
OWN_HOSTS = ("home.cc.umanitoba.ca", "localhost", "127.0.0.1")
ZONEINFO = "/usr/share/zoneinfo"
TZ_NAME = re.compile(r"^[A-Za-z0-9_+\-]+(/[A-Za-z0-9_+\-]+)*$")


# ---------- secrets, password, session ----------

def read_secret():
    os.makedirs(DATA_DIR, mode=0o700, exist_ok=True)
    try:
        fd = os.open(SECRET_PATH, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        with open(SECRET_PATH) as f:
            return f.read().strip()
    with os.fdopen(fd, "w") as f:
        key = secrets.token_hex(32)
        f.write(key)
        return key


def password_hash(password, salt):
    return hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), 200000).hex()


def set_password():
    password = getpass.getpass("New dashboard password: ")
    if len(password) < 8:
        sys.exit("Use at least 8 characters.")
    if getpass.getpass("Repeat it: ") != password:
        sys.exit("The passwords don't match.")
    os.makedirs(DATA_DIR, mode=0o700, exist_ok=True)
    salt = secrets.token_hex(16)
    fd = os.open(CONFIG_PATH, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump({"salt": salt, "hash": password_hash(password, salt)}, f)
    read_secret()
    print("Password saved in %s" % CONFIG_PATH)


def password_ok(password):
    try:
        with open(CONFIG_PATH) as f:
            cfg = json.load(f)
    except (OSError, ValueError):
        return False
    return hmac.compare_digest(password_hash(password, cfg["salt"]), cfg["hash"])


def read_cookie(name):
    # Parsed by hand: the university's load balancer sets a cookie that SimpleCookie trips over.
    for part in os.environ.get("HTTP_COOKIE", "").split(";"):
        key, _, value = part.strip().partition("=")
        if key == name:
            return value
    return ""


def make_session(secret):
    expires = str(int(time.time()) + SESSION_SECONDS)
    sig = hmac.new(secret.encode(), ("session:" + expires).encode(), hashlib.sha256).hexdigest()
    return expires + "." + sig


def session_ok(value, secret):
    expires, _, sig = value.partition(".")
    if not expires.isdigit() or int(expires) < time.time():
        return False
    good = hmac.new(secret.encode(), ("session:" + expires).encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(sig, good)


# ---------- output ----------

def esc(value):
    return html.escape(str(value), quote=True)


def cookie_path():
    script = os.environ.get("SCRIPT_NAME", "/cgi-bin/stats.py")
    return script.rsplit("/", 1)[0] + "/"


def respond(body, cookie=None):
    out = ["Content-Type: text/html; charset=utf-8",
           "Cache-Control: no-store",
           "X-Robots-Tag: noindex, nofollow",
           "Referrer-Policy: no-referrer",
           "X-Frame-Options: DENY"]
    if cookie is not None:
        out.append("Set-Cookie: %s=%s; Path=%s; Max-Age=%d; HttpOnly; Secure; SameSite=Strict"
                   % (COOKIE, cookie, cookie_path(), SESSION_SECONDS if cookie else 0))
    sys.stdout.buffer.write(("\r\n".join(out) + "\r\n\r\n" + body).encode("utf-8"))


STYLE = """
:root { --bg:#f6f7fb; --surface:#fff; --surface-2:#eff2f8; --text:#171a23; --muted:#566074;
  --border:#e0e5ee; --accent:#2f52e0; --accent-soft:#e8edfd; --on-accent:#fff; color-scheme: light dark; }
@media (prefers-color-scheme: dark) { :root { --bg:#0d1016; --surface:#151a23; --surface-2:#1c2230;
  --text:#e8ebf2; --muted:#a0a9ba; --border:#283042; --accent:#8aa7ff; --accent-soft:#1d2642; --on-accent:#0d1016; } }
* { box-sizing: border-box; }
body { margin: 0; font: 15px/1.5 system-ui, -apple-system, "Segoe UI", Roboto, Arial, sans-serif; background: var(--bg); color: var(--text); }
a { color: var(--accent); }
.wrap { max-width: 1120px; margin: 0 auto; padding: 24px 20px 48px; }
header { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 12px; margin-bottom: 20px; }
h1 { font-size: 1.5rem; margin: 0; letter-spacing: -0.02em; }
h2 { font-size: 1rem; margin: 0 0 12px; }
.muted { color: var(--muted); }
.ranges { display: flex; flex-wrap: wrap; gap: 6px; }
.ranges a { padding: 6px 12px; border-radius: 999px; border: 1px solid var(--border); background: var(--surface); color: var(--text); text-decoration: none; font-size: 14px; }
.ranges a.on { background: var(--accent); border-color: var(--accent); color: var(--on-accent); font-weight: 600; }
.tiles { display: grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr)); gap: 12px; margin-bottom: 16px; }
.tile, .panel { background: var(--surface); border: 1px solid var(--border); border-radius: 14px; padding: 16px; }
.tile .label { color: var(--muted); font-size: 13px; }
.tile .value { font-size: 1.7rem; font-weight: 700; letter-spacing: -0.02em; overflow-wrap: anywhere; }
.tile .value.small { font-size: 1.05rem; padding-top: 6px; }
.panels { display: grid; grid-template-columns: repeat(auto-fit, minmax(330px, 1fr)); gap: 16px; }
.panel.wide { grid-column: 1 / -1; }
table { width: 100%; border-collapse: collapse; font-size: 14px; }
th, td { text-align: left; padding: 6px 4px; border-bottom: 1px solid var(--border); vertical-align: top; }
th { color: var(--muted); font-weight: 600; font-size: 12.5px; }
td.num, th.num { text-align: right; font-variant-numeric: tabular-nums; white-space: nowrap; }
td.name { overflow-wrap: anywhere; }
.bar { height: 6px; border-radius: 3px; background: var(--accent); opacity: .75; margin-top: 4px; }
tr.top td { font-weight: 650; }
.chart { width: 100%; height: 190px; display: block; }
.chart rect { fill: var(--accent); }
.chart text { fill: var(--muted); font-size: 11px; }
.chart line { stroke: var(--border); }
form.login { max-width: 360px; margin: 12vh auto; background: var(--surface); border: 1px solid var(--border); border-radius: 16px; padding: 28px; }
input[type=password] { width: 100%; padding: 10px 12px; font: inherit; border-radius: 10px; border: 1px solid var(--border); background: var(--bg); color: var(--text); margin: 12px 0; }
button { font: inherit; font-weight: 600; padding: 9px 16px; border-radius: 999px; border: 1px solid var(--accent); background: var(--accent); color: var(--on-accent); cursor: pointer; }
button.ghost { background: transparent; color: var(--text); border-color: var(--border); }
.error { color: #d23c3c; }
footer { margin-top: 20px; font-size: 13px; }
"""


def page(title, body):
    return ("<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">"
            "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
            "<meta name=\"robots\" content=\"noindex, nofollow\">"
            "<title>%s</title><style>%s</style></head><body>%s</body></html>" % (esc(title), STYLE, body))


def login_page(error=""):
    if not os.path.exists(CONFIG_PATH):
        error = ("No password set yet. On the server run: "
                 "<code>python3 ~/public_html/cgi-bin/stats.py --set-password</code>")
    return page("Site stats: log in", """
<form class="login" method="post">
  <h1>Site stats</h1>
  <p class="muted">Private dashboard for home.cc.umanitoba.ca/~opumni</p>
  %s
  <input type="hidden" name="action" value="login">
  <label>Password<input type="password" name="password" autocomplete="current-password" autofocus required></label>
  <button type="submit">Log in</button>
</form>""" % ('<p class="error">%s</p>' % error if error else ""))


def error_page(problem):
    return page("Site stats: setup needed", """<div class="wrap"><h1>Site stats: setup needed</h1>
<p>The dashboard can't use its data folder <code>%s</code>:</p><pre>%s</pre>
<p>On the server, run <code>mkdir -m 700 ~/site-data</code>, then reload this page.</p></div>"""
                % (esc(DATA_DIR), esc(problem)))


# ---------- locations from time zones ----------

def load_zone_tables():
    """Country names, zone -> country, and zone-file inode -> country (for alias names)."""
    names, zones, inodes = {}, {}, {}
    try:
        with open(os.path.join(ZONEINFO, "iso3166.tab"), encoding="utf-8") as f:
            for line in f:
                if not line.startswith("#") and "\t" in line:
                    code, name = line.rstrip("\n").split("\t", 1)
                    names[code] = name
        with open(os.path.join(ZONEINFO, "zone.tab"), encoding="utf-8") as f:
            for line in f:
                parts = line.rstrip("\n").split("\t")
                if line.startswith("#") or len(parts) < 3:
                    continue
                zones[parts[2]] = parts[0]
                try:
                    inodes.setdefault(os.stat(os.path.join(ZONEINFO, parts[2])).st_ino, parts[0])
                except OSError:
                    pass
    except OSError:
        pass
    return names, zones, inodes


NAMES, ZONES, INODES = load_zone_tables()


def country_of(tz):
    """ISO code for a browser time zone, e.g. Asia/Dhaka -> BD; old names like Asia/Calcutta work too."""
    if tz in ZONES:
        return ZONES[tz]
    if tz and TZ_NAME.match(tz):
        try:
            return INODES.get(os.stat(os.path.join(ZONEINFO, tz)).st_ino)
        except OSError:
            pass
    return None


def flag(code):
    return "".join(chr(0x1F1E6 + ord(c) - 65) for c in code) if code and len(code) == 2 else ""


def place(tz):
    code = country_of(tz)
    if not code:
        return "Unknown"
    return "%s %s" % (flag(code), NAMES.get(code, code))


# ---------- dashboard ----------

def table(headers, rows, top=False, bar_col=None):
    """rows: lists of already-escaped cell HTML; numeric columns are those whose header starts with '#'."""
    if not rows:
        return '<p class="muted">No data yet.</p>'
    peak = max((r[bar_col] for r in rows), default=0) if bar_col is not None else 0
    head = "".join('<th class="num">%s</th>' % h[1:] if h.startswith("#") else "<th>%s</th>" % h for h in headers)
    body = []
    for i, r in enumerate(rows):
        cells = []
        for j, (h, c) in enumerate(zip(headers, r)):
            if h.startswith("#"):
                cells.append('<td class="num">%s</td>' % c)
            else:
                bar = ""
                if bar_col is not None and j == 0 and peak:
                    bar = '<div class="bar" style="width:%d%%"></div>' % max(2, round(100 * r[bar_col] / peak))
                cells.append('<td class="name">%s%s</td>' % (c, bar))
        body.append('<tr%s>%s</tr>' % (' class="top"' if top and i == 0 else "", "".join(cells)))
    return "<table><tr>%s</tr>%s</table>" % (head, "".join(body))


def day_list(first, last):
    days, t = [], time.mktime(time.strptime(first, "%Y-%m-%d")) + 43200
    end = time.mktime(time.strptime(last, "%Y-%m-%d")) + 43200
    while t <= end + 1:
        days.append(time.strftime("%Y-%m-%d", time.localtime(t)))
        t += 86400
    return days


def chart(series):
    """Simple SVG bar chart of views per day; hover a bar for its numbers."""
    if not series:
        return '<p class="muted">No data yet.</p>'
    w, h, pad = 1000, 190, 24
    peak = max(v for _, v, _ in series) or 1
    step = w / len(series)
    bars = []
    for i, (day, views, visitors) in enumerate(series):
        bh = (h - pad - 8) * views / peak
        bars.append('<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" rx="2"><title>%s: %d views, %d visitors</title></rect>'
                    % (i * step + step * 0.12, h - pad - bh, max(step * 0.76, 1), max(bh, 0), day, views, visitors))
    labels = ('<text x="0" y="%d">%s</text><text x="%d" y="%d" text-anchor="end">%s</text>'
              '<text x="0" y="10">max %d/day</text>' % (h - 6, series[0][0], w, h - 6, series[-1][0], peak))
    return ('<svg class="chart" viewBox="0 0 %d %d" preserveAspectRatio="none" role="img" aria-label="Views per day">'
            '<line x1="0" x2="%d" y1="%d" y2="%d"/>%s%s</svg>' % (w, h, w, h - pad, h - pad, "".join(bars), labels))


def dashboard(rng):
    days = dict(RANGES)
    if rng not in days:
        rng = "30"
    today = time.strftime("%Y-%m-%d")
    since = "0000-00-00" if rng == "all" else time.strftime(
        "%Y-%m-%d", time.localtime(time.time() - (int(rng) - 1) * 86400))

    if not os.path.exists(DB_PATH):
        body = '<div class="wrap"><h1>Site stats</h1><p class="muted">No visits recorded yet.</p></div>'
        return page("Site stats", body)
    con = sqlite3.connect(DB_PATH, timeout=10)
    q = lambda sql, *args: con.execute(sql, args).fetchall()
    V = "kind = 'view' AND day >= ?"

    views, visitors = q("SELECT COUNT(*), COUNT(DISTINCT day || visitor) FROM hits WHERE " + V, since)[0]
    t_views, t_visitors = q("SELECT COUNT(*), COUNT(DISTINCT visitor) FROM hits WHERE kind = 'view' AND day = ?", today)[0]
    per_day = {d: (v, u) for d, v, u in q(
        "SELECT day, COUNT(*), COUNT(DISTINCT visitor) FROM hits WHERE " + V + " GROUP BY day", since)}
    pages = q("SELECT page, COUNT(*) AS n, COUNT(DISTINCT day || visitor) FROM hits WHERE " + V
              + " GROUP BY page ORDER BY n DESC LIMIT 25", since)
    referrers = q("SELECT referrer, COUNT(*) AS n FROM hits WHERE " + V + " AND referrer NOT IN (?, ?, ?)"
                  " GROUP BY referrer ORDER BY n DESC LIMIT 20", since, *OWN_HOSTS)
    by_tz = q("SELECT tz, COUNT(*), COUNT(DISTINCT day || visitor) FROM hits WHERE " + V + " GROUP BY tz", since)
    tech = {col: q("SELECT %s, COUNT(DISTINCT day || visitor) AS n FROM hits WHERE %s GROUP BY %s ORDER BY n DESC"
                   % (col, V, col), since) for col in ("device", "browser", "os")}
    clicks = q("SELECT target, COUNT(*) AS n FROM hits WHERE kind = 'click' AND day >= ?"
               " GROUP BY target ORDER BY n DESC LIMIT 20", since)
    recent = q("SELECT ts, page, tz, referrer, device, browser FROM hits WHERE kind = 'view' ORDER BY id DESC LIMIT 50")
    total_rows = q("SELECT COUNT(*) FROM hits")[0][0]
    first_day = q("SELECT MIN(day) FROM hits")[0][0] or today
    con.close()

    countries, zones = {}, {}
    for tz, v, u in by_tz:
        c = countries.setdefault(place(tz), [0, 0])
        c[0] += v
        c[1] += u
        z = zones.setdefault(tz or "Unknown", [0, 0])
        z[0] += v
        z[1] += u
    country_rows = sorted(countries.items(), key=lambda kv: (kv[0] == "Unknown", -kv[1][1]))
    known = [name for name in countries if name != "Unknown"]

    week_ago = time.strftime("%Y-%m-%d", time.localtime(time.time() - 6 * 86400))
    span = day_list(min(first_day, week_ago) if rng == "all" else since, today)
    series = [(d, per_day.get(d, (0, 0))[0], per_day.get(d, (0, 0))[1]) for d in span]

    label = lambda p: "/ (home)" if p == "/" else p
    tiles = [("Page views", views), ("Visitors", visitors), ("Today", "%d views · %d visitors" % (t_views, t_visitors)),
             ("Countries", len(known)), ("Most visited page", label(pages[0][0]) if pages else "–")]
    tiles_html = "".join(
        '<div class="tile"><div class="label">%s</div><div class="value%s">%s</div></div>'
        % (esc(label), " small" if isinstance(val, str) else "", esc(val)) for label, val in tiles)
    ranges_html = "".join('<a href="?range=%s"%s>%s</a>' % (k, ' class="on"' if k == rng else "", esc(v))
                          for k, v in RANGES)

    panels = [
        ("wide", "Views per day", chart(series)),
        ("", "Most visited pages", table(["Page", "#Views", "#Visitors"],
                                         [[esc(label(p)), n, u] for p, n, u in pages], top=True, bar_col=1)),
        ("", "Countries", table(["Country", "#Visitors", "#Views"],
                                [[esc(name), vu[1], vu[0]] for name, vu in country_rows[:25]], bar_col=1)),
        ("", "Where visitors came from", table(["Site", "#Views"],
                                               [[esc(r or "Direct (typed, bookmark, email…)"), n] for r, n in referrers],
                                               bar_col=1)),
        ("", "Regions (browser time zone)", table(["Time zone", "#Visitors"],
                                                  [[esc(z), vu[1]] for z, vu in sorted(
                                                      zones.items(), key=lambda kv: (kv[0] == "Unknown", -kv[1][1]))[:15]],
                                                  bar_col=1)),
        ("", "Downloads &amp; outbound clicks", table(["Link", "#Clicks"], [[esc(t), n] for t, n in clicks], bar_col=1)),
        ("", "Devices, browsers, systems", "".join(
            table([label, "#Visitors"], [[esc(k), n] for k, n in tech[col]], bar_col=1)
            for col, label in (("device", "Device"), ("browser", "Browser"), ("os", "OS")))),
        ("wide", "Latest 50 visits", table(["When", "Page", "Location", "From", "Device"], [
            [time.strftime("%b %d, %H:%M", time.localtime(ts)), esc(p), esc(place(tz)),
             esc(r if r and r not in OWN_HOSTS else ("(this site)" if r else "direct")), esc("%s · %s" % (d, b))]
            for ts, p, tz, r, d, b in recent])),
    ]
    panels_html = "".join('<section class="panel %s"><h2>%s</h2>%s</section>' % (cls, title, content)
                          for cls, title, content in panels)

    body = """<div class="wrap">
<header>
  <div><h1>Site stats</h1><div class="muted">home.cc.umanitoba.ca/~opumni · times in Winnipeg</div></div>
  <nav class="ranges">%s</nav>
  <form method="post"><input type="hidden" name="action" value="logout"><button class="ghost">Log out</button></form>
</header>
<div class="tiles">%s</div>
<div class="panels">%s</div>
<footer class="muted">Visitors are counted once per day (no cookies, no IPs stored), so a person who comes back on
three days counts three times. Locations come from the visitor's time zone. %d hits stored since %s.
This browser is excluded from the counts while you use the dashboard.</footer>
</div>
<script>try { localStorage.setItem('opumni-notrack', '1'); } catch (e) {}</script>""" % (
        ranges_html, tiles_html, panels_html, total_rows, esc(first_day))
    return page("Site stats", body)


def main():
    if sys.argv[1:] == ["--set-password"]:
        return set_password()
    try:
        secret = read_secret()
    except OSError as e:
        return respond(error_page(e))

    logged_in = session_ok(read_cookie(COOKIE), secret)

    if os.environ.get("REQUEST_METHOD") == "POST":
        length = min(int(os.environ.get("CONTENT_LENGTH") or 0), 4096)
        form = parse_qs(sys.stdin.buffer.read(length).decode("utf-8", "replace"))
        action = form.get("action", [""])[0]
        back = '<meta http-equiv="refresh" content="0; url=stats.py"><p><a href="stats.py">Continue</a></p>'
        if action == "logout":
            return respond(page("Logged out", back), cookie="")
        if action == "login":
            if password_ok(form.get("password", [""])[0]):
                return respond(page("Logged in", back), cookie=make_session(secret))
            time.sleep(2)  # slows down password guessing
            return respond(login_page("Wrong password."))

    if not logged_in:
        return respond(login_page())
    rng = parse_qs(os.environ.get("QUERY_STRING", "")).get("range", ["30"])[0]
    return respond(dashboard(rng))


if __name__ == "__main__":
    main()
