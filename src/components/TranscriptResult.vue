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
      supporting-text="Spraakherkenning maakt fouten, vooral bij namen, vaktermen en door elkaar praten. Controleer en verbeter de tekst voordat je hem gebruikt."
    />

    <nldd-form-field label="Tekst" supporting-label="Je kunt de tekst hier aanpassen voordat je hem exporteert.">
      <nldd-multi-line-text-field :value="text" rows="14" resize="vertical" @input="onInput" />
    </nldd-form-field>

    <nldd-text color="secondary">{{ wordCount }} woorden</nldd-text>

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
import { computed, onMounted, ref } from 'vue'
import { baseName, docxBlob, download, textBlob } from '../services/exportService'
import { focusWhenRendered } from '../utils/focusWhenRendered'

const props = defineProps<{ text: string; filename: string }>()
const emit = defineEmits<{ 'update:text': [value: string]; reset: [] }>()

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
  const words = props.text.trim().split(/\s+/).filter(Boolean)
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
    await navigator.clipboard.writeText(props.text)
    notify('success', 'Tekst gekopieerd naar het klembord')
  } catch {
    notify('critical', 'Kopiëren lukte niet. Selecteer de tekst en kopieer hem met Ctrl+C.')
  }
}

function exportTxt() {
  download(textBlob(props.text), `${baseName(props.filename)}.txt`)
}

async function exportDocx() {
  docxBusy.value = true
  try {
    const name = baseName(props.filename)
    download(await docxBlob(props.text, `Transcript ${props.filename}`), `${name}.docx`)
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
