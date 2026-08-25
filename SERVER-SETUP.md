# Reparado live schalten — auf dem bestehenden Server (neben dem Agenten-Büro)

Reparado läuft als **eigener, getrennter Dienst** auf demselben Hetzner-Server wie dein
Agenten-Büro: eigener Port (8790, nur intern), eigene Subdomain, eigene Datenbank.
**0 € extra.** Das Agenten-Büro bleibt völlig unberührt.

Das Backend (`server.py`) ist **lokal end-to-end getestet** (Login + geteiltes Speichern/Laden + Mail).

> Ich kann nicht selbst per SSH auf den Server. Die einmalige Einrichtung machst du
> (per SSH, wie beim Agenten-Büro) — ich liefere alle Dateien + Befehle zum Kopieren.

---

## 1. DNS (Subdomain auf denselben Server)
Bei IONOS einen **A-Record** anlegen: `werkstatt` → **dieselbe Server-IP** wie `agents.margency.de`.
→ ergibt `werkstatt.margency.de`. *(Anderer Name geht auch — sag mir welchen.)*

## 2. Dateien auf den Server laden (von deinem Mac, aus dem Projektordner)
```bash
SRV=root@DEINE.SERVER.IP        # dieselbe IP wie beim Agenten-Büro
ssh $SRV "mkdir -p /opt/reparado && useradd -r -s /usr/sbin/nologin reparado 2>/dev/null; chown -R reparado:reparado /opt/reparado"
scp server.py config.example.py $SRV:/opt/reparado/
scp deploy/reparado.service $SRV:/etc/systemd/system/
```

## 3. Server-Konfiguration (auf dem Server)
```bash
ssh $SRV
cd /opt/reparado && cp config.example.py config.py
python3 -c "import secrets;print('SECRET_KEY =', repr(secrets.token_hex(32)));print('ADMIN_KEY =', repr(secrets.token_hex(16)))"
nano config.py     # die zwei Keys einsetzen; CORS_ORIGIN = "https://singh-oss.github.io"; ggf. SMTP-Daten
chown reparado:reparado config.py
systemctl daemon-reload && systemctl enable --now reparado
systemctl is-active reparado && curl -s http://127.0.0.1:8790/api/health   # -> {"ok": true...}
```

## 4. Caddy: Subdomain ergänzen (NICHT die Agenten-Büro-Zeilen anfassen!)
An die bestehende `/etc/caddy/Caddyfile` **unten anhängen**:
```
werkstatt.margency.de {
    reverse_proxy 127.0.0.1:8790
    encode gzip
}
```
Dann: `systemctl reload caddy`
Check: `curl https://werkstatt.margency.de/api/health` → `{"ok": true, ...}`

## 5. Erste Werkstatt + Login anlegen (einmalig)
```bash
curl -X POST https://werkstatt.margency.de/api/admin/provision \
  -H "X-Admin-Key: DEIN-ADMIN-KEY" -H "Content-Type: application/json" \
  -d '{"workshopName":"Dein Handy Doc","email":"chef@deinhandydoc.de","password":"SICHERES-PASSWORT","userName":"Murat"}'
```
→ E-Mail/Passwort = der Werkstatt-Login. (workshopId wird zurückgegeben, brauchst du nicht extra.)

## 6. App auf den Server zeigen lassen
`config.js` neben `app.html`:
```js
window.REPARADO_CONFIG = { apiUrl: "https://werkstatt.margency.de" };
```
Danach zeigt die App beim Öffnen einen **Login** und arbeitet mit geteilten Serverdaten — auf jedem Gerät derselbe Stand.

---

## Updates später
`deploy/deploy.command` (Server-IP darin eintragen) per Doppelklick → lädt `server.py` hoch + Neustart. Genau wie beim Agenten-Büro.

## Nächste Schritte
- **Echter Mailversand:** SMTP-Daten in `config.py` → Status-/Erinnerungs-Mails gehen wirklich raus.
- **DB-Backup:** kleinen täglichen Cron für `/opt/reparado/reparado.db` richte ich ein.
- **AVV/DSGVO:** Vorlage bereite ich vor, bevor echte Kundendaten drin sind.
