# Businessplan – SimpleFinanceManager (Finanzmanager)

> Arbeitsdokument, Stand 2026-06-13. Lebt mit dem Projekt – bei Entscheidungen aktualisieren.
>
> ⚠️ **Kein Rechts- oder Steuerberatung.** Die rechtlichen Punkte sind nach bestem Wissen
> recherchiert (Quellen am Ende), ersetzen aber vor dem ersten kommerziellen Verkauf **nicht**
> eine einmalige Beratung bei (a) Steuerberater/IHK zur Gründung und (b) einer IT-Recht-Kanzlei
> für Shop-AGB/Widerruf/Update-Zusage. Beides zusammen ist Geld, das Laienfehler verhindert.

---

## 0. Leitplanke (unverhandelbar)

**Kein SaaS.** Das Produkt bleibt user-hosted: Jeder Nutzer greift mit *eigenen* Zugangsdaten auf
*seine eigene* Bank zu, auf *eigener* Hardware. Damit bleibt es ein **Softwareprodukt** (wie
Lexware/StarMoney/MoneyMoney/Hibiscus) und **kein** regulierter Kontoinformationsdienst (AISP).
Ein zentral gehosteter Multi-Tenant-Dienst würde BaFin-Erlaubnis (§ 34 ZAG),
Berufshaftpflicht/Anfangskapital, DORA-IT-Compliance und das Halten fremder Bankdaten bedeuten –
bewusst ausgeschlossen. Details siehe Abschnitt 7.

---

## 1. Produkt & Zielgruppe

**Was es ist:** Selbst-gehosteter Finanzmanager für deutsche Privathaushalte. CSV- und
FinTS/HBCI-Import, automatische Kategorisierung (Regeln/Regel-Sets), tiefe Kategorien, Budgets,
Splitbuchungen, Umbuchungserkennung, Haushalts-/Gemeinschaftsauswertung, Statistiken, Backup/Restore.

**Nische / Alleinstellung:** „Self-hosted Web-UI + natives FinTS + deutsch + lokal" ist unbesetzt.
- Firefly III / Actual: schwache deutsche Bankanbindung.
- Hibiscus: funktional, aber altbackene Java-Desktop-UI.
- MoneyMoney: nur macOS.
- Finanzguru/Outbank: Cloud/Mobile, nicht self-hosted, nicht datensouverän.

**Zielgruppe:** Datenschutzbewusste, technisch interessierte Privatleute in DE, die ihre Finanzen
nicht einer Cloud anvertrauen wollen; Self-Hosting-Community (NAS/Homeserver-Nutzer); Haushalte,
die gemeinsame Ausgaben tracken wollen. **Realistische Marktgröße: Hunderte bis niedrige Tausende**,
nicht Zehntausende. → Planung als Portfolio-/Community-Projekt mit Monetarisierungs-Option, nicht
als Vollzeit-Einkommen.

---

## 2. Vertriebsmodell – zwei Produktlinien aus *einer* Codebasis

Architektonischer Glücksfall: Backend ist ein Webserver mit REST-API. Die „Desktop-App" ist nur
der **verpackte Server**. Daraus zwei Vertriebslinien, beide aus demselben Code:

### Linie A – „Desktop" (für Normalnutzer)
- **Auslieferung:** installierbares Paket (Windows `.exe`/Installer via pywebview/Tauri um den
  FastAPI-Server + SQLite), Download über eigene Website.
- **Featureset-Stufen (eine Code-Basis, per Konfiguration):**
  - **A1 „Solo":** alles lokal, nur eigene Ausgaben, kein Mehrnutzer/Haushalt. Bindet auf
    `127.0.0.1`. Einfachste, „verständlichste" Variante.
  - **A2 „Haushalt im LAN":** identischer Server, bindet aufs lokale Netz → andere Geräte/Personen
    im selben WLAN können mitnutzen (Haushaltsfeatures), **solange der PC läuft**.
- **Companion-App:** für Linie A weitgehend **unnötig** (man sitzt am PC). Optional als PWA, wenn A2
  genutzt wird und jemand vom Handy im selben WLAN draufschauen will.
- **Preis:** Einmalkauf **pro Major-Version** (MoneyMoney-Modell, siehe Abschnitt 4) –
  **keine** „Lifetime"-Zusage (siehe Update-Pflicht, Abschnitt 6).

### Linie B – „Self-hosted Server" (für Tech-affine / Haushalte)
- **Auslieferung:** Docker-Image / Compose. Läuft auf NAS, Homeserver, Mini-PC.
- **Featureset:** **voll** – Mehrnutzer, Haushalt mit echter Datentrennung, Companion-App (PWA →
  später nativ), Backup/Restore, FinTS, Zugriff von unterwegs **per VPN** (WireGuard/Tailscale),
  **nie durch Exposen**.
- **Companion-App:** hier das **Killer-Feature** – ein Client gegen den einen Server, kein
  Sync-Problem, Haushalt funktioniert.
- **Preis/Lizenz:** hängt an der Lizenzentscheidung (Abschnitt 3). Bei OSS faktisch gratis
  self-hostbar → Monetarisierung über Convenience/Support/Spenden, nicht über den Server-Download
  selbst.

**Haushalt/Sync-Logik (Kernprinzip, festhalten):** Gemeinsame Features brauchen *einen*
gemeinsamen Datenbestand. Den liefert der Server (Linie B) oder der laufende PC (Linie A2). Es gibt
**keinen** Geräte-zu-Geräte-Sync zwischen Einzelinstallationen – das ist das schwierigste Problem
überhaupt und wird nicht gebaut. Wer Multi-Device + Haushalt will, nimmt Linie B.

---

## 3. Lizenz- & Monetarisierungsmodell

> **Entscheidung 2026-06-13: AGPL-3.0 + Convenience-Monetarisierung (Option A).**
> Echtes OSS – die Docker-/Self-hosted-Version ist gratis self-hostbar; Code öffentlich (AGPL
> schützt gegen geschlossene Fremd-Kommerzialisierung & SaaS-Trittbrettfahrer). **Geld kommt nicht
> aus dem Server-Download**, sondern aus Bequemlichkeit/Service: fertige signierte Desktop-App
> (Linie A, Major-Version-Kauf), optional Support, Spenden, „pay what you want".
> **Folge-To-dos:** DCO/CLA aufsetzen **vor** dem ersten externen PR (sonst keine spätere
> Dual-License/kommerzielle Desktop-Variante möglich); `LICENSE` von MIT → AGPL-3.0 ändern, **bevor**
> das erste Public-Repo entsteht.

### Begriffsklärung (wichtig – häufiger Denkfehler)
- **Open Source** heißt per Definition: Nutzung (auch kommerziell) ist **erlaubt**. „Offen
  bereitstellen, aber Nutzung verbieten" ist **kein** Open Source.
- Was „Code sichtbar, Nutzung beschränkt" meint, heißt **Source Available** (z. B. Business Source
  License) oder schlicht **proprietär mit einsehbarem Code**.

### Die realistischen Optionen

| Modell | Was es bedeutet | Monetarisierung | Haken |
|---|---|---|---|
| **A) AGPL-3.0 (echtes OSS)** ⭐ | Jeder darf nutzen & selbst hosten, auch gratis. Änderungen/SaaS müssen offengelegt werden. | Bezahlte **Convenience** (fertige signierte Desktop-App, 1-Klick-Installer), Support, Spenden, „pay what you want". | Die Docker-Version ist faktisch **gratis** kopierbar/hostbar. Geld kommt aus Bequemlichkeit & gutem Willen, nicht aus dem Server-Download. |
| **B) Source Available (z. B. BSL 1.1)** | Code öffentlich einsehbar, aber Lizenz **beschränkt** Nutzung (z. B. „nicht kommerziell" / „nur mit gekauftem Schlüssel"); wandelt sich oft nach X Jahren in OSS. | Direkter Verkauf von Lizenzschlüsseln für **beide** Linien möglich. | Nicht „echtes" OSS → Community-Goodwill geringer; Durchsetzung gegen Hobby-Nutzer praktisch schwer. |
| **C) Open Core** | Kern OSS (AGPL), einzelne Premium-Features proprietär/kostenpflichtig. | Gratis-Kern zieht Nutzer, Geld über Premium-Module. | Du musst Features bewusst „hinter die Paywall" legen – Community-Reibung. |
| **D) Closed Source** | Code nicht öffentlich. | Klassischer Softwareverkauf beider Linien. | Verliert das „datensouverän/auditierbar"-Argument, das gerade deine Zielgruppe schätzt. |

### Dual Licensing (nur möglich, solange du Alleinurheber bist)
Solange **du** alle Rechte hältst, kannst du z. B. AGPL **öffentlich** + **kommerzielle** Lizenz an
Zahler parallel anbieten (GitLab/MongoDB-Modell). **Sobald fremde Beiträge reinkommen**, brauchst
du **CLA/DCO** (Contributor License Agreement / Developer Certificate of Origin), sonst verlierst du
diese Freiheit. → **Vor** dem ersten externen PR aufsetzen.

### Gewählter Weg (siehe Kasten oben): AGPL-3.0 + DCO
- **Realistische Erlösbasis bei OSS:** Spenden/Convenience = Biergeld bis niedrige Hunderte/Jahr.
  Nennenswertes Geld nur über **bezahlte Desktop-App (Linie A)** im Major-Version-Modell, und nur
  bei nachgewiesener Nachfrage. SaaS (das einzige „Skalierungs"-Modell) ist ausgeschlossen.
- **Warum AGPL und nicht MIT:** verhindert, dass jemand das Tool als geschlossenes Konkurrenz-SaaS
  betreibt, ohne Änderungen offenzulegen. Als Alleinurheber (mit DCO/CLA für künftige Beiträge)
  darfst du parallel eine **kommerzielle** Lizenz für die Desktop-App vergeben (Dual Licensing).

---

## 4. Preismodell – warum **kein** „Lifetime"

Banking-Software hat **dauerhafte** Wartungskosten (Bank-Schnittstellen ändern sich, TAN-Verfahren,
PSD2→PSD3, VOP-Pflicht seit 10/2025). Quicken/Lexware sind genau deshalb auf Abo umgestiegen
(bei Quicken zusätzlich teure Aggregations-Server, die wir **nicht** haben). Eine Lifetime-Lizenz
verkauft das Versprechen ewiger Bankanbindungs-Pflege für eine Einmalzahlung – die Rechnung geht
nicht auf.

**Empfehlung: MoneyMoney-Modell** – Kauf **pro Major-Version**. Bankanbindung wird für die gekaufte
Version gepflegt; der nächste große Versionssprung kostet erneut. Ehrlich, kundenfreundlich, deckt
die Wartung, **begrenzt zugleich die rechtliche Update-Pflicht** (Abschnitt 6).
Alternative: Abo (deckt Wartung am saubersten, aber Self-Hoster-Community ist abo-allergisch).

---

## 5. FinTS / Bankenabdeckung – Fakten & offene Punkte

### Wie viele Banken? Welche testen?
- **~3.000 Kreditinstitute** in DE sind über **FinTS 3.0** erreichbar (Großteil aller Banken/Sparkassen).
- **Du musst nicht alle testen.** Die FinTS-Implementierung steckt in `python-fints`; die
  protokollarische Last liegt dort. Dein Job ist, dass die **Produkt-ID** akzeptiert wird und der
  **TAN-Flow** über die gängigen Verfahren funktioniert. Pragmatischer Abdeckungsplan:
  - **Bankrechenzentren statt Einzelbanken denken:** Die meisten Banken laufen über wenige
    Backends – **Atruvia** (Volksbanken/Raiffeisen, ~800 Institute, EINE Plattform), **Finanz
    Informatik** (Sparkassen, ~350 Institute, EINE Plattform), dazu die großen Direktbanken
    (ING, DKB, Comdirect, …) mit eigenen Servern. Wer **Atruvia + FI + 2–3 Direktbanken** grün hat,
    deckt faktisch den Großteil der Privatkonten ab.
  - **Status heute:** ING (verifiziert) + Volksbank/Atruvia (verifiziert). → Sparkasse/FI ist der
    nächste hochwertige Test (größte Gruppe). Scalable Capital wäre Eigenbestand-Test.
  - **Realistisches Testziel vor „zuverlässig"-Aussage:** je 1 Konto pro großem Rechenzentrum
    (Atruvia ✔, FI offen) + 2–3 große Direktbanken. ~5–6 erfolgreiche Banken erlauben die ehrliche
    Aussage „funktioniert mit den meistgenutzten deutschen Banken" – **nicht** „mit allen".
- **Marketing-Sprache:** nie „unterstützt alle Banken", sondern „unterstützt Banken mit
  FinTS/HBCI-Zugang; getestet mit X, Y, Z". Banken ohne FinTS (einige Neobanken wie N26) gehen
  technisch nicht.

### Sind die FinTS-Zugangs-URLs öffentlich?
- Es gibt eine **offizielle DK-Bankenliste** (BLZ → FinTS-URL + Parameter). Diese ist **nur für
  registrierte Produkteigner** zugänglich – **du gehörst dazu** und bekommst sie als Anlage per
  Mail über den FinTS-Verteiler (war Teil deiner Registrierung). → Diese Liste als Datenquelle für
  einen Bank-Auswahldialog nutzen (BLZ eingeben → URL automatisch). **Nicht öffentlich
  weiterverteilen** (Verteiler-Bedingungen beachten).
- Es kursieren inoffizielle Listen, aber die offizielle, aktuelle ist der saubere Weg.

### Das „> 3 Monate"-Limit – Entwarnung, kein hartes Limit
- Das ist die **PSD2-SCA-90-Tage-Regel**, kein technisches Maximum: Für Umsätze **älter als 90
  Tage** verlangt die Bank eine **TAN** (Starke Kundenauthentifizierung). Laufende Abrufe der
  letzten 90 Tage gehen je nach Bank **ohne** erneute TAN.
- **Konsequenz fürs Produkt:** Beim **Erstimport** (volle Historie) einmal eine TAN-Abfrage über
  > 90 Tage triggern (HKCAZ-Zeitraum > 90 Tage) → liefert die Altdaten **und** setzt den
  90-Tage-Timer zurück. Danach laufende Syncs < 90 Tage meist TAN-frei. Der bestehende TAN-Flow
  deckt das ab → als „Vollständigen Verlauf abrufen (TAN nötig)"-Option in die UI bauen.

---

## 6. Rechtliche Pflichten beim Software-Vertrieb (B2C, Deutschland)

### 6.1 Unternehmensform
- **Gewerbeanmeldung Pflicht**, sobald Verkauf mit Gewinnerzielungsabsicht – **auch nebenberuflich**,
  unabhängig von der Höhe. Anmeldung beim **Gewerbeamt**.
- **Einfachster Start: Einzelunternehmen / Kleingewerbe.** Günstig, schnell, wenig Bürokratie.
  - **Kleinunternehmerregelung (§ 19 UStG):** keine Umsatzsteuer ausweisen, solange unter den
    Umsatzgrenzen → einfache Buchhaltung (EÜR). Sinnvoll für den Start.
  - **IHK-Mitgliedschaft** wird mit der Gewerbeanmeldung automatisch fällig (Beiträge bei kleinem
    Umsatz gering/teils erlassen).
- **UG/GmbH** erst, wenn **Haftungsbegrenzung** wichtig wird (sobald echtes Umsatz-/Haftungsvolumen).
  Mehr Kosten (Notar, Bilanzierung). Für den Start **überdimensioniert** – Einzelunternehmen +
  gute Haftungsklauseln + Berufshaftpflicht (optional) reicht zunächst.
- **Haftungsrisiko bei Finanzsoftware bedenken:** Wenn die Software falsche Salden anzeigt o. Ä.,
  Haftung über AGB begrenzen (kein Anspruch auf Richtigkeit der Bankdaten, „as is" im rechtlich
  zulässigen Rahmen – bei B2C nicht vollständig ausschließbar!). Hier lohnt anwaltlicher Blick.

### 6.2 Pflichten der Verkaufs-Website / des Shops
- **Impressum** (§ 5 DDG, ex-TMG): Pflicht auf jeder geschäftsmäßigen Website. Bei
  Einzelunternehmen mit **ladungsfähiger Anschrift** (Privatadresse, falls kein Geschäftssitz) –
  das ist ein realer Privatsphäre-Punkt (siehe 6.5).
- **Datenschutzerklärung (DSGVO):** Pflicht (Server-Logs, Zahlungsabwicklung, evtl. Newsletter).
- **AGB:** nicht zwingend, aber dringend empfohlen (regeln Lizenz, Haftung, Update-Umfang).
- **Widerrufsbelehrung + Widerrufsrecht (Fernabsatz, B2C):**
  - Verbraucher haben grundsätzlich **14 Tage Widerruf**.
  - Bei **digitalen Inhalten** (Download) **erlischt** das Widerrufsrecht **nur**, wenn **alle drei**
    erfüllt sind: (1) Kunde stimmt **ausdrücklich** zu, dass die Ausführung **vor** Fristende
    beginnt, (2) bestätigt, dass er dadurch sein Widerrufsrecht **verliert**, (3) erhält eine
    **Bestätigung auf dauerhaftem Datenträger** (z. B. E-Mail). Fehlt eines → Widerrufsrecht bleibt,
    auch nach Download. → **Kaufprozess sauber bauen** (Checkbox + Bestätigungs-Mail), sonst können
    Käufer nach Download zurücktreten und Geld zurückverlangen.
- **Zahlungsabwicklung:** Über einen **Reseller/Merchant of Record** (z. B. Paddle, Lemon Squeezy,
  FastSpring) abwickeln → die übernehmen **Umsatzsteuer (MOSS/OSS), Rechnungen, EU-weite
  Steuerpflichten** und treten als Verkäufer auf. Das spart enorm Bürokratie und löst das
  USt-Thema bei EU-Auslandsverkäufen. Alternative: Stripe/PayPal selbst + Steuerberater.

### 6.3 Update-/Gewährleistungspflicht (digitale Produkte, §§ 327 ff. BGB)
- Seit 01.01.2022: Bei B2C-Verkauf **Aktualisierungspflicht** – Updates, die die
  **Vertragsmäßigkeit** erhalten (inkl. **Sicherheitsupdates**), für den Zeitraum, den der
  Verbraucher „nach **Art und Zweck**" erwarten darf. **Keine feste Dauer, nicht „für immer".**
  - Einmalkauf → angemessener Zeitraum (bei langlebiger Software typ. einige Jahre).
  - Abo → für die Dauer des Abos.
- **Steuerung der Pflicht über Erwartung:** Major-Version-Modell + klare Ansage beim Kauf
  („Bankanbindung für Version X gepflegt mindestens bis JJJJ-MM") definiert und **begrenzt** den
  erwartbaren Zeitraum rechtssicher.
- **Aufhören ist erlaubt** – nach angemessenem Zeitraum und mit klarer Kommunikation. **Sofortiges
  ersatzloses Einstellen kurz nach Verkauf** wäre Pflichtverletzung (Minderung/Rücktritt möglich).
- **Reines kostenloses OSS:** keine Update-Pflicht (MIT/AGPL „as is, no warranty"). Pflicht entsteht
  erst mit dem **Verkauf** an Verbraucher.

### 6.4 „Stop Killing Games" / Produktabschaltung – Einordnung
- Betrifft **aktive Remote-Abschaltung** (Server aus → Produkt tot). **Trifft dich strukturell
  nicht:** lokal laufende Software wird nicht abgeschaltet, sie altert höchstens passiv (eine
  Bank ändert ihre Schnittstelle). EU-Kommission gibt am **16.06.2026** ihre Antwort auf die
  Bürgerinitiative – beobachten, aber für lokal/self-hosted absehbar irrelevant.
- **OSS erfüllt den Geist automatisch:** Auch nach deinem Ausstieg bleibt der Code forkbar/reparierbar
  → starkes Vertrauens- und Marketingargument.

### 6.5 Privatsphäre des Gründers (konkreter Handlungsbedarf)
- **Impressum + ladungsfähige Anschrift** legen deine **Privatadresse** offen, falls kein separater
  Geschäftssitz. Optionen: Coworking-/Business-Center-Adresse, ladungsfähige Anschrift über Dienste,
  oder bewusst akzeptieren. **Vor** Website-Launch klären.
- **FinTS-Registrierungs-PDF**: enthält Privatadresse, ist aus dem Git-Tracking entfernt, **bleibt
  aber in der Historie** → vor Open-Source-Veröffentlichung **frisches Repo ohne Historie** (siehe
  Abschnitt 8).

---

## 7. Warum SaaS ausgeschlossen bleibt (zur Erinnerung im Plan)

Zentral gehostetes Multi-User-Banking = **Kontoinformationsdienst (AIS)** → in DE
**erlaubnispflichtig (BaFin, § 34 ZAG)**. Konsequenzen: **Berufshaftpflicht** (bzw. ab PSD3 optional
50.000 € Anfangskapital), **Geschäftsleiter-Eignung**, **organisatorische Pflichten/Reporting**,
**DORA** (IKT-Risikomanagement, Vorfallmeldung, Dienstleisterverträge – gilt seit 01/2025 auch für
AIS-Dienstleister). Grund: zentrales Halten **fremder** Bankdaten = systemisches Risiko.
**Regulatorischer Kontext Juni 2026:** PSD3/PSR final ausverhandelt (Einigung 23.04.2026, Übergang
mit Re-Authorisierung + DORA-Nachweis); FiDA/Open Finance in Trilog, Anwendung gestaffelt ab
2027–2030. → Aufwand: mittlerer fünfstelliger Betrag/Jahr + Dauer-Compliance. **Nicht nebenbei.**
Falls je Multi-User-Cloud gewünscht: lizenzierten Aggregator (finAPI/Tink/Klarna Kosma) einbinden,
dann liegt die Lizenzpflicht bei denen – aber das ist ein eigenes, separat zu bewertendes Projekt.

---

## 8. To-do vor dem ersten (öffentlichen/kommerziellen) Schritt

### Technisch / Repo
- [ ] **Frisches öffentliches Repo ohne Historie** (entfernt FinTS-PDF & private Registry-IPs aus
      der Vergangenheit dauerhaft).
- [ ] Compose-Dateien generisch (`192.168.178.30:5000/...` → veröffentlichtes Image, z. B.
      ghcr.io via CI-Release-Workflow).
- [ ] Frische Screenshots (aktuelles Design, **Demo-Daten**), README mit Disclaimer
      „self-hosted/LAN, **nicht** für ungeschützte Internet-Exposition gehärtet".
- [ ] Demo-/Seed-Daten, damit Interessenten das Produkt in 5 Minuten testen können (Adoption-Hebel).
- [ ] CONTRIBUTING: Hinweis, dass **abgeleitete Produkte eine eigene (kostenlose) DK-FinTS-Produkt-ID**
      registrieren müssen.
- [ ] **Sparkasse/Finanz-Informatik FinTS-Test** (größte Bankengruppe) – Voraussetzung für die
      Aussage „mit den meisten deutschen Banken nutzbar".
- [ ] „Vollständige Historie abrufen (TAN)"-Option für den >90-Tage-Erstimport in die UI.
- [ ] Desktop-Paketierung (pywebview/Tauri) als PoC für Linie A; Solo- vs. LAN-Schalter.
- [ ] PWA (Manifest + Service Worker) als günstige Companion-Stufe für Linie B.

### Geschäftlich / rechtlich
- [x] **Lizenzentscheidung getroffen (2026-06-13): AGPL-3.0 + Convenience.**
- [ ] `LICENSE` von MIT → **AGPL-3.0** ändern – **vor** dem ersten Public-Commit.
- [ ] **DCO/CLA** aufsetzen, **bevor** externe PRs kommen (sonst keine spätere Dual-License/
      kommerzielle Desktop-Variante möglich).
- [ ] **Gewerbe anmelden** (Einzelunternehmen, Kleinunternehmerregelung) – sobald Geld fließen soll.
- [ ] **Merchant of Record** (Paddle/Lemon Squeezy/FastSpring) für Verkauf + USt evaluieren.
- [ ] **Impressum-Adresse** klären (Privatsphäre, Abschnitt 6.5).
- [ ] **Shop-Rechtstexte** (Impressum, DSGVO, AGB, Widerrufsbelehrung + korrekter
      Download-Verzicht-Flow) – einmal anwaltlich prüfen (IT-Recht).
- [ ] **Update-/Support-Zusage** definieren (Major-Version-Modell, „gepflegt mindestens bis…").
- [ ] Haftungsbegrenzung in AGB (Finanzdaten „as is", soweit B2C zulässig) – anwaltlich.

### Optional / später
- [ ] Berufshaftpflicht für IT-Dienstleister (günstig, deckt Beratungs-/Programmierfehler).
- [ ] Native Companion-App (Stage 2) – nur bei nachgewiesener Nachfrage.
- [ ] UG/GmbH-Wechsel – nur bei relevantem Umsatz/Haftungsvolumen.

---

## 9. Realistische Erwartung (ehrlich)

| Stufe | Aufwand | Realistischer Ertrag |
|---|---|---|
| OSS + Spenden/Convenience | klein | € 0–niedrige Hunderte/Jahr |
| Bezahlte Desktop-App (Linie A, Major-Version) | mittel–hoch | einziger Weg zu nennenswertem Geld – aber Dauer-Support, Releases, Banken-Pflege = Nebenjob |
| App-Stores (native Companion) | hoch | winzige Zielgruppe (self-hostet *und* will App); zuletzt |
| SaaS | — | ausgeschlossen (AISP/BaFin) |

**Fazit:** Veröffentlichen, Reaktionen sammeln (Stars, Issues, „würde zahlen"-Signale), **dann**
entscheiden, ob die bezahlte Desktop-App den Dauer-Support wert ist. Geld ist Bonus, nicht Plan.

---

## Quellen (Stand Juni 2026)
- BaFin – Zulassung/Aufsicht PSD2, § 34/§ 36 ZAG, DORA: bafin.de
- PSD3/PSR Stand 04/2026: Norton Rose Fulbright, Hogan Lovells
- FiDA/Open Finance Stand 2026: Konsentus, Deloitte
- Update-Pflicht digitale Produkte: § 327f BGB (gesetze-im-internet.de), JuraForum, Lecturio
- Widerrufsrecht digitale Inhalte: EVZ, IT-Recht-Kanzlei, eRecht24
- Gewerbe/Rechtsform: BMWK-Existenzgründungsportal, Lexware, eRecht24
- FinTS-Bankenanzahl/Liste: Wikipedia (FinTS), Subsembly, DK-Bankenliste (Produkteigner-Verteiler)
- 90-Tage-SCA / FinTS: willuhn.de (Hibiscus-Wiki), homebanking-hilfe.de
- Stop Killing Games: citizens-initiative.europa.eu, EU-Kommission (Antwort 16.06.2026)
