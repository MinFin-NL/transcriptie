<template>
  <nldd-container gap="16">
    <!-- role="status": een schermlezer hoort elke fase één keer (uploaden,
         omzetten, deel 3 van 12). De teller staat erbuiten, anders zou hij elke
         seconde opnieuw worden voorgelezen. -->
    <div role="status">
      <nldd-title size="4" heading-level="2" :text="heading" :supporting-text="filename" />
    </div>

    <nldd-progress-bar
      :indeterminate="fraction === null"
      :value="fraction === null ? undefined : Math.round(fraction * 100)"
      :text="barText"
      value-display="inline"
    />

    <nldd-text color="secondary">
      {{ hint }} <span aria-hidden="true">Bezig sinds {{ formatDuration(elapsedSeconds) }}.</span>
    </nldd-text>

    <nldd-button-group>
      <nldd-button appearance="secondary" text="Annuleren" @click="emit('cancel')" />
    </nldd-button-group>
  </nldd-container>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { Progress } from '../services/transcriptionService'
import { formatDuration } from '../utils/formatDuration'

const props = defineProps<{ filename: string; elapsedSeconds: number; progress: Progress }>()
const emit = defineEmits<{ cancel: [] }>()

const heading = computed(() => {
  switch (props.progress.phase) {
    case 'uploading':
      return 'Bezig met uploaden…'
    case 'queued':
      return 'In de wachtrij…'
    case 'converting':
      return 'Audio voorbereiden…'
    case 'transcribing':
      return props.progress.total > 1
        ? `Bezig met transcriberen: deel ${Math.min(props.progress.completed + 1, props.progress.total)} van ${props.progress.total}`
        : 'Bezig met transcriberen…'
  }
  return ''
})

const fraction = computed<number | null>(() => {
  const p = props.progress
  if (p.phase === 'uploading') return p.fraction
  if (p.phase === 'transcribing' && p.total > 1) return p.completed / p.total
  return null
})

const barText = computed(() => (props.progress.phase === 'uploading' ? 'Uploaden' : 'Transcriberen'))

const hint = computed(() => {
  const p = props.progress
  if (p.phase === 'queued') return 'Er wordt eerst een andere opname afgemaakt.'
  if (p.phase === 'transcribing' && p.durationSeconds)
    return `De opname duurt ${formatDuration(Math.round(p.durationSeconds))}. Lange opnames worden in stukken uitgeschreven; dat kan even duren.`
  return 'Laat dit venster open staan.'
})
</script>
