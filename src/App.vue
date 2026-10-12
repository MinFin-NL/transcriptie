<template>
  <nldd-app-view>
    <nldd-page>
      <div slot="header">
        <nldd-status-bar
          variant="warning"
          text="Bètaversie: vragen of feedback? innovatiemanagementfinancien@minfin.nl"
          href="mailto:innovatiemanagementfinancien@minfin.nl"
        />
        <nldd-skip-link>
          <nldd-top-navigation-bar logo-title="Ministerie van Financiën" website-title="Transcriptie" website-href="/" />
        </nldd-skip-link>
      </div>

      <nldd-simple-section>
        <nldd-title
          slot="header"
          size="1"
          heading-level="1"
          text="Spraak omzetten naar tekst"
          supporting-text="Upload een audiobestand of neem direct op, tot 2 uur lang. Je krijgt de uitgeschreven tekst terug, die je kunt aanpassen, kopiëren of downloaden."
        />

        <nldd-card>
          <nldd-container padding="24" sm-padding="16" gap="24">
            <!-- Invoer: zichtbaar zolang er niet getranscribeerd wordt of klaar is. -->
            <template v-if="status === 'idle' || status === 'error'">
              <nldd-banner v-if="status === 'error'" variant="critical" text="Transcriberen is mislukt" :supporting-text="error">
                <nldd-button slot="actions" appearance="secondary" start-icon="refresh" text="Opnieuw proberen" @click="retry" />
              </nldd-banner>

              <nldd-segmented-control
                :value="mode"
                accessible-label="Hoe wil je audio aanleveren?"
                variant="icon-and-text"
                :disabled="recording"
                @change="onModeChange"
              >
                <nldd-segmented-control-item value="upload" icon="upload" text="Bestand uploaden" />
                <nldd-segmented-control-item value="record" icon="microphone" text="Opnemen" />
              </nldd-segmented-control>

              <!-- v-show, niet v-if: een gekozen bestand of opname blijft staan
                   als je even naar het andere tabblad kijkt. -->
              <SpeakerOptions v-if="speakersAvailable" v-model="speakerOptions" :disabled="recording" />

              <AudioUpload v-show="mode === 'upload'" @submit="submit" />
              <AudioRecorder v-show="mode === 'record'" @submit="submit" @recording-change="recording = $event" />
            </template>

            <TranscriptionProgress v-else-if="status === 'busy'" :filename="filename" :elapsed-seconds="elapsedSeconds" :progress="progress" @cancel="cancel" />

            <TranscriptResult
              v-else
              v-model:text="text"
              :filename="filename"
              :segments="segments"
              :names="names"
              :duration-seconds="durationSeconds"
              @reset="reset"
              @rename="rename"
              @merge="mergeSpeaker"
              @reassign="reassign"
              @edit="editTurn"
            />
          </nldd-container>
        </nldd-card>
      </nldd-simple-section>

      <nldd-simple-section>
        <nldd-title slot="header" size="3" heading-level="2" text="Goed om te weten" />
        <nldd-rich-text>
          <ul>
            <li>
              Upload geen opnames met bijzondere persoonsgegevens (zoals gezondheid of strafrechtelijke gegevens)
              zonder toestemming van je privacy officer.
            </li>
            <li>Vraag aan iedereen in de opname of het goed is dat je opneemt en laat uitschrijven.</li>
            <li>
              De opname gaat alleen naar de transcriptiedienst en wordt na het uitschrijven direct gewist. Het
              transcript blijft maximaal een uur op de server en daarna alleen in dit venster: sluit je het, dan
              is het weg.
            </li>
            <li>De tekst is gemaakt door spraakherkenning (AI). Controleer hem altijd voordat je hem gebruikt.</li>
            <li v-if="speakersAvailable">
              Sprekerherkenning deelt de opname op in beurten door stemmen met elkaar te vergelijken. Dat gebeurt
              alleen binnen deze ene opname: er wordt niemand herkend en er worden geen stemkenmerken bewaard. Het gaat
              soms mis, vooral als mensen door elkaar praten of op elkaar lijken. Namen die je invult blijven in je
              browser.
            </li>
          </ul>
        </nldd-rich-text>
      </nldd-simple-section>

      <nldd-page-footer slot="footer">
        <nldd-page-footer-legal-bar slot="legal-bar">
          <nldd-page-footer-legal-bar-item slot="start" text="Ministerie van Financiën" />
          <nldd-page-footer-legal-bar-item
            slot="end"
            href="mailto:innovatiemanagementfinancien@minfin.nl"
            text="Contact"
          />
        </nldd-page-footer-legal-bar>
      </nldd-page-footer>
    </nldd-page>
  </nldd-app-view>
</template>

<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'
import AudioRecorder from './components/AudioRecorder.vue'
import AudioUpload from './components/AudioUpload.vue'
import SpeakerOptions from './components/SpeakerOptions.vue'
import TranscriptionProgress from './components/TranscriptionProgress.vue'
import TranscriptResult from './components/TranscriptResult.vue'
import { useTranscription } from './composables/useTranscription'
import { fetchFeatures, type SpeakerOptions as SpeakerChoice } from './services/transcriptionService'

type Mode = 'upload' | 'record'

const mode = ref<Mode>('upload')
const recording = ref(false)

const {
  status,
  text,
  segments,
  names,
  durationSeconds,
  error,
  filename,
  elapsedSeconds,
  progress,
  start,
  cancel,
  retry,
  reset,
  rename,
  mergeSpeaker,
  reassign,
  editTurn,
} = useTranscription()

// Sprekerherkenning alleen aanbieden als de server het kan. Standaard aan: de
// app wordt vooral gebruikt voor overleggen.
const speakersAvailable = ref(false)
const speakerOptions = ref<SpeakerChoice>({ enabled: true })
onMounted(async () => {
  speakersAvailable.value = (await fetchFeatures()).speakers
})

function submit(audio: Blob, name: string) {
  void start(audio, name, speakersAvailable.value ? speakerOptions.value : undefined)
}

function onModeChange(event: Event) {
  const value = (event as CustomEvent<{ value?: string }>).detail?.value
  if (value === 'upload' || value === 'record') mode.value = value
}

// Waarschuwen voor wegnavigeren zolang er werk verloren zou gaan: een lopende
// opname of transcriptie, of een transcript dat nog niet is opgeslagen.
function beforeUnload(event: BeforeUnloadEvent) {
  if (recording.value || status.value === 'busy' || status.value === 'done') {
    event.preventDefault()
  }
}
onMounted(() => window.addEventListener('beforeunload', beforeUnload))
onBeforeUnmount(() => window.removeEventListener('beforeunload', beforeUnload))
</script>
