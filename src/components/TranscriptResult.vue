<template>
  <nldd-container gap="16">
    <!-- Focus komt hier terecht zodra het transcript klaar is, zodat een
         schermlezer- of toetsenbordgebruiker meteen bij het resultaat is. -->
    <div ref="heading" tabindex="-1" class="result__heading">
      <nldd-title size="4" heading-level="2" text="Transcript" :supporting-text="filename" />
    </div>

    <nldd-banner
      variant="neutral"
      size="sm"
      text="Automatisch gegenereerd"
:supporting-text="
        segments
          ? 'Spraakherkenning maakt fouten, vooral bij namen, vaktermen en door elkaar praten, en een beurt kan bij de verkeerde spreker staan. Controleer en verbeter het transcript voordat je het gebruikt.'
          : 'Spraakherkenning maakt fouten, vooral bij namen, vaktermen en door elkaar praten. Controleer en verbeter de tekst voordat je hem gebruikt.'
      "
    />

    <SpeakerTranscript
      v-if="segments"
      :segments="segments"
      :names="names"
      @rename="(id, name) => emit('rename', id, name)"
      @merge="(from, into) => emit('merge', from, into)"
      @reassign="(i, id) => emit('reassign', i, id)"
      @edit="(i, value) => emit('edit', i, value)"
    />

    <nldd-form-field
      v-else
      label="Tekst"
      supporting-label="Je kunt de tekst hier aanpassen voordat je hem exporteert."
    >
      <nldd-multi-line-text-field :value="text" rows="14" resize="vertical" @input="onInput" />
    </nldd-form-field>

    <nldd-text color="secondary">{{ wordCount }} woorden</nldd-text>

    <!-- Wat er in de export komt. Kopiëren en .txt volgen dezelfde keuze. -->
    <nldd-form-field v-if="segments" label="In de export">
      <nldd-container gap="8">
        <nldd-checkbox-field label="Sprekernamen" :checked="options.names" @change="toggle('names', $event)" />
        <nldd-checkbox-field label="Tijden" :checked="options.times" @change="toggle('times', $event)" />
        <nldd-checkbox-field
          label="Word-bestand als tabel (tijd, spreker, tekst)"
          :checked="options.table"
          @change="toggle('table', $event)"
        />
      </nldd-container>
    </nldd-form-field>

    <nldd-button-group>
      <nldd-button appearance="primary" start-icon="copy" text="Kopiëren" @click="copy" />
      <nldd-button appearance="secondary" start-icon="download" text="Download .txt" @click="exportTxt" />
      <nldd-button
        appearance="secondary"
        start-icon="download"
        text="Download .docx"
        :loading="docxBusy"
        loading-text="Word-bestand maken"
        @click="exportDocx"
      />
    </nldd-button-group>

    <nldd-button-group>
      <nldd-button appearance="neutral-transparent" start-icon="refresh" text="Nieuwe transcriptie" @click="emit('reset')" />
    </nldd-button-group>

    <nldd-notification
      v-for="n in notifications"
      :key="n.id"
      :variant="n.variant"
      :text="n.text"
      :duration="n.variant === 'success' ? 4000 : 0"
      @dismiss="dismiss(n.id)"
    />
  </nldd-container>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import {
  baseName,
  docxBlob,
  download,
  speakerText,
  textBlob,
  type SpeakerExport,
  type SpeakerExportOptions,
} from '../services/exportService'
import type { Segment } from '../services/transcriptionService'
import { focusWhenRendered } from '../utils/focusWhenRendered'
import { speakerLabel, type Names } from '../utils/turns'
import SpeakerTranscript from './SpeakerTranscript.vue'

const props = withDefaults(
  defineProps<{
    text: string
    filename: string
    segments?: Segment[] | null
    names?: Names
    durationSeconds?: number | null
  }>(),
  { segments: null, names: () => ({}), durationSeconds: null },
)
const emit = defineEmits<{
  'update:text': [value: string]
  reset: []
  rename: [speaker: string, name: string]
  merge: [from: string, into: string]
  reassign: [index: number, speaker: string]
  edit: [index: number, text: string]
}>()

const options = reactive<Required<SpeakerExportOptions>>({ names: true, times: true, table: false })

function toggle(key: keyof SpeakerExportOptions, event: Event) {
  options[key] = !!(event as CustomEvent<{ checked?: boolean }>).detail?.checked
}

const speakerExport = computed<SpeakerExport | null>(() =>
  props.segments
    ? {
        segments: props.segments,
        label: (id) => speakerLabel(id, props.names),
        options: { ...options },
        durationSeconds: props.durationSeconds,
      }
    : null,
)

/** Wat kopiëren en .txt opleveren: met sprekers als verslag, anders de tekst. */
const exportText = computed(() => (speakerExport.value ? speakerText(speakerExport.value) : props.text))

const heading = ref<HTMLElement | null>(null)
const docxBusy = ref(false)

interface Note {
  id: number
  variant: 'success' | 'critical'
  text: string
}
const notifications = ref<Note[]>([])
let nextId = 0

onMounted(() => focusWhenRendered(heading.value))

const wordCount = computed(() => {
  const source = props.segments ? props.segments.map((s) => s.text).join(' ') : props.text
  const words = source.trim().split(/\s+/).filter(Boolean)
  return words.length.toLocaleString('nl-NL')
})

function notify(variant: Note['variant'], text: string) {
  notifications.value.push({ id: nextId++, variant, text })
}

function dismiss(id: number) {
  notifications.value = notifications.value.filter((n) => n.id !== id)
}

function onInput(event: Event) {
  const value = (event as CustomEvent<{ value?: string }>).detail?.value ?? (event.target as HTMLInputElement)?.value ?? ''
  emit('update:text', value)
}

async function copy() {
  try {
    await navigator.clipboard.writeText(exportText.value)
    notify('success', 'Tekst gekopieerd naar het klembord')
  } catch {
    notify('critical', 'Kopiëren lukte niet. Selecteer de tekst en kopieer hem met Ctrl+C.')
  }
}

function exportTxt() {
  download(textBlob(exportText.value), `${baseName(props.filename)}.txt`)
}

async function exportDocx() {
  docxBusy.value = true
  try {
    const name = baseName(props.filename)
    const blob = await docxBlob(props.text, `Transcript ${props.filename}`, speakerExport.value ?? undefined)
    download(blob, `${name}.docx`)
  } catch {
    notify('critical', 'Het Word-bestand kon niet worden gemaakt. Probeer de .txt-export.')
  } finally {
    docxBusy.value = false
  }
}
</script>

<style scoped>
.result__heading:focus {
  outline: none;
}

.result__heading:focus-visible {
  outline: var(--semantics-focus-ring-outline);
  outline-offset: var(--semantics-focus-ring-outline-offset);
  box-shadow: var(--semantics-focus-ring-box-shadow);
}
</style>
