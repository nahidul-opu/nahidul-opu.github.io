#!/usr/bin/python3
"""Records one anonymous page view or click sent by assets/main.js.

Saved per hit: time, page, referring site, browser / OS / device type, the
browser's time zone (used for the country) and a visitor id. The visitor id is
a hash of (secret that changes every day + IP + browser), so the same person
counts once per day and the IP address itself is never stored.

Data lives in ~/site-data/visits.sqlite, outside public_html, so it is not
reachable from the web. stats.py shows it.
"""
import hashlib
import json
import os
import re
import secrets
import sqlite3
import sys
import time
from urllib.parse import urlparse

os.environ["TZ"] = "America/Winnipeg"  # days in the dashboard follow Winnipeg time
time.tzset()

DATA_DIR = os.environ.get("SITE_DATA_DIR") or os.path.join(os.path.expanduser("~"), "site-data")
DB_PATH = os.path.join(DATA_DIR, "visits.sqlite")
SECRET_PATH = os.path.join(DATA_DIR, "secret.key")

SITE_ORIGIN = "https://home.cc.umanitoba.ca"
SITE_PREFIX = SITE_ORIGIN + "/~opumni/"
LOCAL_ORIGINS = {"http://localhost:8000", "http://127.0.0.1:8000"}  # local preview
BOTS = re.compile(r"bot|crawl|spider|slurp|preview|headless|lighthouse|python|curl|wget|"
                  r"java/|httpclient|okhttp|scrapy|monitor", re.I)
TZ_NAME = re.compile(r"^[A-Za-z0-9_+\-]+(/[A-Za-z0-9_+\-]+)*$")

SCHEMA = """
CREATE TABLE IF NOT EXISTS hits (
    id       INTEGER PRIMARY KEY,
    ts       INTEGER NOT NULL,  -- unix time
    day      TEXT    NOT NULL,  -- YYYY-MM-DD in Winnipeg time
    kind     TEXT    NOT NULL,  -- 'view' or 'click'
    page     TEXT    NOT NULL,  -- page path, e.g. /publications.html
    target   TEXT,              -- clicked link (kind = 'click')
    referrer TEXT,              -- referring site, '' if none
    tz       TEXT,              -- browser time zone, e.g. Asia/Dhaka
    browser  TEXT,
    os       TEXT,
    device   TEXT,
    visitor  TEXT    NOT NULL   -- daily-changing hash; cannot be turned back into an IP
);
CREATE INDEX IF NOT EXISTS hits_day ON hits (day);
"""


def read_secret():
    """Secret used for visitor hashes; created on first use."""
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


def browser_of(ua):
    for name, marker in (("Edge", "Edg"), ("Opera", "OPR/"), ("Samsung Internet", "SamsungBrowser"),
                         ("Firefox", "Firefox/"), ("Firefox", "FxiOS"), ("Chrome", "CriOS"),
                         ("Chrome", "Chrome/"), ("Safari", "Safari/")):
        if marker in ua:
            return name
    return "Other"


def os_of(ua):
    for name, markers in (("Windows", ("Windows",)), ("iOS", ("iPhone", "iPad", "iPod")),
                          ("Android", ("Android",)), ("ChromeOS", ("CrOS",)),
                          ("macOS", ("Macintosh", "Mac OS X")), ("Linux", ("Linux",))):
        if any(m in ua for m in markers):
            return name
    return "Other"


def device_of(ua):
    if "iPad" in ua or "Tablet" in ua or ("Android" in ua and "Mobile" not in ua):
        return "Tablet"
    if "Mobi" in ua or "iPhone" in ua:
        return "Mobile"
    return "Desktop"


def site_host(url):
    """Host of a URL without 'www.', or '' if it is not a web URL."""
    try:
        host = (urlparse(url).hostname or "").lower()
    except ValueError:
        return ""
    return host[4:] if host.startswith("www.") else host


def record():
    if os.environ.get("REQUEST_METHOD") != "POST":
        return
    origin = os.environ.get("HTTP_ORIGIN", "")
    referer = os.environ.get("HTTP_REFERER", "")
    if origin == SITE_ORIGIN:
        # home.cc.umanitoba.ca hosts many people's pages: only accept hits from ours.
        if referer and not referer.startswith(SITE_PREFIX):
            return
    elif origin and origin not in LOCAL_ORIGINS:
        return

    ua = os.environ.get("HTTP_USER_AGENT", "")
    if not ua or BOTS.search(ua):
        return

    length = min(int(os.environ.get("CONTENT_LENGTH") or 0), 4096)
    try:
        data = json.loads(sys.stdin.buffer.read(length).decode("utf-8", "replace") or "{}")
    except ValueError:
        return
    if not isinstance(data, dict):
        return

    kind = "click" if data.get("k") == "click" else "view"
    page = str(data.get("p") or "/")[:200]
    if not page.startswith("/"):
        page = "/" + page
    if page.endswith("/index.html"):
        page = page[:-len("index.html")]

    target = None
    if kind == "click":
        target = str(data.get("t") or "")[:300]
        if target.startswith(SITE_PREFIX):
            target = "/" + target[len(SITE_PREFIX):]
        if not target:
            return

    referrer = site_host(str(data.get("r") or "")) if kind == "view" else ""
    tz = str(data.get("tz") or "")[:64]
    if not TZ_NAME.match(tz):
        tz = ""

    now = int(time.time())
    day = time.strftime("%Y-%m-%d", time.localtime(now))
    secret = read_secret()
    # REMOTE_ADDR plus X-Forwarded-For identifies the client whether or not the
    # university's load balancer forwards the original IP. Only the hash is kept.
    who = "|".join((os.environ.get("REMOTE_ADDR", ""), os.environ.get("HTTP_X_FORWARDED_FOR", ""), ua))
    daily_salt = hashlib.sha256((secret + day).encode()).hexdigest()
    visitor = hashlib.sha256((daily_salt + who).encode()).hexdigest()[:16]

    con = sqlite3.connect(DB_PATH, timeout=10)
    try:
        con.executescript(SCHEMA)
        con.execute(
            "INSERT INTO hits (ts, day, kind, page, target, referrer, tz, browser, os, device, visitor)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (now, day, kind, page, target, referrer, tz, browser_of(ua), os_of(ua), device_of(ua), visitor))
        con.commit()
    finally:
        con.close()


if __name__ == "__main__":
    try:
        record()
    except Exception as e:  # never break the page; leave a note in the server error log
        print("hit.py: %r" % (e,), file=sys.stderr)
    sys.stdout.write("Status: 204 No Content\r\n\r\n")
