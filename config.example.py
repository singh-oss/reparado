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

# Abrechnung / Stripe (Abo Basic/Pro/AI). Leer lassen = Abo deaktiviert (App läuft ohne Bezahlschranke).
APP_BASE_URL = "https://velqio.de"          # für Checkout-Rücksprung + Passwort-Reset-Links
STRIPE_SECRET_KEY    = ""                    # sk_live_… (GEHEIM! nur hier auf dem Server)
STRIPE_WEBHOOK_SECRET = ""                   # whsec_… (aus dem Webhook-Endpunkt im Stripe-Dashboard)
STRIPE_PRICE_BASIC = ""                      # price_… (Basic 49,90 €/Monat, wiederkehrend)
STRIPE_PRICE_PRO   = ""                      # price_… (Pro 84,90 €/Monat)
STRIPE_PRICE_AI    = ""                      # price_… (AI 99,90 €/Monat)
