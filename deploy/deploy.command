#!/bin/bash
# Reparado-Backend auf den Hetzner-Server hochladen + neu starten.
# Vor dem ersten Lauf: SERVER unten auf deine Server-IP/Adresse setzen.
# Ausführen per Doppelklick (macOS) – überträgt server.py und startet den Dienst neu.

set -e
SERVER="root@DEINE.SERVER.IP"      # <-- anpassen
REMOTE_DIR="/opt/reparado"

cd "$(dirname "$0")/.."
echo "→ Übertrage server.py nach $SERVER:$REMOTE_DIR ..."
scp server.py "$SERVER:$REMOTE_DIR/server.py"

echo "→ Dienst neu starten ..."
ssh "$SERVER" "systemctl restart reparado && sleep 1 && systemctl is-active reparado && curl -s -o /dev/null -w 'health: %{http_code}\n' http://127.0.0.1:8790/api/health"

echo "✓ Fertig."
