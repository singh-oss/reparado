# Reparado-Backend – Server-Konfiguration
# ---------------------------------------------------------------------------
# Auf dem Hetzner-Server nach  config.py  kopieren und ausfüllen.
# NICHT ins (öffentliche) Repo committen – steht in .gitignore.

# Sicherheit
SECRET_KEY = "HIER-LANGEN-ZUFALLSSTRING-EINSETZEN"     # signiert Login-Tokens (z. B. `openssl rand -hex 32`)
ADMIN_KEY  = "HIER-ZWEITEN-ZUFALLSSTRING-EINSETZEN"    # schützt /api/admin/provision (Werkstatt anlegen)

# Betrieb
DB_PATH     = "/opt/reparado/reparado.db"
PORT        = 8790
CORS_ORIGIN = "https://singh-oss.github.io"            # exakte Adresse der App (Frontend). "*" nur zum Testen.
TOKEN_TTL_DAYS = 30

# E-Mail-Versand (echter Kundennachrichten-Versand). Leer lassen = wird nur protokolliert.
SMTP_HOST = ""                 # z. B. "smtp.ionos.de"
SMTP_PORT = 587
SMTP_USER = ""                 # Postfach-Login
SMTP_PASS = ""                 # Postfach-Passwort
MAIL_FROM = "Dein Handy Doc <info@deinhandydoc.de>"
