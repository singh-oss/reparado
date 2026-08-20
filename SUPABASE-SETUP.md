# Reparado live schalten — Supabase-Anbindung (Schritt für Schritt)

Ziel: aus dem Prototyp (Daten nur im Browser) ein echtes System machen —
**geteilte Datenbank, Login, Backup, mehrere Geräte**. Dauer: ~20–30 Min.

> Was du hier machst: das Supabase-Projekt anlegen. Danach schickst du mir
> **3 Werte** (Project URL, anon-Key, Werkstatt-ID) und ich verdrahte + teste den Rest.

---

## 1. Supabase-Projekt anlegen (kostenlos)
1. Auf **https://supabase.com** mit E-Mail registrieren → **New project**.
2. **Name:** z. B. `reparado-dein-handy-doc`.
3. **Region: unbedingt EU** (Frankfurt `eu-central-1` oder Irland) — wegen DSGVO.
4. **Database Password** vergeben und **sicher notieren**.
5. Warten, bis das Projekt fertig provisioniert ist (~2 Min).

## 2. Datenbank-Tabellen anlegen
1. Links im Menü **SQL Editor** → **New query**.
2. Den kompletten Inhalt der Datei **`schema.sql`** (liegt im Projekt) hineinkopieren.
3. **Run** klicken. (Legt `workshops`, `memberships`, `app_data` + Sicherheitsregeln an.)

## 3. Werkstatt-Konto (Login) anlegen
1. Links **Authentication** → **Users** → **Add user** → E-Mail + Passwort der Werkstatt.
   *(Das ist der spätere Login des Shops.)* → **User anlegen**, danach die **User-UID** kopieren.
2. Links **Table Editor** → Tabelle **workshops** → **Insert row**:
   - `name` = Name der Werkstatt (z. B. „Dein Handy Doc")
   - Rest kann leer bleiben → **Save**. Danach die erzeugte **id** (UUID) kopieren.
3. Tabelle **memberships** → **Insert row**:
   - `workshop_id` = die eben kopierte Werkstatt-id
   - `user_id` = die User-UID aus Schritt 3.1
   - `name` = Name der Person, `role` = `inhaber` → **Save**.

## 4. Die 3 Zugangswerte holen
Links **Project Settings** → **API**:
- **Project URL** (z. B. `https://abcd.supabase.co`)
- **anon public** Key (langer `eyJ…`-Text) — **nur den anon-Key**, NICHT den `service_role`!
- Die **Werkstatt-id** (UUID) aus Schritt 3.2

## 5. Mir schicken
Schick mir diese drei Werte:
```
supabaseUrl:  https://….supabase.co
supabaseKey:  eyJ…            (anon/public)
workshopId:   ….-….-….       (Werkstatt-UUID)
```
Ich trage sie lokal in `config.js` ein, **verdrahte + teste die echte Verbindung**
(geteilte Daten laden/speichern, Login) und melde mich, sobald es live läuft.

---

## Wichtig / ehrlich
- **anon-Key** ist fürs Frontend gedacht und darf öffentlich sein — die **Row Level
  Security** (aus `schema.sql`) schützt die Daten serverseitig. Der **`service_role`-Key
  gehört NIRGENDWO ins Frontend/Repo.**
- **Echte Kundennachrichten** (E-Mail/SMS/WhatsApp) kommen als **zweiter Schritt**: die
  laufen server-seitig über **Supabase Edge Functions** (Zugangsdaten sicher in Supabase),
  damit keine Passwörter im Frontend liegen. Dafür brauche ich später SMTP-/SMS-/WhatsApp-Zugänge.
- **DSGVO:** Sobald ein echter Shop mit echten Kundendaten testet, braucht ihr einen
  **Auftragsverarbeitungsvertrag (AVV)** zwischen deiner Firma und dem Shop. Vorlage bereite ich vor.
