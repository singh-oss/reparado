// Reparado – Server-Anbindung
// -----------------------------------------------------------------------------
// So aktivierst du den echten, geteilten Betrieb (Reparado-Backend auf Hetzner):
//   1) Diese Datei nach  config.js  kopieren
//   2) apiUrl auf die Adresse deines Reparado-Backends setzen
//   3) Fertig – die App zeigt dann einen Login und arbeitet mit geteilten Daten.
// Ohne config.js läuft die App im lokalen Prototyp-Modus (localStorage).
//
// Hier stehen KEINE Geheimnisse – nur die öffentliche API-Adresse.
// Login/Rechte laufen über das Backend (Token). config.js ist in .gitignore.

window.REPARADO_CONFIG = {
  apiUrl: "https://werkstatt.margency.de"   // Adresse des Reparado-Backends (Caddy -> server.py)
  // Lokaler Test:  apiUrl: "http://127.0.0.1:8790"
};
