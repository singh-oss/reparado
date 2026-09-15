# KI-Telefon-Empfangskraft einrichten (Velqio)

Der Bot nimmt Anrufe entgegen, begrüßt den Kunden, beantwortet die 3–4 wichtigsten
Fragen (Öffnungszeiten, Adresse, **Reparatur-Status per Name/Auftragsnummer**) und
nimmt eine **Rückrufbitte** auf – die landet automatisch unter **Angebote → Anfragen**.

Die Antworten kommen von **Claude** (schon verbunden). Für Telefonie + Spracherkennung
brauchst du zwei günstige Dienste. **Komplett kostenlos geht bei echten Anrufen nicht** –
für ~300 Anrufe/Monat realistisch **ca. 5–8 €/Monat**.

---

## Was du brauchst (2 Konten)

### 1) Twilio (Telefonnummer + Anruf-Weiterleitung an Velqio)
1. Konto anlegen: <https://www.twilio.com/try-twilio>
2. Eine **Telefonnummer** kaufen (Phone Numbers → Buy a Number, Voice-fähig).
   Deutsche Ortsnummern brauchen bei Twilio eine Adress-/Regulierungsangabe (Bundle) –
   alternativ eine Nummer nehmen und **deine Werkstatt-Nummer dorthin umleiten**,
   wenn du nicht rangehst / nach Feierabend.
3. Bei der Nummer unter **Voice → „A CALL COMES IN"** eintragen:
   - **Webhook**, **HTTP POST**
   - URL: *die Webhook-URL aus Velqio* (Einstellungen → KI-Telefon-Empfangskraft → „Kopieren")
     — sie lautet `https://velqio.de/api/voice/incoming`
4. Aus dem Twilio-Dashboard notierst du dir **Account SID** (beginnt mit `AC…`) und
   **Auth Token**. (Diese kommen NICHT in Velqio, sondern nur auf den Server – siehe unten.)

**Twilio-Kosten:** Nummer ~1 €/Monat, eingehende Minute ~0,9 Cent. 300 Anrufe × ~1,5 Min ≈ **~5 €/Monat**.

### 2) Deepgram (Spracherkennung – Gratis-Startguthaben)
1. Konto anlegen: <https://console.deepgram.com/signup> (Startguthaben ~200 $ gratis).
2. Einen **API-Key** erstellen und notieren.

**Deepgram-Kosten:** ~0,4 Cent/Minute → 300 Anrufe liegen locker im Gratis-Guthaben,
danach ~2 €/Monat.

---

## Aktivieren (die Schlüssel sicher auf den Server bringen)

Die geheimen Schlüssel dürfen **nicht** in Chat/E-Mail. Nutze das fertige Skript:

1. Doppelklick auf **`Velqio-Telefon-Bot-aktivieren.command`** (auf dem Desktop).
2. Es fragt nach **Twilio Account SID**, **Twilio Auth Token** und **Deepgram API Key**
   (die Eingabe der geheimen Werte ist unsichtbar).
3. Die Werte gehen direkt von deinem Mac auf den Server, `VOICE_ENABLED` wird auf `True`
   gesetzt, der Dienst startet neu. Wenn am Ende **`active`** steht, ist die Technik scharf.

*(Ohne Mac: die Werte in `/opt/reparado/config.py` eintragen —
`VOICE_ENABLED = True`, `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `DEEPGRAM_API_KEY` —
dann `systemctl restart reparado`.)*

---

## In Velqio einstellen

**Einstellungen → 📞 KI-Telefon-Empfangskraft:**
- **Telefonnummer des Bots** = die Twilio-Nummer eintragen.
- **Begrüßung** anpassen (optional).
- **Zusätzliche Infos** eintragen (optional, z. B. „Displaytausch oft am selben Tag").
- Öffnungszeiten & Adresse zieht der Bot automatisch aus den Stammdaten.
- **Speichern** und den **Schalter „Telefon-Bot aktiv"** anschalten.

Danach einmal die Twilio-Nummer anrufen und testen.

---

## Gut zu wissen
- **Sicherheit:** Velqio prüft jede eingehende Anfrage per Twilio-Signatur – nur echte
  Twilio-Anrufe werden angenommen.
- **Status-Auskunft:** Sagt der Kunde seinen Namen oder die Auftragsnummer, liest der Bot
  den echten Reparatur-Status aus Velqio vor.
- **Rückruf:** Versteht der Bot etwas nicht oder will der Kunde einen Menschen, nimmt er
  Name + Anliegen auf → erscheint unter **Angebote** und im Benachrichtigungs-Zähler.
- **Kosten-Kontrolle:** kurzes Modell (Claude Haiku), kurze Antworten, Aufnahme max. 12 Sek.
- **Aus/An** jederzeit über den Schalter in den Einstellungen.
