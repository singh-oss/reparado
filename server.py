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
