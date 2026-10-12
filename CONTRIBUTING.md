# Bijdragen aan Transcriptie

Fijn dat je wilt bijdragen! Een bug melden, een idee voorstellen, de
documentatie verbeteren en code schrijven zijn allemaal welkom.

Lees ook de [gedragscode](CODE_OF_CONDUCT.md). Een kwetsbaarheid meld je
**niet** via een issue maar zoals in [SECURITY.md](SECURITY.md) staat.

## Een issue openen

- **Bug:** wat deed je, wat verwachtte je, en wat gebeurde er? Vermeld je
  browser en, als het om een bestand gaat, het formaat en de duur. Voeg
  **geen opnames of transcripten van echte gesprekken** toe: daar staan
  persoonsgegevens in.
- **Idee of feature:** beschrijf eerst het probleem van de gebruiker, en pas
  daarna een oplossing. Een groter voorstel bespreken we eerst in het issue,
  voordat er code komt.

## Ontwikkelomgeving

Nodig: Node 26 (zie `.nvmrc`), [uv](https://docs.astral.sh/uv/), ffmpeg en
[Ollama](https://ollama.com) met Voxtral. De volledige stappen staan in de
[README](README.md#lokaal-draaien). Kort:

```bash
npm ci && uv sync
npm run api   # backend op :8010
npm run dev   # frontend op :5173
```

## Een wijziging voorstellen

1. Fork de repository en maak een branch vanaf `main` met een beschrijvende
   naam, bijvoorbeeld `fix/upload-webm-duur` of `feature/vtt-export`.
2. Houd een pull request klein en gericht op één ding.
3. Zorg dat alles groen is:

   ```bash
   npm run build            # vue-tsc + vite build
   npm test                 # frontend-tests (vitest)
   npm run test:api         # backend-tests (pytest, gebruikt ffmpeg)
   uv run ruff check backend && uv run ruff format --check backend
   ```

4. Beschrijf in de pull request wat er verandert en waarom, en hoe je het hebt
   getest. Voor een wijziging in de interface: voeg een schermafbeelding toe.
5. Onderteken je commits met `git commit -s`
   ([Developer Certificate of Origin](https://developercertificate.org/)).
   Daarmee verklaar je dat je de bijdrage onder de licentie van dit project
   mag aanbieden.

## Richtlijnen

- **Taal.** De interface, documentatie en commentaar in de code zijn in het
  Nederlands. Namen van functies en variabelen zijn in het Engels.
- **Stijl.** Volg de code eromheen. Python: `ruff` (de configuratie staat in
  `pyproject.toml`). TypeScript/Vue: strikte `vue-tsc`.
- **Interface.** Gebruik de componenten van het
  [NLDD Designsysteem](https://nederlandsedigitaledienst.github.io/design-system/)
  in plaats van eigen opmaak. Een nieuw `<nldd-*>`-element importeer je in
  `src/main.ts`; een test controleert dat.
- **Toegankelijkheid.** Elke wijziging moet met alleen het toetsenbord te
  bedienen zijn en goed werken met een schermlezer (WCAG 2.2 AA).
- **Privacy.** Audio en transcripten worden niet bewaard, niet gelogd en niet
  in de browser opgeslagen (localStorage). Een wijziging die dat verandert,
  bespreken we eerst in een issue.
- **Transcriptiedienst.** Alle kennis over hoe de dienst wordt aangeroepen staat
  in `backend/app/transcriber.py`. Houd dat zo.
- **Tests.** Een bugfix krijgt een test die zonder de fix faalt. Nieuwe
  functionaliteit krijgt tests.

## Licentie

Door bij te dragen ga je ermee akkoord dat je bijdrage onder de
[EUPL-1.2](LICENSE) valt, net als de rest van dit project.
