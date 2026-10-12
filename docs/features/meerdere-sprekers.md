# Feature: meerdere sprekers herkennen en tonen

Status: **voorstel**. Nog niet gebouwd.

## Waarom

Wie een overleg, interview of hoorzitting opneemt, krijgt nu één doorlopende
lap tekst terug. Voor een verslag wil je juist weten *wie* wat zei. De
gebruiker moet dan zelf terugluisteren en namen erbij typen, en dat is precies
het werk dat deze app hoort weg te nemen.

Doel: het transcript is opgedeeld in **beurten** (wie sprak, van wanneer tot
wanneer, wat werd er gezegd). De gebruiker kan sprekers een naam geven, en de
export leest als een gespreksverslag.

## Wat er technisch nodig is

### Twee situaties: vlam-api (productie) en Voxtral (lokaal)

**In productie levert de transcriptiedienst zelf sprekers.** De
`transcribe`-functie van vlam-api (nu WhisperX) doet volgens vlam.ai
sprekerherkenning en geeft tijdcodes per woord (zie [vlam.ai](../vlam-ai.md)).
Daar is dus geen eigen diarisatie nodig. De adapter
(`backend/app/transcriber.py`) vertaalt het antwoord naar de beurten uit het
datamodel hieronder. Let op één ding: vlam-api diariseert per aanvraag. Knippen
we een opname in stukken van tien minuten, dan is "spreker 1" in stuk 2 niet
per se "spreker 1" in stuk 1. Daarom:

- stuur de opname **in één keer** als vlam-api dat aankan (duur en grootte nog
  navragen), of
- koppel de sprekers tussen stukken aan elkaar via een overlap van ~30 s aan
  elke rand: de spreker die in de overlap het meest samenvalt is dezelfde. Kan
  dat niet betrouwbaar, laat de gebruiker dan samenvoegen (zie
  *Corrigeren*).

**Lokaal levert Voxtral geen sprekers.** Voxtral Small 24B schrijft spraak uit
maar zegt niet wie er spreekt. Het model
een sprekerlabel laten "raden" via een prompt werkt niet betrouwbaar: het
verzint wisselingen en raakt de draad kwijt tussen de stukken van tien minuten.
Wil je lokaal ook sprekers, dan komt er een aparte stap bij:
**sprekerdiarisatie** ("wie sprak wanneer"). Die is optioneel; productie heeft
hem niet nodig.

### Lokale aanpak: eerst diarisatie, dan per beurt transcriberen

```
upload ─► omzetten (16 kHz mono) ─► diarisatie ─► beurten samenvoegen ─► per blok transcriberen ─► transcript met beurten
                                    (wie, van–tot)  (korte beurten         (Voxtral, zoals nu)
                                                    samen, ≤ 10 min)
```

1. **Diarisatie** met een open-sourcemodel dat in onze eigen container draait,
   bijvoorbeeld `pyannote.audio` (`speaker-diarization-3.1` of
   `speaker-diarization-community-1`). Uitvoer: een lijst segmenten
   `(start, eind, spreker_X)`. Er gaat geen audio naar een extra externe dienst.
2. **Beurten samenvoegen.** Opeenvolgende segmenten van dezelfde spreker worden
   één beurt. Pauzes korter dan ~1 s binnen een beurt negeren we, en een
   tussenwerpsel ("ja", "hm") van minder dan ~0,7 s van een ander laten we in de
   beurt staan.
3. **Knippen op beurtgrenzen** in plaats van op stiltes. De bestaande
   `plan_segments` krijgt de beurtgrenzen als kandidaat-knippunten. Zo blijft een
   blok onder de tien minuten en gaat er geen zin doormidden.
4. **Transcriberen** per beurt, of per blok van een paar korte beurten,
   met de bestaande adapter (`backend/app/transcriber.py`). Losse beurten van
   een paar seconden geven Voxtral weinig context. Daarom bundelen we korte
   beurten tot een blok van ten minste ~30 s. Het blok gaat dan als geheel naar
   Voxtral, met tijdstempels als de dienst die levert, of anders als losse
   beurten na elkaar.
5. **Resultaat** als lijst beurten (zie datamodel).

Met vlam-api in productie slaan we stap 1 tot en met 3 over: de adapter geeft
de beurten van vlam-api direct terug. De rest van de app merkt daar niets van,
omdat het datamodel hetzelfde blijft.

### Alternatieven die we niet kiezen

| Aanpak | Waarom niet |
|---|---|
| Voxtral vragen sprekers te labelen | Onbetrouwbaar, niet consistent over stukken heen |
| Eerst alles transcriberen, daarna diariseren en tekst uitlijnen op tijd | Vraagt tijdstempels per woord van de dienst; Voxtral via Ollama levert die niet |
| Een extra externe diarisatiedienst naast vlam-api | Audio gaat dan naar nog een partij: extra verwerker, extra DPIA-werk |

## Datamodel

De taak-API blijft achterwaarts compatibel. `text` blijft bestaan (de platte
tekst), en `segments` en `speakers` komen erbij:

```json
{
  "id": "…",
  "status": "done",
  "text": "Goedemorgen allemaal. …",
  "speakers": [
    { "id": "S1", "label": "Spreker 1" },
    { "id": "S2", "label": "Spreker 2" }
  ],
  "segments": [
    { "speaker": "S1", "start": 0.0,  "end": 12.4, "text": "Goedemorgen allemaal. Zullen we beginnen?" },
    { "speaker": "S2", "start": 12.9, "end": 31.0, "text": "Ja, ik heb eerst een vraag over de begroting." }
  ]
}
```

- `speaker` is een neutrale sleutel (`S1`, `S2`, …) in volgorde van eerste keer
  spreken. De server kent geen namen.
- Namen die de gebruiker invult blijven **in de browser**. Ze gaan niet terug
  naar de server en komen alleen in de export terecht.
- Tijden in seconden vanaf het begin van de opname.

## Gebruikerservaring

### Vooraf: aanzetten en een hint geven

- Een schakelaar **"Sprekers herkennen"** (`nldd-switch-field`), standaard aan
  bij uploads langer dan 2 minuten. Hulptekst: *"Handig voor overleggen en
  interviews. Duurt iets langer."*
- Optioneel: **"Hoeveel mensen spreken er?"** met de keuzes *Weet ik niet*, 2, 3,
  4, 5, 6 of meer (`nldd-dropdown`). Een bekend aantal maakt de diarisatie
  merkbaar beter. *Weet ik niet* is de standaard; we vragen het nooit verplicht.
- De voortgang krijgt een fase erbij: *"Sprekers herkennen…"* vóór
  *"Bezig met transcriberen: deel 3 van 12"*.

### Het resultaat: beurten in plaats van een lap tekst

```
┌ Sprekers ──────────────────────────────────────────────┐
│ ● Spreker 1  [ Voorzitter        ]  14 beurten · 22 min │
│ ● Spreker 2  [ Fatima            ]   9 beurten · 11 min │
│ ● Spreker 3  [ Spreker 3         ]   2 beurten · 0:40   │
│                                    [Sprekers samenvoegen]│
└────────────────────────────────────────────────────────┘

Voorzitter · 00:00:00
Goedemorgen allemaal. Zullen we beginnen?

Fatima · 00:00:12
Ja, ik heb eerst een vraag over de begroting. …
```

- **Namen geven.** Bovenaan staat per spreker een tekstveld. Een naam die je
  daar invult staat meteen bij elke beurt van die spreker. Je typt één keer en
  het hele transcript is bijgewerkt.
- **Kleur is hulp, geen informatie.** Elke spreker krijgt een vaste kleur (stip
  of rand), maar de naam staat er altijd als tekst bij (WCAG 1.4.1).
- **Corrigeren.** Diarisatie maakt fouten. Daarom:
  - *Sprekers samenvoegen*: één persoon die als twee sprekers is herkend.
  - *Beurt toewijzen aan…*: menu per beurt (`nldd-button` met `nldd-menu`) om
    één beurt aan een andere spreker te geven.
  - *Beurt splitsen*: optioneel en pas in een latere fase.
- **Tekst aanpassen** per beurt, zoals nu in het hele tekstveld.
- **Terugluisteren.** De tijd bij een beurt is een knop die de opname vanaf dat
  punt afspeelt. Dat kan omdat de audio van de gebruiker zelf nog in de
  browser staat (object-URL). Er gaat daarvoor niets naar de server.
- **Leesbaarheid.** Opeenvolgende beurten van dezelfde spreker voegen we samen.
  Een lange beurt (> ~2 min) breken we op in alinea's op pauzes, zodat er geen
  muur van tekst staat.

### Toegankelijkheid

- De beurten staan in een lijst (`<ol>`). Elke beurt begint met de sprekernaam
  als tekst, zodat een schermlezer "Fatima, 12 seconden: …" voorleest.
- Een hernoemde spreker wordt via een `role="status"` gemeld ("Spreker 2 heet
  nu Fatima, 9 beurten aangepast").
- De terugluisterknoppen hebben een toegankelijke naam als *"Afspelen vanaf
  0 minuten 12"*, niet alleen "00:00:12".

## Export

Bij exporteren kiest de gebruiker met een paar vinkjes wat erin komt. De
standaard is een gespreksverslag dat zo te delen is.

| Optie | Standaard |
|---|---|
| Sprekernamen | aan |
| Tijden | aan |
| Kop met gegevens (bestand, datum, duur, sprekers) | aan |

### Word (.docx), het gespreksverslag

```
Transcript overleg-begroting.m4a
──────────────────────────────────────────
Datum opname   12 oktober 2026
Duur           1:12:40
Sprekers       Voorzitter, Fatima, Spreker 3

Automatisch gegenereerd transcript. Controleer de tekst voordat je hem gebruikt.

Voorzitter  00:00:00
Goedemorgen allemaal. Zullen we beginnen?

Fatima  00:00:12
Ja, ik heb eerst een vraag over de begroting. …
```

- De sprekernaam is vet, de tijd staat erachter in een rustigere grijstint, en
  de tekst volgt als gewone alinea.
- We gebruiken Word-stijlen (`Spreker`, `Tijd`, `Beurt`) in plaats van losse
  opmaak. Wie het verslag in de eigen huisstijl wil, past dan één stijl aan.
- Alternatieve weergave **"Als tabel"** met de kolommen *Tijd | Spreker | Tekst*.
  Die is handig om te annoteren of te filteren, bijvoorbeeld in Excel.

### Tekst (.txt)

```
[00:00:00] Voorzitter: Goedemorgen allemaal. Zullen we beginnen?

[00:00:12] Fatima: Ja, ik heb eerst een vraag over de begroting. …
```

Elke beurt op één regel met een witregel ertussen, zodat de tekst goed te
plakken is in e-mail of Teams. "Kopiëren" levert dezelfde tekst.

### Ondertitels (.vtt), nieuw

WebVTT met *voice spans*, zodat een videospeler de spreker toont:

```
WEBVTT

00:00:00.000 --> 00:00:12.400
<v Voorzitter>Goedemorgen allemaal. Zullen we beginnen?

00:00:12.900 --> 00:00:31.000
<v Fatima>Ja, ik heb eerst een vraag over de begroting.
```

Lange beurten knippen we op in cues van hoogstens ~7 s / 2 regels, zodat ze
leesbaar zijn als ondertitel. Dit is handig voor de toegankelijkheid van
opgenomen webinars en video's.

### Zonder sprekers

Staat diarisatie uit, of zet de gebruiker "Sprekernamen" uit, dan blijft de
export zoals nu: doorlopende tekst in alinea's.

## Privacy (AVG)

- **Stemkenmerken.** Diarisatie berekent per spreker een stemkenmerk
  (embedding) om stukken van dezelfde stem te groeperen. We gebruiken dat
  alleen binnen één opname en niet om iemand te *identificeren*: er is geen
  koppeling met namen of andere opnames. De kenmerken leven alleen in het
  geheugen tijdens de taak en worden niet opgeslagen. Laat de privacy officer
  dit in de DPIA beoordelen, want stemkenmerken liggen dicht tegen biometrische
  gegevens (art. 9 AVG) aan.
- **Namen** die de gebruiker invult blijven in de browser (zie datamodel).
- **Transparantie.** De bestaande tekst onder "Goed om te weten" krijgt een
  regel over sprekerherkenning: wat het doet, en dat het fouten maakt.

## Fasering

1. **Fase 1, sprekers zien.** `segments` in de API uit het antwoord van
   vlam-api, beurten tonen met "Spreker 1, 2, …", en .txt/.docx met sprekers en
   tijden. Eigen diarisatie voor lokaal gebruik is optioneel.
2. **Fase 2, sprekers corrigeren.** Namen geven, samenvoegen, beurt toewijzen,
   en de .docx-tabelweergave.
3. **Fase 3, extra's.** Terugluisteren vanaf een beurt, .vtt-export en het
   aantal sprekers als hint.

## Open punten

- **Antwoordformaat van vlam-api** met sprekers en woordtijden (staat in het
  voorbeeldnotebook bij de API-sleutel), en of het hele opnames van 2 uur in
  één aanvraag aankan. Dat bepaalt of we sprekers tussen stukken moeten
  koppelen.
- **Kwaliteit van vlam-api's diarisatie.** vlam.ai noemt zelf dat het minder goed
  gaat bij veel sprekers, overlappende spraak of gelijke stemmen. Dat is precies
  een druk overleg, dus de correctiefuncties in de UI zijn geen luxe.
- **Licentie en hosting van een lokaal diarisatiemodel** (alleen als we lokaal
  sprekers willen). De pyannote-modellen staan
  achter een gebruikersovereenkomst op Hugging Face. Check de licentie en
  bundel het model in het image, zodat de container in productie niets van
  buiten hoeft op te halen.
- **Rekentijd lokaal.** Diarisatie van twee uur audio op CPU kan lang duren. In
  productie draait dit bij vlam.ai op GPU's.
- **Kwaliteit meten.** Neem een handvol echte (geanonimiseerde of nagespeelde)
  overleggen met een handmatig gemaakt sprekerverslag als ijkset, en meet de
  *diarization error rate* vóór en na wijzigingen.

## Acceptatiecriteria (fase 1)

- Een opname met 3 sprekers geeft beurten met 3 verschillende sprekers. De
  meeste beurten (> 85 % van de spreektijd, gemeten op de ijkset) staan bij de
  juiste spreker.
- Geen beurt is langer dan nodig: wisselingen van spreker vallen samen met een
  nieuwe beurt.
- De .docx- en .txt-export tonen spreker en tijd per beurt, in de volgorde van
  de opname.
- Na afloop staan er geen audio en geen stemkenmerken meer op schijf of in het
  geheugen (behalve het transcript, binnen de bestaande bewaartermijn).
- Toetsenbord en schermlezer: elke beurt is bereikbaar en wordt voorgelezen
  met de sprekernaam ervoor.
