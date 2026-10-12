# Transcriptie

Spraak omzetten naar tekst voor medewerkers van het ministerie van Financiën.
Upload een audiobestand of neem direct op in de browser, tot **2 uur** lang.
Je krijgt de uitgeschreven tekst terug, die je kunt aanpassen, kopiëren of
downloaden als .txt of .docx. Met sprekerherkenning staat bij elke beurt wie er
sprak; je geeft de sprekers een naam en exporteert het als gespreksverslag.

De frontend is Vue 3 met TypeScript en Vite, gebouwd met het
[NLDD Designsysteem](https://nederlandsedigitaledienst.github.io/design-system/)
(`@nldd/design-system`). De backend is FastAPI op Python 3.13. Die meet en knipt
de audio met ffmpeg en stuurt de stukken naar de transcriptiedienst. Lokaal
is dat **Voxtral Small 24B** in Ollama, in productie **vlam-api** van vlam.ai,
het AI-platform van SSC-ICT. Alles draait als één container in Azure Container
Apps, uitgerold met `azure-pipelines.yml`.

## Hoe het werkt

```
browser ──upload──► backend ──ffprobe: ≤ 2 uur?──► ffmpeg: 16 kHz mono wav
   ▲                   │                              │
   │                   │                   knippen in stukken van ≤ 10 min,
   │  poll: status,    │                   bij voorkeur in een stilte
   │  deel 3 van 12    │                              │
   └───────────────────┘◄── tekst per stuk ◄── transcriptiedienst (Voxtral / vlam-api)
```

Voxtral verwerkt ongeveer 30 minuten audio per aanvraag, en de ingress van
Azure Container Apps kapt een HTTP-aanvraag af na 240 seconden. Een opname van
2 uur gaat daarom als taak: de browser uploadt met voortgang en vraagt daarna
elke 2 seconden de status op. De backend knipt in stukken van hoogstens 10
minuten, bij voorkeur midden in een stilte, zodat er geen woord doormidden gaat.

Met de schakelaar *Sprekers herkennen* komt het transcript terug als beurten
(`segments`: spreker, begin, eind, tekst). Waar de sprekers worden herkend,
hangt af van `DIARIZATION`:

- `service`, in productie: vlam-api doet het zelf, met
  `response_format=diarized_json`. De hele opname gaat dan in één aanvraag,
  want vlam-api geeft elk stuk eigen sprekerlabels.
- `local`, de standaard lokaal: Ollama levert geen sprekers, dus de backend
  draait zelf
  [pyannote speaker-diarization-community-1](https://huggingface.co/pyannote/speaker-diarization-community-1),
  hetzelfde model als vlam-api. Daarna gaat elke beurt los naar Voxtral, lange
  beurten geknipt zoals hierboven. De voortgang telt dan beurten.
- `off`: geen sprekers; de schakelaar verdwijnt.

Namen die de gebruiker invult, samengevoegde sprekers en verplaatste beurten
blijven in de browser. De server kent alleen `S1`, `S2`, enzovoort.

De sleutel van de transcriptiedienst staat alleen in de backend, als Container
App-secret. Audio staat alleen tijdens de verwerking in een tijdelijke map en
wordt daarna gewist. Een klaar transcript blijft hoogstens een uur in het
geheugen (`RESULT_TTL_SECONDS`) en in de browser tot je het venster sluit. Er
is geen database, er gaat niets in localStorage en het log bevat geen
transcriptinhoud.

### Grenzen

| | Standaard | Instelling |
|---|---|---|
| Maximale duur | 2 uur | `MAX_AUDIO_SECONDS` (backend), `VITE_MAX_AUDIO_MINUTES` (frontend) |
| Maximale bestandsgrootte | 500 MB | `MAX_UPLOAD_MB`, `VITE_MAX_UPLOAD_MB` |
| Opnemen in de browser | stopt vanzelf na 2 uur, waarschuwt 5 minuten ervoor | volgt de maximale duur |
| Lengte van een stuk | 10 minuten | `CHUNK_SECONDS` |

De duur wordt drie keer gecontroleerd. De browser kijkt vóór het uploaden, zodat
niemand 300 MB uploadt om dan te horen dat het te lang is. De backend kijkt bij
binnenkomst met ffprobe en antwoordt met 422, en kijkt nog eens na het omzetten:
opnames uit de browser (webm) hebben vaak geen duur in de header.

## Lokaal draaien

Nodig: Node 26 (zie `.nvmrc`), [uv](https://docs.astral.sh/uv/), ffmpeg en
[Ollama](https://ollama.com).

```bash
# 1. Voxtral Small 24B in Ollama (~16 GB, eenmalig)
ollama pull hf.co/bartowski/mistralai_Voxtral-Small-24B-2507-GGUF:Q4_K_M

# 2. Afhankelijkheden
npm ci
uv sync

# 3. Backend (:8010) en frontend (:5173), elk in een eigen terminal
npm run api
npm run dev
```

Open <http://localhost:5173>. Vite stuurt `/api` door naar de backend. Zonder
`.env.local` gebruikt de backend Ollama op `localhost:11434` met het model
hierboven. Andere waarden zet je in `.env.local`, naar het voorbeeld van
`.env.example`.

Sprekerherkenning draait lokaal in de backend met pyannote. Dat zit in de
uv-groep `diarization`, die `uv sync` standaard meeneemt. Het model staat
achter een gebruikersovereenkomst op Hugging Face, dus voor de eerste download
moet je ingelogd zijn:

```bash
# 1. Accepteer de voorwaarden op
#    https://huggingface.co/pyannote/speaker-diarization-community-1
# 2. Eén keer inloggen (of zet HF_TOKEN in .env.local)
uv run hf auth login
```

Bij de eerste opname met sprekers wordt het model opgehaald. Daarna staat het
in `~/.cache/huggingface` en is er geen sleutel meer nodig. `DIARIZATION_MODEL`
mag ook een map zijn waarin je het model zelf hebt gezet. Zonder model biedt de
app geen sprekerherkenning aan.

Om te kijken of Ollama en Voxtral werken:

```bash
curl -s localhost:11434/v1/audio/transcriptions \
  -F file=@opname.wav \
  -F model=hf.co/bartowski/mistralai_Voxtral-Small-24B-2507-GGUF:Q4_K_M \
  -F language=nl
```

### Als container

```bash
docker build -t transcriptie .
docker run -p 8000:8000 \
  -e TRANSCRIBE_URL=http://host.docker.internal:11434/v1/audio/transcriptions \
  -e DIARIZATION=off \
  transcriptie
```

Het image heeft geen pyannote, omdat vlam-api daar de sprekers herkent:
`DIARIZATION=service` is de standaard in het image. Met Ollama als dienst zet
je `DIARIZATION=off`, zoals hierboven.

### Tests

```bash
npm test          # frontend (vitest): service, state machine, export, NLDD-registratie
npm run test:api  # backend (pytest): knippen, beurten, API, adapter; gebruikt ffmpeg
uv run ruff check backend
```

`src/registration/nlddRegistration.test.ts` controleert dat elk `<nldd-*>`-element
in een template ook geïmporteerd wordt in `src/main.ts`. De app laadt NLDD per
component in plaats van het hele pakket, 457 kB in plaats van 1,8 MB, en een
vergeten import levert anders stil een lege tag op.

## API

De API volgt de [NL GOV API Design Rules](https://gitdocumentatie.logius.nl/publicatie/api/adr/)
waar dat voor zo'n kleine API zin heeft: `/api/v1`, meervoud, `problem+json` bij
fouten en een `API-Version`-header.

| | |
|---|---|
| `POST /api/v1/transcriptions` | multipart `file` (+ optioneel `language`, `speakers=true`, `numSpeakers`) → `202` met de taak en een `Location`-header. `413` te groot, `415` geen audio, `422` langer dan 2 uur, ongeldig aantal sprekers of sprekerherkenning niet beschikbaar |
| `GET /api/v1/transcriptions/{id}` | `{ status: queued \| converting \| diarizing \| transcribing \| done \| failed, progress: {completed, total}, durationSeconds, text?, speakers?, segments?, error? }`. `segments` is `[{speaker, start, end, text}]`, alleen met `speakers=true` |
| `GET /api/v1/features` | `{ speakers: bool }`: kan deze server sprekers herkennen |
| `DELETE /api/v1/transcriptions/{id}` | annuleren en alles weggooien |
| `GET /api/v1/health` | health probe |

De koppeling met de transcriptiedienst staat in één bestand,
`backend/app/transcriber.py`. Verandert het formaat van de dienst, dan verandert
alleen dat bestand.

## Deployment

`azure-pipelines.yml` bouwt het image, zet het in de Azure Container Registry
van de resourcegroep en rolt het uit als één Container App, extern bereikbaar
achter een IP-allowlist.

De app draait met één replica die altijd aan staat, met 1 vCPU en 2 GiB. Taken
leven in het geheugen van dat ene proces: bij meer replicas kan de browser
uitkomen bij een replica die zijn taak niet kent, en bij schalen naar nul
verdwijnen lopende taken.

De secrets staan in de variable group `transcriptie-secrets`: `TRANSCRIBE_URL`
en `TRANSCRIBE_API_KEY`, allebei als secret gemarkeerd, en optioneel
`TRANSCRIBE_MODEL`, `TRANSCRIBE_API_KEY_HEADER` en `DIARIZATION`, standaard
`service`. De pipeline zet ze als Container App-secrets. Voor vlam-api is het
model `vlam-transcribe-prepaid`. Een vlam-api-sleutel verloopt na 6 maanden, en
vlam.ai staat hoogstens 5 gelijktijdige aanvragen toe. Het aantal in deze app
stel je in met `TRANSCRIBE_CONCURRENCY`, standaard 1.

Eenmalige setup: maak `transcriptie-secrets` aan, autoriseer de pipeline voor
`transcriptie-secrets` en de gedeelde variable group (`AZURE_SERVICE_CONNECTION`,
`ALLOWED_IP_1..4`), registreer `azure-pipelines.yml` en draai hem op `main`.

## Privacy, beveiliging en toegankelijkheid

Opnames van overleggen bevatten persoonsgegevens. Laat een DPIA doen en neem
de verwerking op in het verwerkingsregister. De app vraagt gebruikers geen
bijzondere persoonsgegevens te uploaden zonder toestemming, en de aanwezigen te
vragen of opnemen goed is.

Sprekerherkenning berekent per stem een kenmerk (embedding) om stukken van
dezelfde stem te groeperen. Dat gebeurt binnen één opname, in het geheugen,
tijdens de taak. Er is geen koppeling met namen of andere opnames en er wordt
niets bewaard. Stemkenmerken liggen dicht tegen biometrische gegevens (art. 9
AVG) aan, dus neem dit mee in de DPIA. De app legt het de gebruiker uit onder
"Goed om te weten".

vlam.ai hanteert *registreren tenzij* voor pilots en productie: registreer de
toepassing in het Algoritmeregister. Het resultaat is in de app en in de
.docx-export gemarkeerd als automatisch gegenereerd, met het verzoek het te
controleren.

Voor de beveiliging (BIO) stuurt de backend een strikte CSP mee
(`script-src 'self'`), een `Permissions-Policy` die de microfoon alleen voor
deze site toestaat, HSTS, `nosniff` en `no-referrer`. De container draait niet
als root, secrets staan nooit in het image, en de uploadgrootte wordt
gecontroleerd terwijl het bestand binnenkomt.

Voor toegankelijkheid (WCAG 2.2 AA) gebruikt de app NLDD-componenten, een
skip-link en live regions voor de voortgang, die niet elke seconde iets
voorlezen. Als het transcript klaar is, gaat de focus ernaartoe, en de opname
is volledig met het toetsenbord te bedienen. Een scan met axe-core vond geen
overtredingen.

## Bijdragen

Bijdragen zijn welkom, zie [CONTRIBUTING.md](CONTRIBUTING.md) en de
[gedragscode](CODE_OF_CONDUCT.md). Een kwetsbaarheid meld je volgens
[SECURITY.md](SECURITY.md), niet via een issue.

## Licentie

© Ministerie van Financiën. Gelicentieerd onder de [EUPL-1.2](LICENSE).
