/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Taal die met de aanvraag meegaat (ISO-639-1); leeg laat de dienst kiezen. */
  readonly VITE_TRANSCRIBE_LANGUAGE?: string
  /** Grootste toegestane bestand in MB. */
  readonly VITE_MAX_UPLOAD_MB?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
