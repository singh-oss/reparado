// Reparado – Server-Anbindung (Supabase)
// -----------------------------------------------------------------------------
// So aktivierst du den echten, geteilten Datenbank-Betrieb:
//   1) Diese Datei nach  config.js  kopieren
//   2) Die drei Werte unten aus deinem Supabase-Projekt eintragen
//   3) Fertig – die App läuft dann im Server-Modus (Login + geteilte Daten).
// Ohne config.js bleibt die App im lokalen Prototyp-Modus (localStorage).
//
// ⚠️ SICHERHEIT:
//   - Hier gehört NUR der ÖFFENTLICHE "anon"/"publishable"-Key rein (der ist für
//     das Frontend gedacht; Row Level Security schützt die Daten serverseitig).
//   - Der "service_role"-Key darf NIEMALS hierher / ins Frontend / ins Repo!
//   - config.js steht in .gitignore und wird NICHT eingecheckt.

window.REPARADO_CONFIG = {
  supabaseUrl: "https://DEIN-PROJEKT.supabase.co",   // Project URL
  supabaseKey: "eyJ...DEIN-ANON-KEY...",              // anon / publishable key
  workshopId:  "WERKSTATT-UUID-AUS-DER-TABELLE-workshops"  // die id-Zeile deiner Werkstatt
};
