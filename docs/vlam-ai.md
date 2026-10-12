# Transcriptiedienst in productie: vlam.ai

In productie gebruikt deze app **vlam-api** van **vlam.ai**, het AI-platform
van SSC-ICT voor de Rijksoverheid. Lokaal draait Voxtral Small 24B in Ollama
(zie de README).

> Dit document is samengesteld uit wat er openbaar over vlam.ai te vinden is
> (stand oktober 2026). De belangrijkste bron is het FAQ-document
> *"Overzicht vlam.ai"* van 21-10-2025, openbaar gemaakt in een Woo-besluit van
> VWS. vlam.ai werkt agile en past details regelmatig aan. **De actuele versie
> staat in de Samenwerkruimte van SSC-ICT**: controleer daar alles voordat je
> aansluit. De bronnen staan onderaan.

## Wat is vlam.ai

- **AI-as-a-Service van SSC-ICT** (ministerie van BZK). vlam.ai host AI-modellen
  voor tekstgeneratie, transcriptie en beeldherkenning op een **eigen
  GPU-cluster**, eerst vanuit de Koningskade en later vanuit ODC Rijswijk. Data,
  modellen en infrastructuur blijven binnen de Rijksoverheid.
- Twee soorten dienstverlening:
  1. **vlam-api**: gestandaardiseerde API's naar AI-modellen, bedoeld voor
     rijksbreed gebruik in eigen applicaties. Dit is wat deze app gebruikt.
  2. **Applicaties**: *vlam-chat* (chat-assistent voor rijksambtenaren) en
     *vlam-search* (zoeken met AI in documentsets).
- vlam.ai host **geen applicaties van afnemers**. Deze app blijft dus draaien
  waar hij nu draait (Azure Container Apps, zie `azure-pipelines.yml`) en roept
  vlam-api aan.

## vlam-api: transcriptie

vlam-api biedt standaardfuncties, waaronder **`transcribe`**. Volgens het
FAQ-document (oktober 2025):

| | |
|---|---|
| Model onder de motorkap | WhisperX (*geen vaste keuze*: vlam.ai wisselt modellen als dat de kwaliteit verbetert) |
| Goed in | transcriberen, **tijdcodes per woord**, **sprekerherkenning (diarisatie)** |
| Minder goed in | audio met lage geluidskwaliteit; diarisatie bij veel sprekers, overlappende spraak of sprekers met dezelfde toon |
| Belofte | *"Het API-format blijft hetzelfde"*. Het onderliggende model kan wisselen, de manier van aanroepen niet. |

Ter vergelijking: de `chat`-functie (nu Mistral Medium 3.1) heeft expliciet een
*OpenAI compatible API-format*. Voor `transcribe` zegt het document dat **niet**.
Het exacte aanvraag- en antwoordformaat staat niet in openbare bronnen: bij de
API-sleutel levert vlam.ai *"een notebook met voorbeelden van het gebruik van
vlam-api"*.

### Fair-usebeleid (basistoegang)

- Maximaal **5 gelijktijdige verzoeken**, maximale wachtrij van 100.
- Geen limiet op het aantal tokens per dag.
- Bij beperkte capaciteit of overmatig gebruik kan vlam.ai de capaciteit
  inperken.
- Uptime minimaal **95 %** (in productie minimaal 98 %).
- **API-sleutels verlopen automatisch na 6 maanden**, tenzij je met een goede
  reden om iets anders vraagt.

## Toegang krijgen

Stappen volgens het FAQ-document:

1. **Inschrijven.** Download het Word-document *"Inschrijfformulier vlam-api"*
   uit de Samenwerkruimte en vul het volledig in. Daarvoor is een **privacy- en
   securityadvies** nodig (zie de aansluitvoorwaarden in de Samenwerkruimte).
   Onderteken het en stuur het naar **sscictai@minbzk.nl**. Met je handtekening
   ga je akkoord met de aansluitvoorwaarden. Er is een versie voor de POC-fase
   en een (strengere) voor de Pilot-fase.
2. **API-sleutel ontvangen.** De opgegeven personen krijgen de sleutel per
   e-mail, met het voorbeeldnotebook.

Verder:

- **Ministerie van BZK** heeft een eigen route: aanvragen lopen via
  postbusteamai@minbzk.nl, en BZK kan aanvullende eisen stellen.
- **Fasen.** In oktober 2025 was vlam-api er alleen voor POC's (geen gebruikers)
  en Pilots (hoogstens 25 gebruikers). Productie was voorzien vanaf 2026. Volgens
  Computable (juni 2026) wordt vlam *"momenteel al geleverd aan de ministeries
  van VWS, Financiën, Algemene Zaken, OCW, IenW en de Hoge Colleges van Staat"*,
  met een brede productie-uitrol in de tweede helft van 2026.
- **Prioriteit bij beperkte capaciteit:** (1) afnemers met een financiële
  commitment, (2) afnemers binnen het verzorgingsgebied van SSC-ICT, (3) de
  rest. Deelname was tijdens de testfase kosteloos; de productieprijzen waren
  toen nog onbekend.
- **Algoritmeregister.** Bij Pilots en Productie hanteert vlam.ai *"registreren
  tenzij"*: je registreert de toepassing in het Algoritmeregister, tenzij er
  geldige redenen zijn om dat niet te doen.
- **Contact:** SSC-ICT AI-team / vlam.ai-team, sscictai@minbzk.nl.

## Hoe deze app op vlam-api aansluit

De app is er al op ingericht dat de transcriptiedienst in Azure verwisselbaar
is:

| Wat | Waar | Voor vlam-api |
|---|---|---|
| URL van de dienst | secret `TRANSCRIBE_URL` (variable group `transcriptie-secrets`) | het `transcribe`-endpoint van vlam-api |
| Sleutel | secret `TRANSCRIBE_API_KEY` | de vlam-api-sleutel. **Let op: verloopt na 6 maanden**, dus zet een herinnering om hem te vernieuwen |
| Header voor de sleutel | `TRANSCRIBE_API_KEY_HEADER` (standaard `Authorization` → `Bearer <sleutel>`) | volgens het voorbeeldnotebook |
| Model | `TRANSCRIBE_MODEL` | waarschijnlijk niet nodig (vlam.ai kiest het model); laat leeg als de API geen `model` vraagt |
| Aanroep en antwoord | `backend/app/transcriber.py` | **aanpassen aan het formaat uit het notebook**; dit is het enige bestand dat ervan weet |
| Gelijktijdige aanvragen | `TRANSCRIBE_CONCURRENCY` (standaard 1) | hoogstens 5 volgens het fair-usebeleid |
| Lengte van de stukken | `CHUNK_SECONDS` (standaard 600) | afstemmen op de grenzen van vlam-api (bestandsgrootte, duur), zodra die bekend zijn |

De adapter stuurt nu een multipart-POST met `file` (16 kHz mono wav), `model`,
`language` en `temperature`, en verwacht `{"text": "..."}` of platte tekst
terug. Dat is het formaat van Ollama, dat we lokaal gebruiken. Wijkt vlam-api
daarvan af, dan pas je alleen `Transcriber.transcribe` en `_text` aan. De
tests in `backend/tests/test_transcriber.py` laten zien wat de rest van de app
verwacht: `transcribe(pad, taal) -> tekst`.

### Sprekerherkenning komt gratis mee

vlam-api's transcriptie levert sprekerherkenning en tijdcodes per woord. Dat
maakt de feature [meerdere sprekers](features/meerdere-sprekers.md) in
productie veel eenvoudiger: de aparte diarisatiestap uit dat voorstel kan
vervallen. De adapter vertaalt dan het antwoord van vlam-api naar de
`segments`/`speakers` uit het datamodel daar. Lokaal (Voxtral via Ollama) zijn
er geen sprekers.

## Open punten vóór aansluiten

- [ ] **Formaat van `transcribe`**: endpoint, velden, authenticatieheader en de
      vorm van het antwoord (met sprekers en tijdcodes) uit het voorbeeldnotebook
      halen, en de adapter plus tests daarop aanpassen.
- [ ] **Grenzen per aanvraag**: maximale bestandsgrootte en duur. Daarop
      `CHUNK_SECONDS` instellen. Als vlam-api zelf 2 uur in één keer aankan,
      kan het knippen op stiltes blijven (kortere aanvragen, betere voortgang)
      of eruit. Let op: diarisatie per stuk geeft per stuk eigen sprekerlabels,
      dus knippen en sprekerherkenning gaan niet zomaar samen. Zie het
      sprekersvoorstel.
- [ ] **Netwerk**: is vlam-api bereikbaar vanuit de Azure Container
      Apps-omgeving? vlam.ai draait in een rijksdatacenter; mogelijk
      is een route via het Rijksnetwerk of een IP-allowlist aan de kant van
      vlam.ai nodig. Het uitgaande IP-adres van de Container Apps-omgeving is
      dan nodig.
- [ ] **Welke gegevens mogen erdoor**: de bronnen lopen uiteen. Het
      FAQ-document noemt vlam-chat een veilig alternatief *"waarmee gebruikers
      vertrouwelijke en gevoelige informatie veilig kunnen verwerken"*, terwijl
      persberichten over vlam-chat zeggen dat er *"geen vertrouwelijke of
      privacygevoelige informatie"* in mag. Leg vast wat de
      aansluitvoorwaarden voor vlam-api zeggen, en pas de tekst onder "Goed om te
      weten" in de app daarop aan.
- [ ] **Privacy- en securityadvies** voor het inschrijfformulier (nodig voor
      aansluiting), en een DPIA. Opnames van overleggen bevatten
      persoonsgegevens.
- [ ] **Algoritmeregister**: registratie voor de Pilot- of productiefase.
- [ ] **Sleutelbeheer**: wie ontvangt de sleutel, waar wordt hij vernieuwd
      (variable group `transcriptie-secrets`), en wie bewaakt de vervaldatum
      van 6 maanden.

## Bronnen

- *Overzicht vlam.ai* (FAQ, 21-10-2025), Woo-besluit VWS:
  <https://open.minvws.nl/dossier/VWS-WOO/4349886-1094118-doo/file/download/document/1f12f444-76c6-6a44-8f86-9f84095f6960>
- Computable, *Vlam in de ai-pan bij rijksambtenaren* (10-06-2026):
  <https://www.computable.nl/2026/06/10/vlam-in-de-ai-pan-bij-rijksambtenaren/>
- Digitale Overheid, *Departementen kiezen voor veilige AI-chatbot van SSC-ICT*:
  <https://www.digitaleoverheid.nl/nieuws/departementen-kiezen-voor-veilige-ai-chatbot-van-ssc-ict/>
- Security.NL, *Rijksambtenaren krijgen volgend jaar toegang tot AI-chatbot vlam-chat*:
  <https://www.security.nl/posting/913738/Rijksambtenaren+krijgen+volgend+jaar+toegang+tot+AI-chatbot+vlam-chat>
- iBestuur, *Rijksambtenaren krijgen in 2026 beschikking over AI-chatbot*:
  <https://ibestuur.nl/data-en-ai/datagedreven-werken/rijksambtenaren-krijgen-in-2026-beschikking-over-ai-chatbot>
- Dutch IT Leaders, interview met Nardie Scharenborg (SSC-ICT):
  <https://www.dutchitleaders.nl/interview/715504/nardie-scharenborg-ssc-ict-met-eigen-ai-platform-kan-rijksoverheid-weer-volop-meedoen>
