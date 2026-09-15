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
import urllib.request as _urlreq, urllib.parse as _urlparse, urllib.error as _urlerr, calendar as _cal

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

# ---------- Stripe / Abrechnung (nur Stdlib via Stripe-REST) ----------
def _iso(ts=None):
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ts if ts is not None else time.time()))
def _iso_epoch(s):
    try: return _cal.timegm(time.strptime(str(s), "%Y-%m-%dT%H:%M:%SZ"))
    except Exception: return 0
def _stripe(method, path, params=None):
    key = str(_cfg("STRIPE_SECRET_KEY", "") or "")
    if not key: raise RuntimeError("stripe_not_configured")
    data = _urlparse.urlencode(params, doseq=True).encode() if params is not None else None
    req = _urlreq.Request("https://api.stripe.com/v1/" + path, data=data, method=method)
    req.add_header("Authorization", "Bearer " + key)
    if data is not None: req.add_header("Content-Type", "application/x-www-form-urlencoded")
    try:
        with _urlreq.urlopen(req, timeout=25) as r:
            return json.loads(r.read().decode())
    except _urlerr.HTTPError as e:
        try: return json.loads(e.read().decode())
        except Exception: return {"error": {"message": "stripe_http_%s" % e.code}}
PLAN_PRICE = {"basic": "STRIPE_PRICE_BASIC", "pro": "STRIPE_PRICE_PRO", "ai": "STRIPE_PRICE_AI"}
def _price_for_plan(plan): return str(_cfg(PLAN_PRICE.get(plan, ""), "") or "")
def _plan_for_price(pid):
    for pl, cfgk in PLAN_PRICE.items():
        if pid and str(_cfg(cfgk, "") or "") == pid: return pl
    return ""
def _ws_get(wid):
    with db() as c:
        return c.execute("SELECT * FROM workshops WHERE id=?", (wid,)).fetchone()
def _ws_set(wid, **f):
    if not f: return
    cols = ",".join(k + "=?" for k in f); vals = list(f.values()) + [wid]
    with _lock, db() as c:
        c.execute("UPDATE workshops SET " + cols + " WHERE id=?", vals)
def _ws_by_customer(cust):
    if not cust: return None
    with db() as c:
        return c.execute("SELECT id FROM workshops WHERE stripe_customer=?", (cust,)).fetchone()
def billing_info(wid):
    r = _ws_get(wid); now = time.time()
    if not r: return {"plan": "trial", "status": "none", "locked": True, "trialEnd": "", "trialDaysLeft": 0, "currentPeriodEnd": ""}
    try: plan = r["plan"] or "trial"
    except Exception: plan = "trial"
    try: status = r["sub_status"] or "trial"
    except Exception: status = "trial"
    try: te = r["trial_end"] or ""
    except Exception: te = ""
    try: cpe = r["current_period_end"] or ""
    except Exception: cpe = ""
    paid = status in ("active", "trialing")           # echtes Stripe-Abo
    trial_ok = bool(te) and _iso_epoch(te) > now
    locked = (not paid) and (not trial_ok)
    days = 0
    if te and _iso_epoch(te) > now: days = int((_iso_epoch(te) - now) // 86400) + 1
    return {"plan": plan, "status": status, "locked": locked, "trialEnd": te, "trialDaysLeft": days, "currentPeriodEnd": cpe}
def _wh_verify(payload, sig, secret):
    try:
        parts = dict(p.split("=", 1) for p in (sig or "").split(","))
        signed = (parts.get("t", "") + "." + payload.decode()).encode()
        mac = hmac.new(secret.encode(), signed, hashlib.sha256).hexdigest()
        return hmac.compare_digest(mac, parts.get("v1", ""))
    except Exception:
        return False

# ---------- 2-Faktor-Authentifizierung per E-Mail (Code) ----------
def _twofa_on():
    if not bool(_cfg("TWOFA_ENABLED", True)):
        return False
    return bool(str(_cfg("SMTP_HOST", "") or ""))   # nur wenn E-Mail-Versand möglich
def _rand_code():
    return "%06d" % (int.from_bytes(os.urandom(4), "big") % 1000000)
def _code_hash(code, challenge):
    return hmac.new(SECRET, (challenge + "|" + str(code)).encode(), hashlib.sha256).hexdigest()
def _mask_email(e):
    try:
        u, d = e.split("@", 1)
        return (u[0] + "***" if len(u) > 1 else "***") + "@" + d
    except Exception:
        return e
def _2fa_start(user, purpose):
    ch = uid("2fa"); code = _rand_code(); exp = time.time() + 600
    with _lock, db() as c:
        c.execute("INSERT OR REPLACE INTO twofa(challenge,user_id,workshop_id,email,name,role,code_hash,purpose,expires,tries) VALUES(?,?,?,?,?,?,?,?,?,0)",
                  (ch, user["id"], user["workshop_id"], user["email"], user["name"], user["role"], _code_hash(code, ch), purpose, exp))
    txt = ("Hallo,\n\ndein Velqio-Bestaetigungscode lautet:\n\n    " + code +
           "\n\nDer Code ist 10 Minuten gueltig. Wenn du dich nicht anmelden wolltest, ignoriere diese E-Mail.\n\nDein Velqio-Team")
    try:
        send_mail(user["workshop_id"], user["email"], "Velqio - Dein Bestaetigungscode: " + code, txt)
    except Exception:
        pass
    return ch

# ---------- Datenbank ----------
class _DBCtx:
    """Context-Manager: committet bei Erfolg, rollt bei Fehler zurück und SCHLIESST IMMER die Verbindung
    (verhindert File-Descriptor-Leak unter Dauerlast wie Long-Polling)."""
    def __enter__(self):
        self.c = sqlite3.connect(DB_PATH, timeout=10)
        self.c.row_factory = sqlite3.Row
        self.c.execute("PRAGMA journal_mode=WAL")
        return self.c
    def __exit__(self, et, ev, tb):
        try:
            if et is None:
                self.c.commit()
            else:
                self.c.rollback()
        except Exception:
            pass
        finally:
            try: self.c.close()
            except Exception: pass
        return False

def db():
    return _DBCtx()

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
        CREATE TABLE IF NOT EXISTS twofa(
          challenge TEXT PRIMARY KEY, user_id TEXT, workshop_id TEXT, email TEXT,
          name TEXT, role TEXT, code_hash TEXT, purpose TEXT, expires REAL, tries INTEGER DEFAULT 0);
        """)
        # Abo/Stripe-Spalten (idempotent nachrüsten)
        for col in ("plan", "sub_status", "trial_end", "stripe_customer", "stripe_sub", "current_period_end", "pub"):
            try: c.execute("ALTER TABLE workshops ADD COLUMN %s TEXT" % col)
            except Exception: pass
        # Bestehende Werkstätten (Pilot) NICHT aussperren: großzügige Testphase nachtragen
        far = _iso(time.time() + 30 * 86400)
        try: c.execute("UPDATE workshops SET trial_end=?, plan=COALESCE(NULLIF(plan,''),'trial'), sub_status=COALESCE(NULLIF(sub_status,''),'trial') WHERE trial_end IS NULL OR trial_end=''", (far,))
        except Exception: pass

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

# ---------- Öffentlicher Werkstatt-Schlüssel (für Website-Formular) ----------
def _ws_pub(wid):
    """Stabiler, öffentlich teilbarer Schlüssel je Werkstatt (nur zum Einreichen von
    Website-Anfragen; erlaubt keinerlei Lesezugriff). Wird bei Bedarf erzeugt."""
    with _lock, db() as c:
        row = c.execute("SELECT pub FROM workshops WHERE id=?", (wid,)).fetchone()
        if not row:
            return ""
        pub = row["pub"]
        if not pub:
            pub = base64.b32encode(os.urandom(7)).decode().rstrip("=").lower()
            c.execute("UPDATE workshops SET pub=? WHERE id=?", (pub, wid))
        return pub

# Einfacher Spam-Schutz für das öffentliche Formular (IP -> Zeitstempel)
_PUB_HITS = {}

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

# ---------- KI-Telefon-Empfangskraft (Voice-Bot: Twilio + Deepgram + Claude) ----------
_VOICE_CALLS = {}   # CallSid -> {wid, turns:[(role,text)], count, frm}

def _voice_on():
    return (bool(_cfg("VOICE_ENABLED", False))
            and bool(_cfg("TWILIO_AUTH_TOKEN", ""))
            and bool(_cfg("DEEPGRAM_API_KEY", ""))
            and bool(_cfg("ANTHROPIC_API_KEY", "") or _cfg("LLM_API_KEY", "")))

def _xe(s):
    return (str(s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;").replace("'", "&apos;"))

def _norm_num(s):
    d = "".join(ch for ch in str(s or "") if ch.isdigit())
    return d[-10:] if len(d) >= 10 else d

def _voice_prof(wid):
    with db() as c:
        r = c.execute("SELECT value FROM app_data WHERE workshop_id=? AND key='voice'", (wid,)).fetchone()
    if not r:
        return {}
    try: return json.loads(r["value"])
    except Exception: return {}

def _ws_by_voice_number(to):
    to2 = _norm_num(to)
    if not to2:
        return None, None
    with db() as c:
        rows = c.execute("SELECT workshop_id, value FROM app_data WHERE key='voice'").fetchall()
    for r in rows:
        try: prof = json.loads(r["value"])
        except Exception: continue
        if prof.get("enabled") and _norm_num(prof.get("number", "")) == to2:
            return r["workshop_id"], prof
    return None, None

def _deepgram_stt(audio, ct):
    key = _cfg("DEEPGRAM_API_KEY", "")
    if not key or not audio:
        return ""
    url = "https://api.deepgram.com/v1/listen?model=nova-2&language=de&smart_format=true&punctuate=true"
    req = _urlreq.Request(url, data=audio, headers={"Authorization": "Token " + key, "Content-Type": ct or "audio/wav"})
    try:
        with _urlreq.urlopen(req, timeout=25) as r:
            d = json.loads(r.read().decode())
        chans = ((d.get("results") or {}).get("channels") or [])
        alts = (chans[0].get("alternatives") if chans else []) or []
        return (alts[0].get("transcript", "") if alts else "").strip()
    except Exception:
        return ""

def _twilio_fetch(url):
    sid = _cfg("TWILIO_ACCOUNT_SID", ""); tok = _cfg("TWILIO_AUTH_TOKEN", "")
    req = _urlreq.Request(url)
    req.add_header("Authorization", "Basic " + base64.b64encode((sid + ":" + tok).encode()).decode())
    with _urlreq.urlopen(req, timeout=25) as r:
        return r.read(), r.headers.get("Content-Type", "audio/wav")

def _twilio_sig_ok(url, params, sig):
    tok = _cfg("TWILIO_AUTH_TOKEN", "")
    if not tok:
        return False
    s = url
    for k in sorted(params.keys()):
        s += k + params[k]
    mac = hmac.new(tok.encode(), s.encode(), hashlib.sha1).digest()
    return hmac.compare_digest(base64.b64encode(mac).decode(), sig or "")

def _voice_status_lookup(wid, text):
    """Bester Versuch: Auftrag zu genannter Auftragsnummer ODER Kundenname finden und den
    Reparatur-Status als gesprochenen Satz formulieren. Nur Lesezugriff."""
    import re as _re
    low = " " + (text or "").lower() + " "
    try:
        with db() as c:
            ords = c.execute("SELECT data FROM sync_items WHERE workshop_id=? AND coll='ord' AND deleted=0", (wid,)).fetchall()
            custs = c.execute("SELECT data FROM sync_items WHERE workshop_id=? AND coll='cust' AND deleted=0", (wid,)).fetchall()
    except Exception:
        return ""
    orders = []
    for r in ords:
        try: orders.append(json.loads(r["data"]))
        except Exception: pass
    cust = {}
    for r in custs:
        try:
            cc = json.loads(r["data"]); cust[cc.get("id")] = cc
        except Exception: pass
    STL = {"offen": "ist angenommen, aber noch nicht in Bearbeitung",
           "bearbeitung": "wird gerade repariert",
           "warten": "wartet noch auf ein Ersatzteil",
           "fertig": "ist fertig und abholbereit",
           "abgeholt": "wurde bereits abgeholt"}
    match = None
    digits = _re.findall(r"\d{2,}", text or "")
    for o in orders:
        nrd = "".join(ch for ch in str(o.get("nr", "")) if ch.isdigit())
        for dg in digits:
            if len(dg) >= 3 and nrd.endswith(dg):
                match = o; break
        if match: break
    if not match:
        for o in orders:
            c = cust.get(o.get("cid")) or {}
            nm = (c.get("name") or "").strip().lower()
            if nm and len(nm) >= 3:
                last = nm.split()[-1]
                if len(last) >= 3 and (" " + last + " ") in low:
                    match = o; break
    if not match:
        return ""
    st = match.get("status", "")
    phrase = STL.get(st, "ist bei uns in Bearbeitung")
    extra = ""
    if st == "fertig" and match.get("repResult"):
        rr = {"repariert": "erfolgreich repariert", "teilweise": "teilweise repariert",
              "unrepariert": "leider nicht repariert worden", "abgelehnt": "auf Wunsch nicht repariert worden",
              "nicht_reparierbar": "leider nicht reparierbar"}.get(match.get("repResult"), "")
        if rr: extra = " Es wurde " + rr + "."
    dev = (str(match.get("brand", "")) + " " + str(match.get("model", ""))).strip() or "Ihr Gerät"
    return dev + " " + phrase + "." + extra

def _voice_llm(prof, statusinfo, turns):
    key = _cfg("ANTHROPIC_API_KEY", "") or _cfg("LLM_API_KEY", "")
    if not key:
        return ""
    name = prof.get("name") or "die Werkstatt"
    facts = []
    if prof.get("hours"): facts.append("Öffnungszeiten: " + prof["hours"])
    if prof.get("address"): facts.append("Adresse: " + prof["address"])
    if prof.get("phone"): facts.append("Telefon: " + prof["phone"])
    if prof.get("faq"): facts.append("Weitere Infos: " + prof["faq"])
    sysmsg = ("Du bist die freundliche telefonische Empfangskraft der Reparaturwerkstatt '" + name +
              "'. Du sprichst am Telefon mit einem Kunden. Antworte sehr KURZ (1-2 Saetze), natuerlich gesprochen, "
              "auf Deutsch, ohne Aufzaehlungen oder Sonderzeichen. Beantworte nur Fragen zur Werkstatt "
              "(Oeffnungszeiten, Adresse, Reparatur-Status, ungefaehre Ablaeufe, allgemeine Infos). Erfinde NIEMALS "
              "Preise, feste Zusagen oder Termine. Wenn du etwas nicht sicher weisst oder der Kunde einen Menschen "
              "braucht, sag freundlich, dass du gern eine Rueckrufbitte aufnimmst. Fakten: "
              + (" | ".join(facts) or "keine hinterlegt") + ".")
    if statusinfo:
        sysmsg += " Aktueller Reparatur-Status (nutze ihn, wenn der Kunde danach fragt): " + statusinfo
    msgs = [{"role": ("assistant" if role == "assistant" else "user"), "content": txt} for role, txt in turns[-6:]]
    if not msgs:
        return ""
    payload = {"model": _cfg("LLM_MODEL", "claude-haiku-4-5"), "max_tokens": 160, "system": sysmsg, "messages": msgs}
    req = _urlreq.Request("https://api.anthropic.com/v1/messages", data=json.dumps(payload).encode(),
                          headers={"content-type": "application/json", "x-api-key": key, "anthropic-version": "2023-06-01"})
    try:
        with _urlreq.urlopen(req, timeout=25) as r:
            res = json.loads(r.read().decode())
        parts = res.get("content") or []
        return "".join(b.get("text", "") for b in parts if b.get("type") == "text").strip()
    except Exception:
        return ""

def _twiml(inner):
    return '<?xml version="1.0" encoding="UTF-8"?><Response>' + inner + '</Response>'

def _say(text):
    return '<Say language="de-DE" voice="Polly.Vicki">' + _xe(text) + '</Say>'

def _rec(action):
    return ('<Record action="' + _xe(action) + '" method="POST" maxLength="12" timeout="4" '
            'playBeep="true" trim="trim-silence" transcribe="false"/>')

_VOICE_END = ("nein danke", "nein, danke", "tschuess", "tschuss", "tschüss", "tschüs",
              "auf wiederhoeren", "auf wiederhören", "wiederhoeren", "wiederhören",
              "das war es", "das wars", "das war's", "nichts weiter", "nichts mehr", "alles klar danke")

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

    def _form(self):
        n = int(self.headers.get("Content-Length", 0) or 0)
        if not n:
            return {}
        try:
            raw = self.rfile.read(n).decode("utf-8", "ignore")
            return {k: v[0] for k, v in parse_qs(raw, keep_blank_values=True).items()}
        except Exception:
            return {}

    def _send_xml(self, code, xml):
        data = xml.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "text/xml; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _voice_url(self):
        host = self.headers.get("X-Forwarded-Host") or self.headers.get("Host") or "velqio.de"
        proto = self.headers.get("X-Forwarded-Proto") or "https"
        return proto + "://" + host + self.path

    def _voice(self, path):
        params = self._form()
        if not _voice_on() or not _twilio_sig_ok(self._voice_url(), params, self.headers.get("X-Twilio-Signature", "")):
            return self._send_xml(200, _twiml(_say("Dieser Dienst ist gerade nicht verfuegbar. Auf Wiederhoeren.")))
        frm = params.get("From", ""); to = params.get("To", ""); sid = params.get("CallSid", "")
        q = parse_qs(urlparse(path).query); csid = (q.get("sid") or [sid])[0]
        if path.startswith("/api/voice/incoming"):
            wid, prof = _ws_by_voice_number(to)
            if not wid:
                return self._send_xml(200, _twiml(_say("Vielen Dank fuer Ihren Anruf. Bitte versuchen Sie es spaeter erneut. Auf Wiederhoeren.")))
            if len(_VOICE_CALLS) > 500:
                _VOICE_CALLS.clear()
            _VOICE_CALLS[sid] = {"wid": wid, "turns": [], "count": 0, "frm": frm}
            greet = prof.get("greeting") or ("Willkommen bei " + (prof.get("name") or "der Werkstatt") + ". Ich bin die digitale Empfangskraft. Wie kann ich Ihnen helfen?")
            return self._send_xml(200, _twiml(_say(greet) + _rec("/api/voice/step?sid=" + _urlparse.quote(sid))))
        if path.startswith("/api/voice/step"):
            st = _VOICE_CALLS.get(csid)
            if not st:
                return self._send_xml(200, _twiml(_say("Entschuldigung, es gab ein technisches Problem. Auf Wiederhoeren.")))
            transcript = ""
            rec = params.get("RecordingUrl", "")
            if rec:
                try:
                    audio, ct = _twilio_fetch(rec + ".wav")
                    transcript = _deepgram_stt(audio, "audio/wav")
                except Exception:
                    transcript = ""
            st["count"] += 1
            low = transcript.lower().strip()
            if st["count"] > 5 or (low and any(w in low for w in _VOICE_END)):
                return self._send_xml(200, _twiml(
                    _say("Alles klar. Wenn Sie moechten, nennen Sie mir nach dem Signalton kurz Ihren Namen und Ihr Anliegen, dann rufen wir Sie zurueck. Sonst koennen Sie einfach auflegen. Auf Wiederhoeren.")
                    + _rec("/api/voice/callback?sid=" + _urlparse.quote(csid))))
            if not low:
                if st["count"] >= 3:
                    return self._send_xml(200, _twiml(_say("Ich konnte Sie leider nicht verstehen. Bitte nennen Sie nach dem Signalton Ihren Namen und Ihr Anliegen, wir rufen Sie zurueck.") + _rec("/api/voice/callback?sid=" + _urlparse.quote(csid))))
                return self._send_xml(200, _twiml(_say("Entschuldigung, das habe ich nicht verstanden. Bitte wiederholen Sie es nach dem Signalton.") + _rec("/api/voice/step?sid=" + _urlparse.quote(csid))))
            st["turns"].append(("user", transcript))
            statusinfo = _voice_status_lookup(st["wid"], transcript)
            answer = _voice_llm(_voice_prof(st["wid"]), statusinfo, st["turns"]) or "Das kann ich Ihnen am Telefon leider nicht sicher beantworten. Gern nehme ich eine Rueckrufbitte auf."
            st["turns"].append(("assistant", answer))
            return self._send_xml(200, _twiml(_say(answer) + _say("Kann ich sonst noch etwas fuer Sie tun? Wenn nicht, sagen Sie einfach: nein danke.") + _rec("/api/voice/step?sid=" + _urlparse.quote(csid))))
        if path.startswith("/api/voice/callback"):
            st = _VOICE_CALLS.get(csid) or {}
            wid = st.get("wid")
            transcript = ""
            rec = params.get("RecordingUrl", "")
            if rec and wid:
                try:
                    audio, ct = _twilio_fetch(rec + ".wav")
                    transcript = _deepgram_stt(audio, "audio/wav")
                except Exception:
                    transcript = ""
            if wid and (transcript or frm):
                try:
                    now = time.time()
                    data = {"name": "Telefon-Anrufer", "tel": frm or "", "type": "", "brand": "", "model": "",
                            "issue": "Telefon-Rueckruf", "problem": transcript or "(keine Sprachnachricht hinterlassen)",
                            "contact": "Rückruf", "besttime": "", "at": _iso(now)}
                    with _lock, db() as c:
                        c.execute("INSERT INTO intake_sessions(token,workshop_id,herkunft,workshop_name,workshop_tel,data,submitted,consumed,created,expires) VALUES(?,?,?,?,?,?,?,?,?,?)",
                                  (uid("cb"), wid, "telefon", "", "", json.dumps(data), 1, 0, now, now + 30 * 86400))
                except Exception:
                    pass
            _VOICE_CALLS.pop(csid, None)
            return self._send_xml(200, _twiml(_say("Vielen Dank. Wir melden uns bei Ihnen. Auf Wiederhoeren.") + "<Hangup/>"))
        return self._send_xml(200, _twiml(_say("Auf Wiederhoeren.") + "<Hangup/>"))

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
                # Long-Polling: bis ~20s auf eine Änderung warten -> nahezu Echtzeit ohne WebSocket
                deadline = time.time() + 20
                while not items and time.time() < deadline:
                    time.sleep(1.5)
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
        if self.path.startswith("/api/intake/info"):
            # Öffentlich: Website-Formular liest den Werkstatt-Namen anhand des öffentlichen Schlüssels.
            q = parse_qs(urlparse(self.path).query)
            key = (q.get("key") or [""])[0].strip().lower()
            if not key:
                return self._send(400, {"error": "key fehlt"})
            with db() as c:
                w = c.execute("SELECT name FROM workshops WHERE pub=?", (key,)).fetchone()
            if not w:
                return self._send(404, {"error": "nicht gefunden"})
            return self._send(200, {"ok": True, "name": w["name"] or "Werkstatt"})
        if self.path == "/api/intake/key":
            # Werkstatt holt ihren stabilen öffentlichen Formular-Schlüssel (für Website-Einbindung).
            p = self._auth()
            if not p:
                return self._send(401, {"error": "unauthorized"})
            return self._send(200, {"ok": True, "key": _ws_pub(p["wid"])})
        if self.path == "/api/voice/config":
            # Werkstatt liest ihre Telefon-Bot-Konfiguration + die Webhook-URL für Twilio.
            p = self._auth()
            if not p:
                return self._send(401, {"error": "unauthorized"})
            base = str(_cfg("APP_BASE_URL", "https://velqio.de")).rstrip("/")
            return self._send(200, {"ok": True, "profile": _voice_prof(p["wid"]),
                                    "webhook": base + "/api/voice/incoming", "voiceReady": _voice_on()})
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
        if self.path == "/api/billing/status":
            p = self._auth()
            if not p:
                return self._send(401, {"error": "unauthorized"})
            return self._send(200, billing_info(p["wid"]))
        return self._send(404, {"error": "not found"})

    def _webhook(self):
        secret = str(_cfg("STRIPE_WEBHOOK_SECRET", "") or "")
        n = int(self.headers.get("Content-Length", 0) or 0)
        raw = self.rfile.read(n) if n else b""
        if not secret or not _wh_verify(raw, self.headers.get("Stripe-Signature", ""), secret):
            return self._send(400, {"error": "bad signature"})
        try: evt = json.loads(raw.decode() or "{}")
        except Exception: return self._send(400, {"error": "bad json"})
        typ = evt.get("type", ""); obj = (evt.get("data") or {}).get("object") or {}
        try:
            if typ == "checkout.session.completed":
                wid = obj.get("client_reference_id") or (obj.get("metadata") or {}).get("wid")
                plan = (obj.get("metadata") or {}).get("plan") or ""
                if wid:
                    _ws_set(wid, stripe_customer=obj.get("customer") or "", stripe_sub=obj.get("subscription") or "",
                            plan=(plan or "pro"), sub_status="active")
            elif typ in ("customer.subscription.updated", "customer.subscription.created"):
                row = _ws_by_customer(obj.get("customer"))
                if row:
                    items = (obj.get("items") or {}).get("data") or []
                    pid = ((items[0].get("price") or {}).get("id")) if items else ""
                    f = {"sub_status": obj.get("status") or "", "current_period_end": _iso(obj.get("current_period_end")), "stripe_sub": obj.get("id") or ""}
                    pl = _plan_for_price(pid)
                    if pl: f["plan"] = pl
                    _ws_set(row["id"], **f)
            elif typ == "customer.subscription.deleted":
                row = _ws_by_customer(obj.get("customer"))
                if row: _ws_set(row["id"], sub_status="canceled")
        except Exception:
            pass
        return self._send(200, {"received": True})

    def do_POST(self):
        if self.path == "/api/stripe/webhook":
            return self._webhook()
        if self.path.startswith(("/api/voice/incoming", "/api/voice/step", "/api/voice/callback")):
            return self._voice(self.path)
        body = self._body()
        if self.path == "/api/voice/config":
            p = self._auth()
            if not p:
                return self._send(401, {"error": "unauthorized"})
            prof = body.get("profile") or {}
            clean = {k: (str(prof.get(k, ""))[:800]) for k in ("number", "name", "greeting", "hours", "address", "phone", "faq")}
            clean["enabled"] = bool(prof.get("enabled"))
            with _lock, db() as c:
                c.execute("INSERT INTO app_data(workshop_id,key,value,updated_at) VALUES(?,?,?,?) ON CONFLICT(workshop_id,key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
                          (p["wid"], "voice", json.dumps(clean), _iso()))
            return self._send(200, {"ok": True})

        if self.path == "/api/auth/login":
            email = (body.get("email") or "").strip().lower()
            pw = body.get("password") or ""
            with db() as c:
                u = c.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
            if not u or not check_pw(pw, u["pw_hash"], u["pw_salt"]):
                return self._send(401, {"error": "E-Mail oder Passwort falsch"})
            if _twofa_on():
                ch = _2fa_start(u, "login")
                return self._send(200, {"twofa": True, "challenge": ch, "email": _mask_email(u["email"])})
            token = make_token(u["id"], u["workshop_id"])
            return self._send(200, {"token": token, "workshopId": u["workshop_id"],
                                    "name": u["name"], "role": u["role"], "billing": billing_info(u["workshop_id"])})

        if self.path == "/api/auth/2fa/verify":
            ch = body.get("challenge") or ""; code = (body.get("code") or "").strip()
            now = time.time()
            with _lock, db() as c:
                row = c.execute("SELECT * FROM twofa WHERE challenge=?", (ch,)).fetchone()
                if not row or (row["expires"] or 0) < now:
                    return self._send(400, {"error": "Code abgelaufen. Bitte neu anmelden."})
                if (row["tries"] or 0) >= 5:
                    c.execute("DELETE FROM twofa WHERE challenge=?", (ch,))
                    return self._send(400, {"error": "Zu viele Fehlversuche. Bitte neu anmelden."})
                if not hmac.compare_digest(_code_hash(code, ch), row["code_hash"] or ""):
                    c.execute("UPDATE twofa SET tries=tries+1 WHERE challenge=?", (ch,))
                    left = 5 - ((row["tries"] or 0) + 1)
                    return self._send(400, {"error": "Code falsch. Noch %d Versuch(e)." % max(0, left)})
                c.execute("DELETE FROM twofa WHERE challenge=?", (ch,))
            token = make_token(row["user_id"], row["workshop_id"])
            return self._send(200, {"token": token, "workshopId": row["workshop_id"],
                                    "name": row["name"], "role": row["role"], "billing": billing_info(row["workshop_id"])})

        if self.path == "/api/auth/2fa/resend":
            ch = body.get("challenge") or ""; now = time.time()
            with db() as c:
                row = c.execute("SELECT workshop_id,email,expires FROM twofa WHERE challenge=?", (ch,)).fetchone()
            if not row:
                return self._send(400, {"error": "Sitzung abgelaufen. Bitte neu anmelden."})
            code = _rand_code()
            with _lock, db() as c:
                c.execute("UPDATE twofa SET code_hash=?, expires=?, tries=0 WHERE challenge=?", (_code_hash(code, ch), time.time() + 600, ch))
            txt = ("Hallo,\n\ndein neuer Velqio-Bestaetigungscode lautet:\n\n    " + code + "\n\n10 Minuten gueltig.\n\nDein Velqio-Team")
            try: send_mail(row["workshop_id"], row["email"], "Velqio - Dein Bestaetigungscode: " + code, txt)
            except Exception: pass
            return self._send(200, {"ok": True})

        if self.path == "/api/billing/checkout":
            p = self._auth()
            if not p:
                return self._send(401, {"error": "unauthorized"})
            plan = (body.get("plan") or "").lower()
            price = _price_for_plan(plan)
            if not price:
                return self._send(400, {"error": "Unbekannter Tarif oder Preis nicht konfiguriert"})
            base = str(_cfg("APP_BASE_URL", "https://velqio.de")).rstrip("/")
            ws = _ws_get(p["wid"])
            params = {"mode": "subscription", "line_items[0][price]": price, "line_items[0][quantity]": 1,
                      "client_reference_id": p["wid"], "metadata[wid]": p["wid"], "metadata[plan]": plan,
                      "subscription_data[metadata][wid]": p["wid"], "allow_promotion_codes": "true",
                      "success_url": base + "/app.html?billing=success", "cancel_url": base + "/app.html?billing=cancel"}
            cust = ""
            try: cust = ws["stripe_customer"] if ws else ""
            except Exception: cust = ""
            if cust:
                params["customer"] = cust
            else:
                with db() as c:
                    u2 = c.execute("SELECT email FROM users WHERE workshop_id=? ORDER BY created ASC LIMIT 1", (p["wid"],)).fetchone()
                if u2 and u2["email"]:
                    params["customer_email"] = u2["email"]
            try:
                sess = _stripe("POST", "checkout/sessions", params)
            except Exception:
                return self._send(500, {"error": "Stripe nicht erreichbar / nicht konfiguriert"})
            if sess.get("url"):
                return self._send(200, {"url": sess["url"]})
            return self._send(500, {"error": (sess.get("error") or {}).get("message") or "Checkout fehlgeschlagen"})

        if self.path == "/api/billing/portal":
            p = self._auth()
            if not p:
                return self._send(401, {"error": "unauthorized"})
            ws = _ws_get(p["wid"])
            cust = ""
            try: cust = ws["stripe_customer"] if ws else ""
            except Exception: cust = ""
            if not cust:
                return self._send(400, {"error": "Noch kein Abo vorhanden"})
            base = str(_cfg("APP_BASE_URL", "https://velqio.de")).rstrip("/")
            try:
                sess = _stripe("POST", "billing_portal/sessions", {"customer": cust, "return_url": base + "/app.html"})
            except Exception:
                return self._send(500, {"error": "Stripe nicht erreichbar"})
            if sess.get("url"):
                return self._send(200, {"url": sess["url"]})
            return self._send(500, {"error": (sess.get("error") or {}).get("message") or "Portal fehlgeschlagen"})

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
                    c.execute("INSERT INTO workshops(id,name,created,plan,sub_status,trial_end) VALUES(?,?,?,?,?,?)",
                              (wid, wname, now, "trial", "trial", _iso(time.time() + 14 * 86400)))
                    c.execute("INSERT INTO users(id,workshop_id,email,pw_hash,pw_salt,role,name,created) VALUES(?,?,?,?,?,?,?,?)",
                              (usr, wid, email, ph, salt, "inhaber", uname, now))
            except sqlite3.IntegrityError:
                return self._send(409, {"error": "Diese E-Mail ist bereits registriert"})
            if _twofa_on():
                ch = _2fa_start({"id": usr, "workshop_id": wid, "email": email, "name": uname, "role": "inhaber"}, "signup")
                return self._send(200, {"twofa": True, "challenge": ch, "email": _mask_email(email)})
            token = make_token(usr, wid)
            return self._send(200, {"token": token, "workshopId": wid, "name": uname, "role": "inhaber", "billing": billing_info(wid)})

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
            if billing_info(p["wid"]).get("locked"):
                return self._send(402, {"error": "billing_locked", "message": "Testphase abgelaufen – bitte Tarif buchen."})
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
            if billing_info(p["wid"]).get("locked"):
                return self._send(402, {"error": "billing_locked", "message": "Testphase abgelaufen – bitte Tarif buchen."})
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
                        srv_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                        seen = set(); merged = []
                        for e in (list(prev_act) + list(new_act)):
                            if not isinstance(e, dict): continue
                            eid = e.get("id") or (str(e.get("at","")) + "|" + str(e.get("action","")))
                            if eid in seen: continue
                            seen.add(eid); merged.append(e)
                        # server-Empfangszeit einmalig setzen (danach unveränderlich -> manipulationssicherer Anker)
                        for e in merged:
                            if isinstance(e, dict) and not e.get("sat"):
                                e["sat"] = srv_iso
                        data["activity"] = merged
                        for e in new_act:
                            if not isinstance(e, dict): continue
                            eid = str(e.get("id") or "")
                            if not eid: continue
                            try:
                                c.execute("""INSERT OR IGNORE INTO activity_log(workshop_id,order_id,entry_id,user_id,user_name,action,detail,at)
                                             VALUES(?,?,?,?,?,?,?,?)""",
                                          (p["wid"], rid, eid, str(e.get("uid","")), str(e.get("user","")),
                                           str(e.get("action","")), str(e.get("detail","")), (e.get("sat") or str(e.get("at","")))))
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
            if billing_info(p["wid"]).get("locked"):
                return self._send(402, {"error": "billing_locked"})
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

        if self.path == "/api/intake/public":
            # Öffentlich: Website-Formular reicht eine Anfrage per stabilem Werkstatt-Schlüssel ein.
            ip = (self.headers.get("X-Forwarded-For", "").split(",")[0].strip() or self.client_address[0])
            now = time.time()
            hits = [t for t in _PUB_HITS.get(ip, []) if t > now - 3600]
            if len(hits) >= 20:
                return self._send(429, {"error": "Zu viele Anfragen – bitte später erneut."})
            key = (body.get("key") or "").strip().lower()
            data = body.get("data")
            herkunft = (str(body.get("herkunft") or "website")).strip()[:40] or "website"
            if not key or not isinstance(data, dict):
                return self._send(400, {"error": "Formular unvollständig"})
            if not (str(data.get("name", "")).strip() and str(data.get("tel", "")).strip()):
                return self._send(400, {"error": "Name und Telefon nötig"})
            clean = {k: (str(data.get(k, ""))[:500]) for k in
                     ("name", "tel", "mail", "type", "brand", "model", "issue", "problem", "contact", "besttime")}
            clean["at"] = _iso(now)
            with _lock, db() as c:
                w = c.execute("SELECT id FROM workshops WHERE pub=?", (key,)).fetchone()
                if not w:
                    return self._send(404, {"error": "Formular nicht gefunden"})
                c.execute("DELETE FROM intake_sessions WHERE expires<?", (now,))
                cnt = c.execute("SELECT COUNT(*) n FROM intake_sessions WHERE workshop_id=? AND submitted=1 AND consumed=0",
                                (w["id"],)).fetchone()["n"]
                if cnt > 200:
                    return self._send(429, {"error": "Posteingang voll – bitte später erneut."})
                c.execute("INSERT INTO intake_sessions(token,workshop_id,herkunft,workshop_name,workshop_tel,data,submitted,consumed,created,expires) VALUES(?,?,?,?,?,?,?,?,?,?)",
                          (uid("wq"), w["id"], herkunft, "", "", json.dumps(clean), 1, 0, now, now + 30 * 86400))
            _PUB_HITS[ip] = hits + [now]
            if len(_PUB_HITS) > 5000:
                for k2 in [k3 for k3, v in _PUB_HITS.items() if not [t for t in v if t > now - 3600]]:
                    _PUB_HITS.pop(k2, None)
            return self._send(200, {"ok": True})

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
                    c.execute("INSERT INTO workshops(id,name,created,plan,sub_status,trial_end) VALUES(?,?,?,?,?,?)",
                              (wid, wname, now, "trial", "trial", _iso(time.time() + 14 * 86400)))
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
