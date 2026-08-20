# Track F — Vom Prototyp zum vollwertigen System

**Rahmen (vom Nutzer festgelegt, 19.8.2026):**
- **Erst lokal bauen** – kein Cloud-Konto nötig, um zu starten.
- **Vorerst simuliert** – kein echter Mail-/SMS-Versand ohne ausdrückliche Freigabe pro Schritt.
- **Server-Anbindung als Letztes** – zuerst alles andere (Architektur + Features), dann der echte Server.

Der Prototyp ist funktional vollständig (39 Roadmap-Punkte, Phasen 1–5). Track F macht ihn produktiv.

---

## Phasen

### F1 · Fundament (läuft)
- [x] **Datenschicht-Naht** (`DB`-Adapter in `app.html`) – einzige Persistenz-Stelle, `backend:'local'`→`'server'` umschaltbar. Server-Bindung ändert nur diese eine Stelle.
- [x] **Ziel-Datenbankschema** (`schema.sql`) – Multi-Tenant (workshops/memberships/app_data) + RLS + Normalisierungs-Roadmap.
- [ ] **Login & Mandanten-Modell** in der App (Werkstatt-Account statt reiner Geräte-PIN) – lokal, echte Auth beim Server-Schritt.
- [ ] **Migrationspfad** v11-State → `app_data`-Blob je Werkstatt.

### F2 · Echte Kern-Funktionen (Server-Logik – kommt mit/nach der Anbindung)
- [ ] GoBD-Beleg-/Rechnungs-Ledger (Hash-Kette) + **TSE** (KassenSichV)
- [ ] **E-Rechnung / ZUGFeRD / Peppol** (Repender-Punkt)
- [ ] Echter **Mail-/SMS-Versand** + **WhatsApp-Status-Kanal** (Repender-Punkt) — *nur nach Freigabe*
- [ ] Öffentliche **API** (Repender-Punkt)

### F3 · Repender-Integrationen (Code hier, Zugänge vom Nutzer)
- [ ] **Foneday-API** — echte Preise + 1-Klick-Bestellung *(braucht Händler-API-Zugang)*
- [ ] **Zahlungsterminal** — SumUp/CCV *(braucht Händler-Konto)*
- [ ] **Hardware** — Barcode-Scanner, Etiketten-/Bondrucker (QZ Tray) *(braucht Geräte)*
- [ ] **Kalender-2-Wege-Sync** — Google/Apple/Outlook *(OAuth-Apps)*
- [ ] **Shopify / Wix** Embed-Ziele *(Widget läuft schon; Doku/Test)*
- [ ] **Mehrsprachigkeit** (DE/EN/NL/IT)

### F4 · Hosting & Launch
- [ ] Deploy (Hosting + echte Domain) · Backups · DSGVO/AVV · Cloud-Multi-User

---

## Was nur der Nutzer beisteuern kann (später)
Supabase-/Cloud-Konto · Foneday-Händler-API-Zugang · Zahlungsterminal-Konto ·
physische Drucker/Scanner · SMTP-/SMS-Zugang · Domain.
→ Ich baue Code + Gerüst; die Zugänge werden lokal (nicht ins öffentliche Repo) eingesteckt.

## Sicherheits-/Repo-Regeln
- Repo `singh-oss/reparado` ist **öffentlich** → **keine echten Keys/Secrets** committen.
- Secrets kommen in lokale Konfiguration außerhalb des Repos.
