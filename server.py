#!/usr/bin/env python3
"""
Reparado – Backend (Python-Stdlib, keine Fremd-Pakete).
Aufgabe: echte, geteilte Datenhaltung pro Werkstatt (Mandant) + Login + Mailversand.

Architektur (wie Agenten-Büro): Caddy (HTTPS) -> dieser Dienst (127.0.0.1:8790) -> SQLite.
Alles Stdlib -> laeuft auf jedem Hetzner-Server ohne pip.

Endpunkte (JSON):
  GET  /api/health                      -> {ok:true}
  POST /api/auth/login {email,password} -> {token, workshopId, name, role}
  GET  /api/state          (Bearer)     -> {value: <app_data-blob>|null, updated_at}
  POST /api/state {value}  (Bearer)     -> {ok:true}
  POST /api/mail/send {to,subject,body,html?} (Bearer) -> {sent:bool, note}
  POST /api/admin/provision (X-Admin-Key) {workshopName,email,password,userName}
                                        -> {workshopId, userId}   (Werkstatt+Login anlegen)

Konfiguration: config.py (nicht im oeffentlichen Repo!). Fehlt sie, gelten lokale Defaults.
"""
import json, os, sqlite3, hmac, hashlib, base64, time, smtplib, ssl, threading
from email.message import EmailMessage
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

# ---------- Konfiguration ----------
try:
    import config as CFG            # eigene config.py auf dem Server
except Exception:
    class CFG:                      # lokale Defaults (Entwicklung/Test)
        SECRET_KEY = "dev-secret-change-me"
        ADMIN_KEY = "dev-admin-change-me"
        DB_PATH = os.path.join(os.path.dirname(__file__), "reparado.db")
        PORT = 8790
        CORS_ORIGIN = "*"           # produktiv: exakte App-URL eintragen
        TOKEN_TTL_DAYS = 30
        SMTP_HOST = ""              # leer -> Mail wird nur protokolliert (nicht gesendet)
        SMTP_PORT = 587
        SMTP_USER = ""
        SMTP_PASS = ""
        MAIL_FROM = "Reparado <noreply@example.com>"

def _cfg(name, default=None):
    return getattr(CFG, name, default)

DB_PATH = _cfg("DB_PATH", os.path.join(os.path.dirname(__file__), "reparado.db"))
SECRET = str(_cfg("SECRET_KEY", "dev-secret")).encode()
_lock = threading.Lock()

# ---------- Datenbank ----------
def db():
    c = sqlite3.connect(DB_PATH, timeout=10)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    return c

def init_db():
    with db() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS workshops(
          id TEXT PRIMARY KEY, name TEXT, created TEXT);
        CREATE TABLE IF NOT EXISTS users(
          id TEXT PRIMARY KEY, workshop_id TEXT, email TEXT UNIQUE,
          pw_hash TEXT, pw_salt TEXT, role TEXT, name TEXT, created TEXT);
        CREATE TABLE IF NOT EXISTS app_data(
          workshop_id TEXT, key TEXT, value TEXT, updated_at TEXT,
          PRIMARY KEY(workshop_id, key));
        CREATE TABLE IF NOT EXISTS mail_log(
          id INTEGER PRIMARY KEY AUTOINCREMENT, workshop_id TEXT, ts TEXT,
          recipient TEXT, subject TEXT, sent INTEGER, note TEXT);
        CREATE TABLE IF NOT EXISTS sign_sessions(
          token TEXT PRIMARY KEY, workshop_id TEXT, data TEXT,
          signature TEXT, consents TEXT, signed INTEGER DEFAULT 0,
          created REAL, expires REAL);
        CREATE TABLE IF NOT EXISTS intake_sessions(
          token TEXT PRIMARY KEY, workshop_id TEXT, herkunft TEXT,
          workshop_name TEXT, workshop_tel TEXT, data TEXT,
          submitted INTEGER DEFAULT 0, consumed INTEGER DEFAULT 0,
          created REAL, expires REAL);
        CREATE TABLE IF NOT EXISTS portal_sessions(
          token TEXT PRIMARY KEY, workshop_id TEXT, order_id TEXT,
          data TEXT, created REAL, updated REAL);
        CREATE TABLE IF NOT EXISTS portal_replies(
          id INTEGER PRIMARY KEY AUTOINCREMENT, token TEXT, workshop_id TEXT,
          order_id TEXT, text TEXT, at REAL, consumed INTEGER DEFAULT 0);
        CREATE UNIQUE INDEX IF NOT EXISTS ux_portal_ws_order ON portal_sessions(workshop_id, order_id);
        CREATE TABLE IF NOT EXISTS sync_items(
          workshop_id TEXT, coll TEXT, id TEXT, data TEXT,
          updated_at REAL, deleted INTEGER DEFAULT 0,
          PRIMARY KEY(workshop_id, coll, id));
        CREATE INDEX IF NOT EXISTS ix_sync_ws_upd ON sync_items(workshop_id, updated_at);
        CREATE TABLE IF NOT EXISTS activity_log(
          id INTEGER PRIMARY KEY AUTOINCREMENT, workshop_id TEXT, order_id TEXT,
          entry_id TEXT, user_id TEXT, user_name TEXT, action TEXT, detail TEXT, at TEXT);
        CREATE UNIQUE INDEX IF NOT EXISTS ux_activity_entry ON activity_log(workshop_id, entry_id);
        """)

# ---------- Passwort & Token ----------
def hash_pw(pw, salt=None):
    if salt is None:
        salt = base64.b64encode(os.urandom(16)).decode()
    h = hashlib.pbkdf2_hmac("sha256", pw.encode(), salt.encode(), 120000)
    return base64.b64encode(h).decode(), salt

def check_pw(pw, pw_hash, salt):
    h, _ = hash_pw(pw, salt)
    return hmac.compare_digest(h, pw_hash)

def _b64u(b):  return base64.urlsafe_b64encode(b).decode().rstrip("=")
def _b64ud(s): return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))

def make_token(user_id, workshop_id):
    payload = {"uid": user_id, "wid": workshop_id,
               "exp": int(time.time()) + int(_cfg("TOKEN_TTL_DAYS", 30)) * 86400}
    body = _b64u(json.dumps(payload, separators=(",", ":")).encode())
    sig = _b64u(hmac.new(SECRET, body.encode(), hashlib.sha256).digest())
    return body + "." + sig

def verify_token(token):
    try:
        body, sig = token.split(".")
        exp_sig = _b64u(hmac.new(SECRET, body.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(sig, exp_sig):
            return None
        payload = json.loads(_b64ud(body))
        if payload.get("exp", 0) < time.time():
            return None
        return payload
    except Exception:
        return None

def make_reset_token(user_id):
    payload = {"uid": user_id, "typ": "reset", "exp": int(time.time()) + 3600}  # 1 Stunde
    body = _b64u(json.dumps(payload, separators=(",", ":")).encode())
    sig = _b64u(hmac.new(SECRET, body.encode(), hashlib.sha256).digest())
    return body + "." + sig

def verify_reset_token(token):
    p = verify_token(token)
    if not p or p.get("typ") != "reset":
        return None
    return p

def uid(prefix="id"):
    return prefix + "_" + base64.b32encode(os.urandom(8)).decode().rstrip("=").lower()

# ---------- Mail ----------
def send_mail(workshop_id, to, subject, body, html=None):
    host = _cfg("SMTP_HOST", "")
    ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    if not host:
        with db() as c:
            c.execute("INSERT INTO mail_log(workshop_id,ts,recipient,subject,sent,note) VALUES(?,?,?,?,?,?)",
                      (workshop_id, ts, to, subject, 0, "SMTP nicht konfiguriert – nur protokolliert"))
        return False, "SMTP nicht konfiguriert – Nachricht protokolliert, nicht gesendet"
    msg = EmailMessage()
    msg["From"] = _cfg("MAIL_FROM", "Reparado <noreply@example.com>")
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body or "")
    if html:
        msg.add_alternative(html, subtype="html")
    try:
        ctx = ssl.create_default_context()
        with smtplib.SMTP(host, int(_cfg("SMTP_PORT", 587)), timeout=20) as s:
            s.starttls(context=ctx)
            if _cfg("SMTP_USER"):
                s.login(_cfg("SMTP_USER"), _cfg("SMTP_PASS"))
            s.send_message(msg)
        note = "gesendet"
        ok = True
    except Exception as e:
        note = "Fehler: " + str(e)
        ok = False
    with db() as c:
        c.execute("INSERT INTO mail_log(workshop_id,ts,recipient,subject,sent,note) VALUES(?,?,?,?,?,?)",
                  (workshop_id, ts, to, subject, 1 if ok else 0, note))
    return ok, note

# ---------- KI-Formulierungshilfe (optional, nur mit Schlüssel) ----------
def _ai_rewrite(key, raw, kind):
    import urllib.request
    sys_prompt = ("Du bist Assistenz einer Handy-/Elektronik-Reparaturwerkstatt. Formuliere den folgenden internen "
                  "Stichpunkt-Text zu einer professionellen, freundlichen und klaren Kundennachricht auf Deutsch um. "
                  "WICHTIG: Erfinde KEINE neuen Fakten, Preise, Termine oder technischen Zusagen. Verbessere nur "
                  "Formulierung, Rechtschreibung, Verständlichkeit und Ton. Gib NUR den fertigen Nachrichtentext "
                  "zurück, ohne Erklärungen oder Anführungszeichen.")
    payload = {"model": _cfg("LLM_MODEL", "claude-haiku-4-5"), "max_tokens": 600,
               "system": sys_prompt, "messages": [{"role": "user", "content": raw}]}
    req = urllib.request.Request("https://api.anthropic.com/v1/messages",
                                 data=json.dumps(payload).encode(),
                                 headers={"content-type": "application/json", "x-api-key": key,
                                          "anthropic-version": "2023-06-01"})
    with urllib.request.urlopen(req, timeout=30) as r:
        res = json.loads(r.read().decode())
    parts = res.get("content") or []
    return "".join(b.get("text", "") for b in parts if b.get("type") == "text").strip() or raw

# ---------- Geo (Adress-/Straßen-Autovervollständigung via OpenPLZ) ----------
_GEO_CACHE = {}
def _geo_fetch(url):
    import urllib.request
    now = time.time()
    hit = _GEO_CACHE.get(url)
    if hit and hit[0] > now:
        return hit[1]
    req = urllib.request.Request(url, headers={"User-Agent": "Velqio/1.0 (Werkstatt-Software)", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=8) as r:
        data = json.loads(r.read().decode())
    if len(_GEO_CACHE) > 2000:
        _GEO_CACHE.clear()
    _GEO_CACHE[url] = (now + 86400, data)  # 1 Tag Cache
    return data

# ---------- HTTP ----------
class H(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", _cfg("CORS_ORIGIN", "*"))
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, X-Admin-Key")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")

    def _send(self, code, obj):
        data = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self._cors()
        self.end_headers()
        self.wfile.write(data)

    def _body(self):
        n = int(self.headers.get("Content-Length", 0) or 0)
        if not n:
            return {}
        try:
            return json.loads(self.rfile.read(n).decode() or "{}")
        except Exception:
            return {}

    def _auth(self):
        h = self.headers.get("Authorization", "")
        if h.startswith("Bearer "):
            return verify_token(h[7:])
        return None

    def log_message(self, *a):  # ruhig
        pass

    def do_OPTIONS(self):
        self.send_response(204); self._cors(); self.end_headers()

    def do_GET(self):
        if self.path == "/api/health":
            return self._send(200, {"ok": True, "service": "reparado"})
        if self.path.startswith("/api/geo/plz"):
            q = parse_qs(urlparse(self.path).query); plz = (q.get("plz") or [""])[0]
            if not (plz.isdigit() and len(plz) == 5):
                return self._send(400, {"error": "ungueltige PLZ"})
            try:
                data = _geo_fetch("https://openplzapi.org/de/Localities?postalCode=" + plz)
                seen = set(); cities = []
                for x in (data or []):
                    n = x.get("name")
                    if n and n not in seen:
                        seen.add(n); cities.append(n)
                return self._send(200, {"ok": True, "cities": cities})
            except Exception:
                return self._send(200, {"ok": True, "cities": []})
        if self.path.startswith("/api/geo/streets"):
            from urllib.parse import quote
            q = parse_qs(urlparse(self.path).query)
            plz = (q.get("plz") or [""])[0]; name = (q.get("q") or q.get("name") or [""])[0].strip()
            if not (plz.isdigit() and len(plz) == 5) or len(name) < 2:
                return self._send(200, {"ok": True, "streets": []})
            try:
                data = _geo_fetch("https://openplzapi.org/de/Streets?postalCode=" + plz + "&name=" + quote(name))
                seen = set(); sts = []
                for x in (data or []):
                    n = x.get("name")
                    if n and n not in seen:
                        seen.add(n); sts.append(n)
                return self._send(200, {"ok": True, "streets": sts[:12]})
            except Exception:
                return self._send(200, {"ok": True, "streets": []})
        if self.path == "/api/state":
            p = self._auth()
            if not p:
                return self._send(401, {"error": "unauthorized"})
            with db() as c:
                row = c.execute("SELECT value, updated_at FROM app_data WHERE workshop_id=? AND key='reparado_v1'",
                                (p["wid"],)).fetchone()
            if row:
                return self._send(200, {"value": json.loads(row["value"]), "updated_at": row["updated_at"]})
            return self._send(200, {"value": None})
        if self.path.startswith("/api/sync/pull"):
            # Einzeldatensatz-Sync: geänderte Aufträge/Kunden/… seit <since> abholen (Mehrplatz + Live-Refresh)
            p = self._auth()
            if not p:
                return self._send(401, {"error": "unauthorized"})
            q = parse_qs(urlparse(self.path).query)
            try: since = float((q.get("since") or ["0"])[0])
            except Exception: since = 0.0
            wait = (q.get("wait") or ["0"])[0] == "1"
            def _fetch():
                with db() as c:
                    rr = c.execute("SELECT coll,id,data,updated_at,deleted FROM sync_items WHERE workshop_id=? AND updated_at>? ORDER BY updated_at ASC",
                                   (p["wid"], since)).fetchall()
                out = []
                for r in rr:
                    out.append({"coll": r["coll"], "id": r["id"],
                                "data": (json.loads(r["data"]) if r["data"] else None),
                                "updated_at": r["updated_at"], "deleted": bool(r["deleted"])})
                return out
            items = _fetch()
            if wait and not items:
                # Long-Polling: bis ~25s auf eine Änderung warten -> nahezu Echtzeit ohne WebSocket
                deadline = time.time() + 25
                while not items and time.time() < deadline:
                    time.sleep(0.7)
                    items = _fetch()
            return self._send(200, {"ok": True, "now": time.time(), "items": items})
        if self.path.startswith("/api/sign/get"):
            # Öffentlich (Kunde ist nicht eingeloggt): Auftrags-Snapshot per Einmal-Token abrufen.
            q = parse_qs(urlparse(self.path).query)
            tok = (q.get("t") or [""])[0]
            now = time.time()
            with db() as c:
                row = c.execute("SELECT data,signature,consents,signed,expires FROM sign_sessions WHERE token=?", (tok,)).fetchone()
            if not row or (row["expires"] or 0) < now:
                return self._send(404, {"error": "Signatur-Link ungültig oder abgelaufen"})
            return self._send(200, {"ok": True, "data": json.loads(row["data"]), "signed": bool(row["signed"]),
                                    "signature": row["signature"] or "",
                                    "consents": json.loads(row["consents"]) if row["consents"] else None})
        if self.path.startswith("/api/intake/get"):
            # Öffentlich: Kunde öffnet Vorab-Auftragsformular per Token.
            q = parse_qs(urlparse(self.path).query)
            tok = (q.get("t") or [""])[0]
            now = time.time()
            with db() as c:
                row = c.execute("SELECT workshop_name,workshop_tel,submitted,expires FROM intake_sessions WHERE token=?", (tok,)).fetchone()
            if not row or (row["expires"] or 0) < now:
                return self._send(404, {"error": "Formular-Link ungültig oder abgelaufen"})
            return self._send(200, {"ok": True, "workshop": row["workshop_name"] or "Werkstatt",
                                    "tel": row["workshop_tel"] or "", "submitted": bool(row["submitted"])})
        if self.path == "/api/intake/pending":
            # Werkstatt holt neue, noch nicht übernommene Vorab-Anfragen ab.
            p = self._auth()
            if not p:
                return self._send(401, {"error": "unauthorized"})
            with db() as c:
                rows = c.execute("SELECT token,herkunft,data,created FROM intake_sessions WHERE workshop_id=? AND submitted=1 AND consumed=0 ORDER BY created DESC",
                                 (p["wid"],)).fetchall()
            out = [{"token": r["token"], "herkunft": r["herkunft"] or "online",
                    "data": json.loads(r["data"]) if r["data"] else None, "created": r["created"]} for r in rows]
            return self._send(200, {"ok": True, "items": out})
        if self.path.startswith("/api/portal/get"):
            # Öffentlich: Kunde ruft Auftrags-Portal per Token ab.
            q = parse_qs(urlparse(self.path).query)
            tok = (q.get("t") or [""])[0]
            with db() as c:
                row = c.execute("SELECT data FROM portal_sessions WHERE token=?", (tok,)).fetchone()
            if not row:
                return self._send(404, {"error": "Portal nicht gefunden"})
            return self._send(200, {"ok": True, "data": json.loads(row["data"]) if row["data"] else None})
        if self.path == "/api/portal/replies":
            p = self._auth()
            if not p:
                return self._send(401, {"error": "unauthorized"})
            with db() as c:
                rows = c.execute("SELECT id,token,order_id,text,at FROM portal_replies WHERE workshop_id=? AND consumed=0 ORDER BY at ASC",
                                 (p["wid"],)).fetchall()
            return self._send(200, {"ok": True, "items": [{"id": r["id"], "token": r["token"], "orderId": r["order_id"],
                                                           "text": r["text"], "at": r["at"]} for r in rows]})
        return self._send(404, {"error": "not found"})

    def do_POST(self):
        body = self._body()

        if self.path == "/api/auth/login":
            email = (body.get("email") or "").strip().lower()
            pw = body.get("password") or ""
            with db() as c:
                u = c.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
            if not u or not check_pw(pw, u["pw_hash"], u["pw_salt"]):
                return self._send(401, {"error": "E-Mail oder Passwort falsch"})
            token = make_token(u["id"], u["workshop_id"])
            return self._send(200, {"token": token, "workshopId": u["workshop_id"],
                                    "name": u["name"], "role": u["role"]})

        if self.path == "/api/auth/signup":
            # Öffentliche Selbst-Registrierung: Werkstatt legt ihr eigenes Konto an.
            wname = (body.get("workshopName") or "").strip()
            email = (body.get("email") or "").strip().lower()
            pw = body.get("password") or ""
            uname = (body.get("userName") or "Inhaber").strip() or "Inhaber"
            if not wname:
                return self._send(400, {"error": "Bitte einen Werkstatt-Namen angeben"})
            if "@" not in email or "." not in email.split("@")[-1]:
                return self._send(400, {"error": "Bitte eine gültige E-Mail angeben"})
            if len(pw) < 6:
                return self._send(400, {"error": "Passwort mind. 6 Zeichen"})
            now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            wid = uid("ws"); usr = uid("u"); ph, salt = hash_pw(pw)
            try:
                with _lock, db() as c:
                    c.execute("INSERT INTO workshops(id,name,created) VALUES(?,?,?)", (wid, wname, now))
                    c.execute("INSERT INTO users(id,workshop_id,email,pw_hash,pw_salt,role,name,created) VALUES(?,?,?,?,?,?,?,?)",
                              (usr, wid, email, ph, salt, "inhaber", uname, now))
            except sqlite3.IntegrityError:
                return self._send(409, {"error": "Diese E-Mail ist bereits registriert"})
            token = make_token(usr, wid)
            return self._send(200, {"token": token, "workshopId": wid, "name": uname, "role": "inhaber"})

        if self.path == "/api/auth/reset":
            # Passwort-Reset anfordern: schickt Link per E-Mail. Antwort immer generisch (kein Konto-Leak).
            email = (body.get("email") or "").strip().lower()
            if email:
                with db() as c:
                    u = c.execute("SELECT id,workshop_id FROM users WHERE email=?", (email,)).fetchone()
                if u:
                    tok = make_reset_token(u["id"])
                    base = str(_cfg("APP_BASE_URL", "https://velqio.de")).rstrip("/")
                    link = base + "/app.html?reset=" + tok
                    txt = ("Hallo,\n\ndu hast das Zuruecksetzen deines Velqio-Passworts angefordert.\n"
                           "Ueber diesen Link kannst du innerhalb von 1 Stunde ein neues Passwort vergeben:\n\n"
                           + link + "\n\nWenn du das nicht warst, ignoriere diese E-Mail einfach.\n\nDein Velqio-Team")
                    try:
                        send_mail(u["workshop_id"], email, "Velqio - Passwort zuruecksetzen", txt)
                    except Exception:
                        pass
            return self._send(200, {"ok": True})

        if self.path == "/api/auth/reset/confirm":
            tok = body.get("token") or ""
            pw = body.get("password") or ""
            if len(pw) < 6:
                return self._send(400, {"error": "Passwort mind. 6 Zeichen"})
            p = verify_reset_token(tok)
            if not p:
                return self._send(400, {"error": "Link ungueltig oder abgelaufen. Bitte neu anfordern."})
            ph, salt = hash_pw(pw)
            with _lock, db() as c:
                cur = c.execute("UPDATE users SET pw_hash=?, pw_salt=? WHERE id=?", (ph, salt, p["uid"]))
                if cur.rowcount == 0:
                    return self._send(400, {"error": "Konto nicht gefunden"})
            return self._send(200, {"ok": True})

        if self.path == "/api/state":
            p = self._auth()
            if not p:
                return self._send(401, {"error": "unauthorized"})
            val = body.get("value")
            if val is None:
                return self._send(400, {"error": "value fehlt"})
            ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            with _lock, db() as c:
                c.execute("""INSERT INTO app_data(workshop_id,key,value,updated_at) VALUES(?,?,?,?)
                             ON CONFLICT(workshop_id,key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at""",
                          (p["wid"], "reparado_v1", json.dumps(val), ts))
            return self._send(200, {"ok": True, "updated_at": ts})

        if self.path == "/api/sync/push":
            # Einzeldatensatz-Sync: Aufträge/Kunden/… einzeln upserten (kein Ganz-Paket-Überschreiben mehr)
            p = self._auth()
            if not p:
                return self._send(401, {"error": "unauthorized"})
            items = body.get("items") or []
            if not isinstance(items, list):
                return self._send(400, {"error": "items fehlt"})
            saved = []
            base = time.time()
            with _lock, db() as c:
                for i, it in enumerate(items[:3000]):
                    coll = str(it.get("coll") or "")
                    rid = str(it.get("id") or "")
                    if not coll or not rid:
                        continue
                    deleted = 1 if it.get("deleted") else 0
                    data = it.get("data")
                    ua = base + i * 1e-6
                    # Aktivitätsprotokoll append-only zusammenführen (Aufträge)
                    if coll == "ord" and isinstance(data, dict):
                        prev_act = []
                        prow = c.execute("SELECT data FROM sync_items WHERE workshop_id=? AND coll='ord' AND id=?",
                                         (p["wid"], rid)).fetchone()
                        if prow and prow["data"]:
                            try: prev_act = (json.loads(prow["data"]) or {}).get("activity") or []
                            except Exception: prev_act = []
                        new_act = data.get("activity") if isinstance(data.get("activity"), list) else []
                        seen = set(); merged = []
                        for e in (list(prev_act) + list(new_act)):
                            if not isinstance(e, dict): continue
                            eid = e.get("id") or (str(e.get("at","")) + "|" + str(e.get("action","")))
                            if eid in seen: continue
                            seen.add(eid); merged.append(e)
                        data["activity"] = merged
                        for e in new_act:
                            if not isinstance(e, dict): continue
                            eid = str(e.get("id") or "")
                            if not eid: continue
                            try:
                                c.execute("""INSERT OR IGNORE INTO activity_log(workshop_id,order_id,entry_id,user_id,user_name,action,detail,at)
                                             VALUES(?,?,?,?,?,?,?,?)""",
                                          (p["wid"], rid, eid, str(e.get("uid","")), str(e.get("user","")),
                                           str(e.get("action","")), str(e.get("detail","")), str(e.get("at",""))))
                            except Exception: pass
                    c.execute("""INSERT INTO sync_items(workshop_id,coll,id,data,updated_at,deleted) VALUES(?,?,?,?,?,?)
                                 ON CONFLICT(workshop_id,coll,id) DO UPDATE SET data=excluded.data, updated_at=excluded.updated_at, deleted=excluded.deleted""",
                              (p["wid"], coll, rid, (json.dumps(data) if data is not None else None), ua, deleted))
                    saved.append({"coll": coll, "id": rid, "updated_at": ua})
            return self._send(200, {"ok": True, "now": time.time(), "saved": saved})

        if self.path == "/api/seq/reserve":
            # Atomare, kollisionsfreie Nummernvergabe pro Werkstatt (hi/lo-Block) -> keine Doppel-Auftragsnummern
            p = self._auth()
            if not p:
                return self._send(401, {"error": "unauthorized"})
            kind = str(body.get("kind") or "order")
            if kind not in ("order", "quote"):
                kind = "order"
            try: count = int(body.get("count") or 5)
            except Exception: count = 5
            count = max(1, min(count, 100))
            try: mn = int(body.get("min") or 0)
            except Exception: mn = 0
            key = "seq_" + kind
            with _lock, db() as c:
                row = c.execute("SELECT value FROM app_data WHERE workshop_id=? AND key=?", (p["wid"], key)).fetchone()
                cur = 0
                if row and row["value"]:
                    try: cur = int(json.loads(row["value"]))
                    except Exception: cur = 0
                base = max(cur, mn)
                start = base + 1
                newv = base + count
                ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                c.execute("""INSERT INTO app_data(workshop_id,key,value,updated_at) VALUES(?,?,?,?)
                             ON CONFLICT(workshop_id,key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at""",
                          (p["wid"], key, json.dumps(newv), ts))
            return self._send(200, {"ok": True, "start": start, "end": newv, "count": count})

        if self.path == "/api/sign/create":
            # Werkstatt (eingeloggt) legt eine Signatur-Session an -> Token für QR-Link.
            p = self._auth()
            if not p:
                return self._send(401, {"error": "unauthorized"})
            data = body.get("data")
            if data is None:
                return self._send(400, {"error": "data fehlt"})
            tok = uid("s")
            now = time.time(); exp = now + 45 * 60
            with _lock, db() as c:
                c.execute("DELETE FROM sign_sessions WHERE expires<?", (now,))
                c.execute("INSERT INTO sign_sessions(token,workshop_id,data,signature,consents,signed,created,expires) VALUES(?,?,?,?,?,?,?,?)",
                          (tok, p["wid"], json.dumps(data), "", "", 0, now, exp))
            return self._send(200, {"token": tok})

        if self.path == "/api/sign/submit":
            # Öffentlich: Kunde reicht Unterschrift + Einwilligungen zum Token ein.
            tok = body.get("t") or ""
            sig = body.get("signature") or ""
            consents = body.get("consents")
            if not tok or not sig:
                return self._send(400, {"error": "Token/Unterschrift fehlt"})
            if len(sig) > 500000:
                return self._send(413, {"error": "Unterschrift zu groß"})
            now = time.time()
            with _lock, db() as c:
                row = c.execute("SELECT expires,signed FROM sign_sessions WHERE token=?", (tok,)).fetchone()
                if not row or (row["expires"] or 0) < now:
                    return self._send(404, {"error": "Signatur-Link ungültig oder abgelaufen"})
                c.execute("UPDATE sign_sessions SET signature=?,consents=?,signed=1 WHERE token=?",
                          (sig, json.dumps(consents), tok))
            return self._send(200, {"ok": True})

        if self.path == "/api/intake/create":
            # Werkstatt erzeugt Vorab-Auftrags-Link (mit Herkunft Telefon/E-Mail/Online).
            p = self._auth()
            if not p:
                return self._send(401, {"error": "unauthorized"})
            herkunft = (body.get("herkunft") or "online").strip()
            wname = (body.get("workshopName") or "Werkstatt").strip()
            wtel = (body.get("workshopTel") or "").strip()
            tok = uid("i")
            now = time.time(); exp = now + 7 * 86400
            with _lock, db() as c:
                c.execute("DELETE FROM intake_sessions WHERE expires<?", (now,))
                c.execute("INSERT INTO intake_sessions(token,workshop_id,herkunft,workshop_name,workshop_tel,data,submitted,consumed,created,expires) VALUES(?,?,?,?,?,?,?,?,?,?)",
                          (tok, p["wid"], herkunft, wname, wtel, "", 0, 0, now, exp))
            return self._send(200, {"token": tok})

        if self.path == "/api/intake/submit":
            # Öffentlich: Kunde reicht seine Vorab-Daten ein.
            tok = body.get("t") or ""
            data = body.get("data")
            if not tok or data is None:
                return self._send(400, {"error": "Token/Daten fehlen"})
            now = time.time()
            with _lock, db() as c:
                row = c.execute("SELECT expires,submitted FROM intake_sessions WHERE token=?", (tok,)).fetchone()
                if not row or (row["expires"] or 0) < now:
                    return self._send(404, {"error": "Formular-Link ungültig oder abgelaufen"})
                c.execute("UPDATE intake_sessions SET data=?,submitted=1 WHERE token=?", (json.dumps(data), tok))
            return self._send(200, {"ok": True})

        if self.path == "/api/intake/consume":
            p = self._auth()
            if not p:
                return self._send(401, {"error": "unauthorized"})
            toks = body.get("tokens") or []
            if toks:
                with _lock, db() as c:
                    for t in toks:
                        c.execute("UPDATE intake_sessions SET consumed=1 WHERE token=? AND workshop_id=?", (t, p["wid"]))
            return self._send(200, {"ok": True})

        if self.path == "/api/portal/sync":
            # Werkstatt veröffentlicht/aktualisiert das Kundenportal für einen Auftrag. Gibt (Einmal-)Token zurück.
            p = self._auth()
            if not p:
                return self._send(401, {"error": "unauthorized"})
            oid = (body.get("orderId") or "").strip()
            data = body.get("data")
            if not oid or data is None:
                return self._send(400, {"error": "orderId/data fehlt"})
            now = time.time()
            with _lock, db() as c:
                row = c.execute("SELECT token FROM portal_sessions WHERE workshop_id=? AND order_id=?", (p["wid"], oid)).fetchone()
                if row:
                    tok = row["token"]
                    c.execute("UPDATE portal_sessions SET data=?,updated=? WHERE token=?", (json.dumps(data), now, tok))
                else:
                    tok = uid("p")
                    c.execute("INSERT INTO portal_sessions(token,workshop_id,order_id,data,created,updated) VALUES(?,?,?,?,?,?)",
                              (tok, p["wid"], oid, json.dumps(data), now, now))
            return self._send(200, {"token": tok})

        if self.path == "/api/portal/reply":
            # Öffentlich: Kunde antwortet über sein Portal.
            tok = body.get("t") or ""
            text = (body.get("text") or "").strip()
            if not tok or not text:
                return self._send(400, {"error": "Token/Text fehlt"})
            if len(text) > 4000:
                text = text[:4000]
            with _lock, db() as c:
                row = c.execute("SELECT workshop_id,order_id FROM portal_sessions WHERE token=?", (tok,)).fetchone()
                if not row:
                    return self._send(404, {"error": "Portal nicht gefunden"})
                c.execute("INSERT INTO portal_replies(token,workshop_id,order_id,text,at,consumed) VALUES(?,?,?,?,?,0)",
                          (tok, row["workshop_id"], row["order_id"], text, time.time()))
            return self._send(200, {"ok": True})

        if self.path == "/api/portal/replies/consume":
            p = self._auth()
            if not p:
                return self._send(401, {"error": "unauthorized"})
            ids = body.get("ids") or []
            if ids:
                with _lock, db() as c:
                    for i in ids:
                        c.execute("UPDATE portal_replies SET consumed=1 WHERE id=? AND workshop_id=?", (i, p["wid"]))
            return self._send(200, {"ok": True})

        if self.path == "/api/ai/rewrite":
            # KI-Formulierungshilfe. Nur aktiv, wenn ein LLM-Schlüssel konfiguriert ist.
            p = self._auth()
            if not p:
                return self._send(401, {"error": "unauthorized"})
            key = _cfg("ANTHROPIC_API_KEY", "") or _cfg("LLM_API_KEY", "")
            raw = (body.get("text") or "").strip()
            if not key:
                return self._send(200, {"enabled": False, "text": raw,
                                        "note": "KI-Formulierung ist noch nicht freigeschaltet (kein Schlüssel hinterlegt)."})
            try:
                out = _ai_rewrite(key, raw, body.get("kind") or "nachricht")
                return self._send(200, {"enabled": True, "text": out})
            except Exception as e:
                return self._send(200, {"enabled": True, "text": raw, "note": "KI nicht erreichbar: " + str(e)})

        if self.path == "/api/mail/send":
            p = self._auth()
            if not p:
                return self._send(401, {"error": "unauthorized"})
            to = body.get("to"); subj = body.get("subject", ""); text = body.get("body", "")
            if not to:
                return self._send(400, {"error": "Empfaenger fehlt"})
            ok, note = send_mail(p["wid"], to, subj, text, body.get("html"))
            return self._send(200, {"sent": ok, "note": note})

        if self.path == "/api/admin/provision":
            if self.headers.get("X-Admin-Key") != _cfg("ADMIN_KEY"):
                return self._send(403, {"error": "forbidden"})
            wname = body.get("workshopName") or "Werkstatt"
            email = (body.get("email") or "").strip().lower()
            pw = body.get("password") or ""
            uname = body.get("userName") or "Inhaber"
            if not email or not pw:
                return self._send(400, {"error": "email/password noetig"})
            now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            wid = uid("ws"); usr = uid("u"); ph, salt = hash_pw(pw)
            try:
                with _lock, db() as c:
                    c.execute("INSERT INTO workshops(id,name,created) VALUES(?,?,?)", (wid, wname, now))
                    c.execute("INSERT INTO users(id,workshop_id,email,pw_hash,pw_salt,role,name,created) VALUES(?,?,?,?,?,?,?,?)",
                              (usr, wid, email, ph, salt, "inhaber", uname, now))
            except sqlite3.IntegrityError:
                return self._send(409, {"error": "E-Mail bereits vergeben"})
            return self._send(200, {"workshopId": wid, "userId": usr})

        return self._send(404, {"error": "not found"})

def main():
    init_db()
    port = int(_cfg("PORT", 8790))
    srv = ThreadingHTTPServer(("127.0.0.1", port), H)
    print(f"Reparado-Backend laeuft auf 127.0.0.1:{port} (DB: {DB_PATH})")
    srv.serve_forever()

if __name__ == "__main__":
    main()
