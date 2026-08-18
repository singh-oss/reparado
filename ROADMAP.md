# Reparado — Produkt-Roadmap

> **Positionierung:** RepairDash ist ein **Verwaltungs-System** (dokumentiert, was der Shop tut).
> Reparado wird ein **Mitarbeiter** (erledigt Arbeit + bringt Umsatz) — dank KI-Diagnose & KI-Empfangskraft, die RepairDash fehlen.
> **Ziel:** erst Parität bei den Basics, dann per KI/Marge/Bindung an RepairDash **vorbeiziehen**.

**Stand:** 18.8.2026 · Quelle: kompletter RepairDash-Durchgang (Lücken-Analyse) + „Besser-als"-Ideation.

---

## Legende
- **Effort:** S = klein (Std./1 Tag) · M = mittel (Tage) · L = groß (Woche+)
- **Impact:** ★★★ sehr hoch · ★★ hoch · ★ solide
- **Typ:** `[Parität]` = RepairDash einholen · `[Leap]` = besser werden · `[Fundament]` = echtes System
- **Status im Prototyp:** vieles wird zuerst **client-seitig/simuliert** gebaut (Demo-tauglich), später im echten System gehärtet.

---

## 🎯 Now / Next / Later (Kurzüberblick)

**NOW — Phase 1 + 2 (Fundament-Basics + die 3 Killer-Wedges)**
Katalog selbst pflegen · konfigurierbare Status+Automatik · Foto-Diagnose → Auto-Angebot · Bewertungs-Booster · Reaktivierung · echte Marge.

**NEXT — Phase 3 + 4**
Warenwirtschaft & Teile-Intelligenz · Kundenerlebnis (Live-Fotos, QR-Akte, Self-Check-in) · Widget-Konfig · Auftragslisten-/Kassen-Politur.

**LATER — Phase 5 + Track F**
Wachstums-Motoren (Versandreparatur, B2B, Forecast) · **Echtes System** (DB, Auth, TSE, E-Rechnung, Hosting).

---

## Phase 1 — Fundament des Produkts (schaltet alles andere frei) — ✅ KOMPLETT (18.8.)
*Die erste Frage jedes Shops: „Kann ich meine eigenen Preise/Abläufe einstellen?"*

| # | Feature | Typ | Effort | Impact | Abhängig |
|---|---|---|---|---|---|
| ✅ P1 | **Selbst-pflegbarer Katalog** — Gerätetypen→Marken→Modelle, Reparaturarten, Basispreise, Preise pro Modell überschreibbar, Qualitätsoptionen, **Modellbilder (B3)** · **FERTIG 18.8.** | Parität 🔴 | L | ★★★ | — (Basis für Preise, Angebote, Widget) |
| ✅ P3 | **Konfigurierbare Status + Automatisierungen** — Status anlegen/sortieren/Farbe/aktivieren, je Status Auto-E-Mail/SMS mit Vorlage · **FERTIG 18.8.** | Parität 🔴 | M–L | ★★★ | — |
| ✅ P8 | **Systemeinstellungen** — Nummernschema (REP-/AN-), Pflichtfelder (E-Mail/Adresse/IMEI/Unterschrift), AGB-Text auf Beleg · **FERTIG 18.8.** | Parität 🟠 | S–M | ★★ | — |
| ✅ P12 | **Auftragsliste-Politur** — Inline-Status (farbig), Sortierung, Bulk-Auswahl, **Archiv**, **Papierkorb** (+Wiederherstellen/endgültig löschen) · **FERTIG 18.8.** | Parität 🟡 | M | ★★ | — |

## Phase 2 — Die 3 Killer-Wedges (das Wow, das verkauft) — ✅ KOMPLETT (18.8.)
*Nutzt euren KI-Vorsprung — RepairDash kann das nicht.*

| # | Feature | Typ | Effort | Impact | Abhängig |
|---|---|---|---|---|---|
| ✅ L1 | **📸 Foto-Diagnose** — Gerät fotografieren → KI erkennt Schaden, schlägt Reparatur+Teil+Preis vor · **FERTIG 18.8.** (Sim/Prototyp) | Leap ★ | M | ★★★ | erweitert KI-Diagnose |
| ✅ L2 | **⚡ Auto-Angebot aus Diagnose** — Diagnose/Foto → 1-Klick fertiges Angebot (Gerät/Reparatur/Preis vorbefüllt) · **FERTIG 18.8.** | Leap ★ | M | ★★★ | P1, L1 |
| ✅ L6 | **⭐ Bewertungs-Booster** — Statusseite mit Sentiment-Gate (zufrieden→Google, kritisch→intern), Feedback-Inbox, Dashboard-Karte · **FERTIG 18.8.** | Leap | S–M | ★★★ | — |
| ✅ L5 | **🔁 Reaktivierung** — KI-Chancen (Garantie endet / Akku fällig / lange nicht da) in CRM, Ansprechen/Alle anschreiben · **FERTIG 18.8.** | Leap | M | ★★★ | — |
| ✅ L9 | **💰 Echte Marge pro Auftrag** — Preis − Teilekosten (EK aus Lager) − Arbeitszeit = Gewinn €/%, Verlust rot; Statistik-Kennzahlen · **FERTIG 18.8.** | Leap | M | ★★★ | Teilekosten aus P2 |

## Phase 3 — Warenwirtschaft & Teile-Intelligenz — ✅ KOMPLETT (18.8.)
*Zusammenhängender Block; Marge & Bestellungen hängen daran.*

| # | Feature | Typ | Effort | Impact | Abhängig |
|---|---|---|---|---|---|
| ✅ P2 | **Warenwirtschaft** — Kategorien, Wareneingang, Inventur, Lagerbewegungen, Lieferanten, Lagerwert, niedrige Bestände (EK/VK) · **FERTIG 18.8.** (offen: Eingangsrechnungen/IMAP → mit Buchhaltung) | Parität 🔴 | L | ★★★ | — |
| ✅ P5 | **Bestellwesen** — Lager- vs. Kundenbestellung, Lieferant, Bestellliste drucken, Filter/Status/Priorität, Eingang→Lager, Nachbestellen bei Unterbestand · **FERTIG 18.8.** | Parität 🟠 | M | ★★ | P2 |
| ✅ L10 | **🔎 Ersatzteil-Preisvergleich** über Lieferanten + Preishistorie · **FERTIG 18.8.** | Leap | M | ★★ | P2 |
| ✅ L11 | **♻️ Auto-Nachbestellung** bei niedrigem Bestand (Setting + Sammelknopf) · **FERTIG 18.8.** | Leap | S | ★★ | P2 |
| ✅ P6 | **Ankauf/Verkauf-Tiefe** — Zustand, Profit €/%, Status verfügbar/reserviert/verkauft, Lagerwert, Filter · **FERTIG 18.8.** | Parität 🟠 | M | ★ | — |
| ✅ P4 | **Wunsch-Handy-Liste** — Kundenmerkliste + Auto-Treffer bei Ankauf · **FERTIG 18.8.** | Parität 🟠 | S | ★ | P6 |

## Phase 4 — Kundenerlebnis & Alltags-Politur
*Bindung + die restliche Parität.*

| # | Feature | Typ | Effort | Impact |
|---|---|---|---|---|
| ✅ L12 | **🖼️ Live-Status mit Foto-Updates** (Werkstattfotos auf der Kunden-Statusseite) · **FERTIG 18.8.** | Leap | M | ★★ |
| ✅ L13 | **📱 Digitale Geräte-Akte per QR** (QR im Drawer + Reparatur-Historie auf Statusseite) · **FERTIG 18.8.** | Leap | M | ★★ |
| ✅ L14 | **🖥️ Self-Check-in-Terminal** (Vollbild-Selbstannahme + Unterschrift → Auftrag) · **FERTIG 18.8.** | Leap | S–M | ★★ |
| ✅ L15 | **🛡️ Garantie-Portal** (Kunde sieht Garantie, meldet Fall → Dashboard-Inbox) · **FERTIG 18.8.** | Leap | M | ★ |
| ✅ L7 | **📦 „Nicht abgeholt"-Workflow** (eskalierende Stufen + Lagergebühr) · **FERTIG 18.8.** | Leap | S–M | ★★ |
| ✅ L8 | **🛒 Upsell an der Kasse** (Zubehör bei Reparatur im Warenkorb) · **FERTIG 18.8.** | Leap | S | ★ |
| ✅ B2 | **Fotos am Auftrag** (Upload+Galerie im Drawer, aus Diagnose übernommen) · **FERTIG 18.8.** | Leap | S–M | ★★ |
| L18 | **⚖️ Rechtssichere digitale Übergabe** (Datenverlust-Waiver/DSGVO signiert) | Leap | S | ★★ |
| L4 | **💬 Proaktive Kundenkommunikation** (Empfangskraft treibt aktiv) | Leap | M | ★★ |
| ✅ L3 | **🔧 Techniker-Playbook** (KI-Reparaturanleitung je Reparaturart im Auftrag) · **FERTIG 18.8.** | Leap | M | ★★ |
| ✅ L16 | **🧠 KI-Tagesbriefing** (Chef-Cockpit auf dem Dashboard, GF-only) · **FERTIG 18.8.** | Leap | M | ★★ |
| P10 | **Repair-Widget-Konfig** — Preise/Styling, iframe-Embed, **WordPress-Plugin**, Standardpreise | Parität 🟠 | M–L | ★★ |
| ✅ P14 | **Kasse-Politur** — editierbarer Artikelkatalog + Kategorien, Meistverkauft, Verwalten · **FERTIG 19.8.** (Scan via Suche) | Parität 🟡 | M | ★ |
| ✅ P13 | **Kunden-Politur** — Suche, A→Z-Sortierung, Pagination · **FERTIG 18.8.** | Parität 🟡 | S | ★ |
| ✅ P16 | **Detaillierte Statistik** — Monatsvergleich (Trend) + Ankauf/Verkauf/Handels-Marge · **FERTIG 19.8.** | Parität 🟡 | S–M | ★ |
| ✅ P15 | **Top-Bar-Werkzeuge** — Scanner-Fokus, Schnell-Kasse, Benachrichtigungs-Zähler · **FERTIG 18.8.** | Parität 🟡 | S | ★ |
| ✅ P9 | **Benutzer & Berechtigungen granular** (Mitarbeiter-Zugriff je Bereich einstellbar) · **FERTIG 19.8.** | Parität 🟠 | M | ★ |
| ✅ P7 | **Benachrichtigungen** — SMTP-Konfig + SMS-Gateway (Vorlagen via Erinnerungen/Status) · **FERTIG 19.8.** | Parität 🟠 | M | ★★ |

## Phase 5 — Wachstums-Motoren
| # | Feature | Typ | Effort | Impact |
|---|---|---|---|---|
| L20 | **📮 Versandreparatur end-to-end** (Prepaid-Label, Tracking, Fernannahme) | Leap | M–L | ★★ |
| L21 | **🏢 B2B-Verträge** (Gerätepools, SLA, Monatsabrechnung — wiederkehrender Umsatz) | Leap | L | ★★ |
| L17 | **📈 Forecast + Filial-Benchmark** (Franchise) | Leap | M | ★ |
| L19 | **🏥 Mehr Versicherer** neben Wertgarantie + Direktabrechnung | Leap | M | ★ |
| P11 | **Integrationen** — HelloCash, SumUp, Lexware, Google Bewertungen | Parität 🟠 | M | ★ |

---

## 📷 Fotos & Dokumentation (alle Bild-Funktionen an einem Ort)
*Bilder sind in einer Werkstatt zentral — Haftung, Vertrauen, Diagnose, Katalog. Hier alle Foto-Touchpoints gebündelt.*

| # | Feature | Typ | Phase | Effort | Impact | Warum wichtig |
|---|---|---|---|---|---|---|
| B1 | **Zustandsfotos bei Annahme** — Gerät bei Abgabe fotografieren (Kratzer/Dellen/Risse), am Auftrag gespeichert, auf dem Annahmebeleg vermerkt | Leap ★ | 2 | S–M | ★★★ | **Haftungsschutz** — Kunde kann später keinen Vorschaden reklamieren. Standard bei guten Shops. |
| L1 | **📸 Foto-Diagnose (KI)** — Schaden fotografieren → KI erkennt Reparatur+Teil+Preis | Leap | 2 | M | ★★★ | Schnelles Angebot, online & an der Theke |
| B2 | **Fotos am Auftrag (Vorher/Nachher, Schaden, Zubehör)** — beliebig viele Bilder je Auftrag, Galerie im Auftrag | Leap | 3 | S–M | ★★ | Beweis der Arbeit, interne Doku, Zubehör-Nachweis |
| L12 | **🖼️ Live-Status mit Foto-Updates** — Kunde sieht Technikerfotos auf der Statusseite | Leap | 4 | M | ★★ | Vertrauen, killt „ist-es-fertig"-Anrufe |
| B3 | **Modell-/Produktbilder** — Bild je Gerätetyp/Modell/Ersatzteil; **angezeigt beim Modell-Auswählen** (Auftragsformular + Buchungs-/Anfrage-Widget) und in Kasse & Lager | Parität | 1–3 | S–M | ★★ | visuelle, schnellere Geräteauswahl (wie RepairDash) + Erkennung an Kasse/Lager |
| ✅ B4 | **Logo** — eigenes Logo auf Belegen/Angeboten/KVA/Garantie (Upload in Stammdaten) · **FERTIG 19.8.** | Parität | 1 | S | ★ | Marken-Auftritt |
| ✅ B5 | **Foto beim Ankauf** (Gerät/Ausweis/Kaufbeleg → Ident-/Herkunftsnachweis) · **FERTIG 19.8.** | Leap | 3 | S | ★★ | **Rechtssicherheit Ankauf** |

> **Technik-Hinweis:** Im Prototyp werden Bilder als Data-URL in localStorage gehalten (klein/komprimiert). Im echten System → Supabase Storage (Track F1), mit Thumbnails.

---

## Track F — Echtes System (parallel, sobald echte Kunden/echtes Geld)
*Bis dahin bleibt alles Prototyp/simuliert. Reihenfolge F1→F2 zuerst. Bauplan existiert bereits im **Agenten-Büro**.*

| # | Baustein | Effort | Warum |
|---|---|---|---|
| F1 | **Datenbank/Backend (Supabase)** — localStorage → echte DB, Multi-User-Sync, Backup | L | ohne das kein echter Mehrplatz-Betrieb |
| F2 | **Auth + server-seitige Rollen (RLS)** — Login sicher, „Techniker sieht kein Umsatz" wirklich durchgesetzt | M | Sicherheit |
| F3 | **Mail/SMS-Versand real** (SMTP + SMS-Gateway) | M | schaltet alle Auto-Nachrichten scharf |
| F4 | **Echte TSE** (fiskaly) — KassenSichV-konform | M | gesetzlich Pflicht |
| F5 | **Buchhaltung/E-Rechnung/DATEV** (aus Agenten-Büro übernehmen) | M | GoBD, echte Rechnungen |
| F6 | **Hosting/Deploy** (Hetzner + Caddy + systemd, wie Agenten-Büro) | S–M | 24/7-Betrieb |

---

## Sofort-Empfehlung (wenn nur ein Block)
**Phase 1 (Katalog + Status/Automatik) + die 3 Wedges aus Phase 2 (Foto-Diagnose→Auto-Angebot, Bewertungs-Booster, Reaktivierung).**
Das gibt dem Partner beides: „ich kann es an meinen Shop anpassen" **und** „das bringt mir Geld, was RepairDash nicht kann."

## Bereits erledigt (Fundament steht schon)
Auftragserstellung (Mehrgeräte, Entwurf-Autospeicherung) · Angebote + Website-Anfragen · Benutzer/Rollen (Prototyp) · Wertgarantie-Modul · KI-Diagnose · KI-Empfangskraft (Telefon/WhatsApp) · Kasse+TSE (simuliert) · Buchhaltung EÜR/USt/DATEV (simuliert) · Kiosk-/QR-Unterschrift · Online-Buchung.
