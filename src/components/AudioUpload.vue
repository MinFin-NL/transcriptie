<template>
  <nldd-container gap="16">
    <nldd-form-field
      label="Audiobestand"
      :supporting-label="`mp3, m4a, wav, webm, ogg of mp4. Maximaal ${MAX_HOURS} uur en ${MAX_UPLOAD_MB} MB.`"
    >
      <nldd-file-field
        :accept="ACCEPT"
        :invalid="!!error"
        :disabled="disabled"
        @change="onChange"
      />
    </nldd-form-field>

    <nldd-banner v-if="error" variant="critical" size="sm" :text="error" />

    <nldd-button-group>
      <nldd-button
        appearance="primary"
        text="Transcriberen"
        :disabled="!file || !!error || checking || disabled"
        @click="submit"
      />
    </nldd-button-group>
  </nldd-container>
</template>

<script setup lang="ts">
import { ref, shallowRef } from 'vue'
import { MAX_DURATION_SECONDS, MAX_UPLOAD_BYTES, MAX_UPLOAD_MB } from '../services/transcriptionService'
import { audioDuration } from '../utils/audioDuration'
import { formatDuration } from '../utils/formatDuration'

defineProps<{ disabled?: boolean }>()
const emit = defineEmits<{ submit: [audio: Blob, filename: string] }>()

// De backend zet alles met ffmpeg om, dus elk gangbaar audioformaat werkt. mp4
// en webm kunnen ook video zijn; daar gebruiken we alleen het geluid van.
const ACCEPT = 'audio/*,.mp3,.m4a,.wav,.webm,.ogg,.oga,.flac,.mp4,.mpeg,.mpga'
const EXTENSIONS = /\.(mp3|m4a|wav|webm|ogg|oga|flac|mp4|mpeg|mpga)$/i

const MAX_HOURS = MAX_DURATION_SECONDS / 3600

const file = shallowRef<File | null>(null)
const error = ref('')
const checking = ref(false)

async function onChange(event: Event) {
  const files = (event as CustomEvent<{ files: File[] }>).detail?.files ?? []
  const chosen = files[0] ?? null
  file.value = chosen
  error.value = chosen ? validate(chosen) : ''
  if (!chosen || error.value) return

  // De duur meten vóór het uploaden: anders wacht iemand op 300 MB upload om
  // dan te horen dat de opname te lang is. Weet de browser de duur niet, dan
  // controleert de server.
  checking.value = true
  const seconds = await audioDuration(chosen)
  checking.value = false
  if (file.value !== chosen) return
  if (seconds && seconds > MAX_DURATION_SECONDS + 1) {
    error.value = `${chosen.name} duurt ${formatDuration(Math.round(seconds))}. Het maximum is ${MAX_HOURS} uur; kort de opname in of splits hem op.`
  }
}

function validate(f: File): string {
  if (!f.type.startsWith('audio/') && !EXTENSIONS.test(f.name)) {
    return `${f.name} is geen audiobestand dat we kunnen transcriberen.`
  }
  if (f.size > MAX_UPLOAD_BYTES) {
    return `${f.name} is groter dan ${MAX_UPLOAD_MB} MB. Kort de opname in of splits hem op.`
  }
  if (f.size === 0) return `${f.name} is leeg.`
  return ''
}

function submit() {
  if (file.value && !error.value) emit('submit', file.value, file.value.name)
}
</script>
