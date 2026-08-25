# Reparado live schalten — eigener Hetzner-Server

Ziel: Reparado auf deinem eigenen (neuen) Hetzner-Server betreiben — **geteilte Daten,
Login, echter Mailversand**. Das Backend (`server.py`) ist bereits gebaut und **lokal
end-to-end getestet** (Login + geteiltes Laden/Speichern + Mail-Endpunkt).

> Was nur du machen kannst: Server buchen + DNS. Ich liefere Code + Deploy-Skript.
> Ich kann nicht selbst per SSH drauf — der Deploy läuft per `deploy/deploy.command`, das du ausführst (wie beim Agenten-Büro).

---

## 1. Server buchen (Hetzner Cloud)
- Neuer Server, **Region Nürnberg/Falkenstein (EU)**, z. B. **CX22** (reicht locker).
- Image **Ubuntu 24.04**. SSH-Key hinterlegen. → Server-IP notieren.

## 2. DNS
- Bei deinem DNS (IONOS): **A-Record** `werkstatt` → Server-IP.
  (Ergibt `werkstatt.margency.de` — Subdomain für das Backend.)

## 3. Server einrichten (einmalig, per SSH)
```bash
ssh root@DEINE.SERVER.IP
apt update && apt install -y python3 caddy
useradd -r -s /usr/sbin/nologin reparado
mkdir -p /opt/reparado && chown reparado:reparado /opt/reparado
```
Dann von deinem Mac hochladen (aus dem Projektordner):
```bash
scp server.py config.example.py root@DEINE.SERVER.IP:/opt/reparado/
scp deploy/reparado.service root@DEINE.SERVER.IP:/etc/systemd/system/
scp deploy/Caddyfile root@DEINE.SERVER.IP:/etc/caddy/Caddyfile
```
Auf dem Server `config.py` anlegen (aus der Vorlage) und **SECRET_KEY / ADMIN_KEY** setzen:
```bash
cd /opt/reparado && cp config.example.py config.py
python3 -c "import secrets;print('SECRET_KEY =', repr(secrets.token_hex(32)));print('ADMIN_KEY =', repr(secrets.token_hex(16)))"
nano config.py   # die zwei Werte einsetzen, CORS_ORIGIN auf die App-Adresse, ggf. SMTP-Daten
chown reparado:reparado config.py
systemctl daemon-reload && systemctl enable --now reparado && systemctl restart caddy
```
Check: `curl https://werkstatt.margency.de/api/health` → `{"ok": true, ...}`

## 4. Erste Werkstatt + Login anlegen
Einmalig über den geschützten Provision-Endpunkt (ADMIN_KEY aus config.py):
```bash
curl -X POST https://werkstatt.margency.de/api/admin/provision \
  -H "X-Admin-Key: DEIN-ADMIN-KEY" -H "Content-Type: application/json" \
  -d '{"workshopName":"Dein Handy Doc","email":"chef@deinhandydoc.de","password":"EIN-SICHERES-PASSWORT","userName":"Murat"}'
```
→ Notiere die zurückgegebene `workshopId`. Das E-Mail/Passwort ist der spätere Werkstatt-Login.

## 5. App auf den Server zeigen lassen
`config.js` (Frontend) neben der App:
```js
window.REPARADO_CONFIG = { apiUrl: "https://werkstatt.margency.de" };
```
- Für den Live-Betrieb auf GitHub Pages: `config.js` neben `app.html` legen (nicht ins öffentliche Repo — sie enthält nur die API-Adresse, kein Geheimnis; du kannst sie aber auch einfach committen, da harmlos).
- Danach zeigt die App beim Öffnen einen **Login** und arbeitet mit geteilten Serverdaten.

---

## Danach (nächste Schritte)
- **Echter Mailversand:** SMTP-Daten in `config.py` eintragen → Status-/Erinnerungs-Mails gehen wirklich raus.
- **Updates:** einfach `deploy/deploy.command` ausführen (SERVER-IP darin eintragen) → lädt server.py hoch + Neustart.
- **DSGVO/AVV:** Vorlage für den Auftragsverarbeitungsvertrag bereite ich vor, bevor echte Kundendaten drin sind.
- **Backups:** kleines Cronjob-Backup der `reparado.db` richte ich dir ein.
