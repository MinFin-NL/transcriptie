# Transcriptie

Spraak omzetten naar tekst voor medewerkers van het ministerie van Financiën.
Upload een audiobestand of neem direct op in de browser, tot **2 uur** lang.
Je krijgt de uitgeschreven tekst terug, die je kunt aanpassen, kopiëren of
downloaden als .txt of .docx. Met **sprekerherkenning** staat er per beurt wie
er sprak; je geeft sprekers een naam en exporteert het als gespreksverslag.

- **Frontend:** Vue 3 + TypeScript + Vite, met het
  [NLDD Designsysteem](https://nederlandsedigitaledienst.github.io/design-system/)
  (`@nldd/design-system`).
- **Backend:** FastAPI (Python 3.13) met ffmpeg. Meet en knipt de audio en
  stuurt de stukken naar de transcriptiedienst.
- **Transcriptiedienst:** lokaal **Voxtral Small 24B** in Ollama, in productie
  **vlam-api** van [vlam.ai](docs/vlam-ai.md) (SSC-ICT).
- **Deploy:** één container in Azure Container Apps, via `azure-pipelines.yml`.

## Hoe het werkt

```
browser ──upload──► backend ──ffprobe: ≤ 2 uur?──► ffmpeg: 16 kHz mono wav
   ▲                   │                              │
   │                   │                   knippen in stukken van ≤ 10 min,
   │  poll: status,    │                   bij voorkeur in een stilte
   │  deel 3 van 12    │                              │
   └───────────────────┘◄── tekst per stuk ◄── transcriptiedienst (Voxtral / vlam-api)
```

- **Waarom knippen.** Voxtral verwerkt ongeveer 30 minuten audio per aanvraag,
  en de ingress van Azure Container Apps kapt een HTTP-aanvraag af na 240
  seconden. Een opname van 2 uur gaat daarom als **taak**: de browser uploadt
  (met voortgang) en vraagt daarna elke 2 seconden de status op. De backend
  knipt in stukken van hoogstens 10 minuten, bij voorkeur midden in een stilte,
  zodat er geen woord doormidden gaat.
- **Sprekers.** Met de schakelaar *Sprekers herkennen* komt het transcript terug
  als beurten (`segments`: spreker, begin, eind, tekst). Waar dat gebeurt hangt
  af van `DIARIZATION`:
  - `service` (productie): vlam-api doet het zelf (`response_format=diarized_json`).
    De hele opname gaat dan in één aanvraag, anders krijgt elk stuk eigen
    sprekerlabels. Zie [docs/vlam-ai.md](docs/vlam-ai.md#sprekerherkenning).
  - `local` (standaard lokaal, voor Ollama): de backend draait zelf
    [pyannote speaker-diarization-community-1](https://huggingface.co/pyannote/speaker-diarization-community-1),
    hetzelfde model als vlam-api. Daarna gaat elke beurt los naar Voxtral. Lange
    beurten worden geknipt zoals hierboven. De voortgang telt dan beurten.
  - `off`: geen sprekers; de schakelaar verdwijnt.

  Namen die de gebruiker invult, samengevoegde sprekers en verplaatste beurten
  blijven in de browser. De server kent alleen `S1`, `S2`, ….
- **De sleutel** van de transcriptiedienst zit alleen in de backend (een Container
  App-secret). De browser ziet hem nooit.
- **Niets blijft bewaard.** Audio staat alleen tijdens de verwerking in een
  tijdelijke map en wordt daarna gewist. Een klaar transcript blijft hoogstens
  een uur in het geheugen (`RESULT_TTL_SECONDS`), en in de browser alleen tot
  je het venster sluit. Er is geen database en er wordt niets in localStorage
  gezet. Het log bevat geen transcriptinhoud.

### Grenzen

| | Standaard | Instelling |
|---|---|---|
| Maximale duur | 2 uur | `MAX_AUDIO_SECONDS` (backend), `VITE_MAX_AUDIO_MINUTES` (frontend) |
| Maximale bestandsgrootte | 500 MB | `MAX_UPLOAD_MB`, `VITE_MAX_UPLOAD_MB` |
| Opnemen in de browser | stopt vanzelf na 2 uur, waarschuwt 5 minuten ervoor | volgt de maximale duur |
| Lengte van een stuk | 10 minuten | `CHUNK_SECONDS` |

De duur wordt drie keer gecontroleerd: in de browser vóór het uploaden (geen
300 MB uploaden om dan te horen dat het te lang is), bij binnenkomst met
ffprobe (antwoord 422), en na het omzetten. Dat laatste is voor opnames uit de
browser (webm), die vaak geen duur in de header hebben.

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

Open <http://localhost:5173>. Vite stuurt `/api` door naar de backend.

**Sprekerherkenning lokaal.** Die draait in de backend met pyannote (de
uv-groep `diarization`, die `uv sync` standaard meeneemt). Het model staat achter een gebruikersovereenkomst op Hugging Face,
dus alleen voor de eerste download moet je ingelogd zijn:

```bash
# 1. Accepteer de voorwaarden op
#    https://huggingface.co/pyannote/speaker-diarization-community-1
# 2. Eén keer inloggen (of zet HF_TOKEN in .env.local)
uv run hf auth login
```

Bij de eerste opname met sprekers wordt het model opgehaald. Daarna
staat het in `~/.cache/huggingface` en is geen sleutel meer nodig.
`DIARIZATION_MODEL` mag ook een map zijn waarin je het model zelf hebt gezet.
Zonder model biedt de app geen sprekerherkenning aan. Zonder
`.env.local` gebruikt de backend Ollama op `localhost:11434` met het model
hierboven. Andere waarden zet je in `.env.local` (zie `.env.example`).

Snelle check of Ollama en Voxtral werken:

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

Het image heeft geen pyannote: daarin herkent vlam-api de sprekers
(`DIARIZATION=service`, de standaard in het image). Met Ollama als dienst zet je
`DIARIZATION=off`, zoals hierboven.

### Tests

```bash
npm test          # frontend (vitest): service, state machine, export, NLDD-registratie
npm run test:api  # backend (pytest): knippen, beurten, API, adapter; gebruikt ffmpeg
uv run ruff check backend
```

`src/registration/nlddRegistration.test.ts` controleert dat elk `<nldd-*>`-element
in een template ook geïmporteerd wordt in `src/main.ts`. De app laadt NLDD per
component in plaats van het hele pakket (457 kB in plaats van 1,8 MB), en een
vergeten import levert anders stil een lege tag op.

## API

Volgt de [NL GOV API Design Rules](https://gitdocumentatie.logius.nl/publicatie/api/adr/)
waar dat voor zo'n kleine API zin heeft: `/api/v1`, meervoud, `problem+json` bij
fouten en een `API-Version`-header.

| | |
|---|---|
| `POST /api/v1/transcriptions` | multipart `file` (+ optioneel `language`, `speakers=true`, `numSpeakers`) → `202` met de taak en een `Location`-header. `413` te groot, `415` geen audio, `422` langer dan 2 uur, ongeldig aantal sprekers of sprekerherkenning niet beschikbaar |
| `GET /api/v1/transcriptions/{id}` | `{ status: queued \| converting \| diarizing \| transcribing \| done \| failed, progress: {completed, total}, durationSeconds, text?, speakers?, segments?, error? }`. `segments` is `[{speaker, start, end, text}]`, alleen met `speakers=true` |
| `GET /api/v1/features` | `{ speakers: bool }`: kan deze server sprekers herkennen |
| `DELETE /api/v1/transcriptions/{id}` | annuleren en alles weggooien |
| `GET /api/v1/health` | health probe |

De koppeling met de transcriptiedienst staat in één bestand:
`backend/app/transcriber.py`. Spreekt vlam-api een ander formaat dan Ollama,
dan verandert alleen dat bestand. Zie [docs/vlam-ai.md](docs/vlam-ai.md).

## Deployment

`azure-pipelines.yml` bouwt het image, zet het in de Azure Container Registry
van de resourcegroep en rolt het uit als één Container App. De app is extern
bereikbaar achter een IP-allowlist.

- **Eén replica, altijd aan** (1 vCPU / 2 GiB). Taken leven in het geheugen van
  dat ene proces. Bij meer replicas kan de browser bij een replica uitkomen die
  zijn taak niet kent, en bij schalen naar nul verdwijnen lopende taken.
- **Secrets** in de variable group `transcriptie-secrets`: `TRANSCRIBE_URL` en
  `TRANSCRIBE_API_KEY` (allebei als secret markeren), en optioneel
  `TRANSCRIBE_MODEL`, `TRANSCRIBE_API_KEY_HEADER` en `DIARIZATION` (standaard
  `service`). De pipeline zet ze als
  Container App-secrets.

Eenmalige setup: maak `transcriptie-secrets` aan, autoriseer de pipeline voor
`transcriptie-secrets` en de gedeelde variable group (`AZURE_SERVICE_CONNECTION`,
`ALLOWED_IP_1..4`), registreer `azure-pipelines.yml` en draai hem op `main`.

## Privacy, beveiliging en toegankelijkheid

- **AVG.** Opnames van overleggen bevatten persoonsgegevens. Laat een DPIA doen
  en neem de verwerking op in het verwerkingsregister. De app wijst gebruikers
  erop dat ze geen bijzondere persoonsgegevens uploaden zonder toestemming, en
  dat ze aanwezigen vragen of opnemen goed is.
- **Stemkenmerken.** Sprekerherkenning berekent per stem een kenmerk
  (embedding) om stukken van dezelfde stem te groeperen. Dat gebeurt alleen
  binnen één opname en alleen in het geheugen, tijdens de taak. Er is geen
  koppeling met namen of andere opnames, en niets wordt bewaard. Stemkenmerken
  liggen dicht tegen biometrische gegevens (art. 9 AVG) aan: neem dit mee in de
  DPIA. De app legt het de gebruiker uit onder "Goed om te weten".
- **Algoritmeregister.** vlam.ai hanteert *registreren tenzij* voor pilots en
  productie; zie [docs/vlam-ai.md](docs/vlam-ai.md).
- **AI-transparantie.** Het resultaat is gemarkeerd als automatisch gegenereerd,
  met het verzoek het te controleren. Dat staat ook in de .docx-export.
- **Beveiliging (BIO).** Strikte CSP (`script-src 'self'`), `Permissions-Policy`
  (microfoon alleen voor deze site), HSTS, `nosniff`, `no-referrer`. De container
  draait niet als root, secrets staan nooit in het image, en de uploadgrootte
  wordt gecontroleerd tijdens het binnenkomen.
- **Toegankelijkheid (WCAG 2.2 AA).** NLDD-componenten, een skip-link, live
  regions voor de voortgang (zonder elke seconde iets voor te lezen), focus naar
  het resultaat als het klaar is, en een opname die volledig met het
  toetsenbord te bedienen is. Getest met axe-core: geen overtredingen.

## Verder

- [docs/vlam-ai.md](docs/vlam-ai.md): de productie-transcriptiedienst, toegang
  krijgen en open punten.

## Bijdragen

Bijdragen zijn welkom, zie [CONTRIBUTING.md](CONTRIBUTING.md) en de
[gedragscode](CODE_OF_CONDUCT.md). Een kwetsbaarheid meld je volgens
[SECURITY.md](SECURITY.md), niet via een issue.

## Licentie

© Ministerie van Financiën. Gelicentieerd onder de [EUPL-1.2](LICENSE).
