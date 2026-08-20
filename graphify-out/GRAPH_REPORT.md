# Graph Report - handy-doc-system  (2026-08-20)

## Corpus Check
- Corpus is ~25,621 words - fits in a single context window. You may not need a graph.

## Summary
- 67 nodes · 81 edges · 12 communities (7 shown, 5 thin omitted)
- Extraction: 67% EXTRACTED · 33% INFERRED · 0% AMBIGUOUS · INFERRED: 27 edges (avg confidence: 0.77)
- Token cost: 219,024 input · 26,282 output

## Community Hubs (Navigation)
- Werkstatt-Backend & Datenmodell
- Roadmap: Wettbewerb & Killer-Wedges
- Kasse, Buchhaltung & Umsatz
- Öffentliche Web-Widgets
- Kunden-Statusseite & Bewertungen
- Auftrags- & Angebots-Flow
- Design-System & Landingpage
- B2B-Verträge (Roadmap)
- Forecast (Roadmap)
- Integrationen (Roadmap)
- Track F: Echtes System
- Versand (Roadmap)

## God Nodes (most connected - your core abstractions)
1. `Aufträge / Orders (auftraege)` - 9 edges
2. `status.html — Kunden-Reparaturstatus` - 8 edges
3. `Repair order data model (S.ord / oDevices / devices)` - 6 edges
4. `Phase 2 — Die 3 Killer-Wedges` - 6 edges
5. `Quiet Precision (Design-Philosophie)` - 5 edges
6. `Empfang / Reception AI (anrufe)` - 4 edges
7. `KI-Diagnose (diagnose)` - 4 edges
8. `Angebote / Quotes (angebote)` - 4 edges
9. `Neuer Auftrag/Angebot Formular (neworder)` - 4 edges
10. `Versicherung / Insurance claims (versicherung)` - 4 edges

## Surprising Connections (you probably didn't know these)
- `anfrage.html — Anfrage-/Rückruf-Wizard` --semantically_similar_to--> `booking.html — Online-Terminbuchung`  [INFERRED] [semantically similar]
  anfrage.html → booking.html
- `index.html — Reparado Landingpage` --semantically_similar_to--> `landing.html — Reparado Landingpage (Variante)`  [INFERRED] [semantically similar]
  index.html → landing.html
- `index.html — Reparado Landingpage` --implements--> `Quiet Precision (Design-Philosophie)`  [INFERRED]
  index.html → DESIGN-PHILOSOPHY.md
- `status.html — Kunden-Reparaturstatus` --implements--> `Öko-Grün Signalfarbe (#0e7a3c)`  [INFERRED]
  status.html → DESIGN-PHILOSOPHY.md
- `status.html — Kunden-Reparaturstatus` --implements--> `Live-Status mit Foto-Updates (L12)`  [INFERRED]
  status.html → ROADMAP.md

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **Repair order lifecycle** — app_anrufe, app_diagnose, app_angebote, app_neworder, app_auftraege, app_bestellungen, app_kasse [INFERRED 0.85]
- **Modules reading/writing the shared S state** — app_state_s, app_localstorage_key, app_auftraege, app_kasse, app_lager, app_buchhaltung, app_versicherung [INFERRED 0.75]
- **Revenue and accounting reporting flow** — app_kasse, app_sales_model, app_buchhaltung, app_statistik, app_vertraege [INFERRED 0.75]
- **Öffentliche kundenseitige Seiten speisen den Haupt-App-Store** — anfrage_wizard, booking_page, status_page, status_reparado_v1_store [INFERRED 0.80]
- **Phase 2 — Die 3 Killer-Wedges** — roadmap_ki_diagnose, roadmap_auto_angebot, roadmap_bewertungs_booster, roadmap_reaktivierung, roadmap_marge [EXTRACTED 1.00]
- **Quiet Precision — Design-Säulen** — design_philosophy_raum_und_form, design_philosophy_farbe_und_material, design_philosophy_skala_und_rhythmus, design_philosophy_komposition_und_balance [EXTRACTED 1.00]

## Communities (12 total, 5 thin omitted)

### Community 0 - "Werkstatt-Backend & Datenmodell"
Cohesion: 0.20
Nodes (12): Ankauf / Verkauf (used-device trade), Bestellungen / Parts orders (bestellungen), Dashboard (Übersicht), Erinnerungen / Reminders (erinnerungen), Kalender (kalender), Kunden / CRM (kunden), Lager & Teile / Inventory (lager), localStorage persistence (KEY / load / save) (+4 more)

### Community 1 - "Roadmap: Wettbewerb & Killer-Wedges"
Cohesion: 0.22
Nodes (11): Auto-Angebot aus Diagnose (L2), Selbst-pflegbarer Katalog (P1), KI-Diagnose / Foto-Diagnose (L1), Echte Marge pro Auftrag (L9), Phase 1 — Fundament des Produkts, Phase 2 — Die 3 Killer-Wedges, Reaktivierung (L5), RepairDash (Wettbewerber) (+3 more)

### Community 2 - "Kasse, Buchhaltung & Umsatz"
Cohesion: 0.27
Nodes (10): Belege / receipts inbox (S.belege), Buchhaltung / Accounting (buchhaltung), POS cart & checkout (cart / checkout / TSE tx), Einstellungen / Settings & Integrations (einstellungen), Kasse / POS (kasse), Nav router (go / views map / canView), Role-based view access (canView / applyNavRole), Sales / TSE receipts (S.sales) (+2 more)

### Community 3 - "Öffentliche Web-Widgets"
Cohesion: 0.32
Nodes (8): localStorage reparado_requests, anfrage.html — Anfrage-/Rückruf-Wizard, booking.html — Online-Terminbuchung, localStorage reparado_bookings, Farbe und Material (disziplinierte Palette, Öko-Grün Signal), Öko-Grün Signalfarbe (#0e7a3c), Website-Widget-Konfig / WordPress-Plugin (P10), localStorage reparado_v1 (Haupt-Store)

### Community 4 - "Kunden-Statusseite & Bewertungen"
Cohesion: 0.25
Nodes (8): Bewertungs-Booster (L6), Garantie-Portal (L15), Live-Status mit Foto-Updates (L12), Digitale Geräte-Akte per QR (L13), status.html — Kunden-Reparaturstatus, localStorage reparado_feedback, localStorage reparado_warranty, Sentiment-Gate (zufrieden→Google / kritisch→intern)

### Community 5 - "Auftrags- & Angebots-Flow"
Cohesion: 0.52
Nodes (7): Angebote / Quotes (angebote), Empfang / Reception AI (anrufe), Aufträge / Orders (auftraege), KI-Diagnose (diagnose), Neuer Auftrag/Angebot Formular (neworder), Modelle & Preise (preise), Versand / Shipping (versand)

### Community 6 - "Design-System & Landingpage"
Cohesion: 0.33
Nodes (6): Komposition und Balance (ruhige Übergänge, zarte Interaktion), Quiet Precision (Design-Philosophie), Raum und Form (Weißraum als Material, 4/8-Punkt-Raster), Skala und Rhythmus (Typografie, tabellarische Ziffern), index.html — Reparado Landingpage, landing.html — Reparado Landingpage (Variante)

## Knowledge Gaps
- **25 isolated node(s):** `localStorage persistence (KEY / load / save)`, `Kalender (kalender)`, `Lager & Teile / Inventory (lager)`, `Versand / Shipping (versand)`, `Belege / receipts inbox (S.belege)` (+20 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **5 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `status.html — Kunden-Reparaturstatus` connect `Kunden-Statusseite & Bewertungen` to `Öffentliche Web-Widgets`?**
  _High betweenness centrality (0.156) - this node is a cross-community bridge._
- **Why does `Phase 2 — Die 3 Killer-Wedges` connect `Roadmap: Wettbewerb & Killer-Wedges` to `Kunden-Statusseite & Bewertungen`?**
  _High betweenness centrality (0.116) - this node is a cross-community bridge._
- **Are the 4 inferred relationships involving `status.html — Kunden-Reparaturstatus` (e.g. with `Öko-Grün Signalfarbe (#0e7a3c)` and `Garantie-Portal (L15)`) actually correct?**
  _`status.html — Kunden-Reparaturstatus` has 4 INFERRED edges - model-reasoned connections that need verification._
- **Are the 2 inferred relationships involving `Repair order data model (S.ord / oDevices / devices)` (e.g. with `Kalender (kalender)` and `Statistik / Forecast (statistik)`) actually correct?**
  _`Repair order data model (S.ord / oDevices / devices)` has 2 INFERRED edges - model-reasoned connections that need verification._
- **What connects `localStorage persistence (KEY / load / save)`, `Kalender (kalender)`, `Lager & Teile / Inventory (lager)` to the rest of the system?**
  _25 weakly-connected nodes found - possible documentation gaps or missing edges._