<template>
  <nldd-container gap="16">
    <nldd-banner
      v-if="!supported"
      variant="warning"
      size="sm"
      text="Opnemen werkt niet in deze browser"
      supporting-text="Gebruik een recente versie van Edge, Chrome, Firefox of Safari, of upload een bestand."
    />

    <template v-else>
      <nldd-banner v-if="recorder.error.value" variant="critical" size="sm" :text="recorder.error.value" />

      <!-- Opnemen loopt: een duidelijke, tekstuele status (niet alleen kleur). -->
      <div v-if="state === 'recording'" class="recorder__live">
        <span class="recorder__dot" aria-hidden="true" />
        <nldd-text weight="bold">Opname loopt</nldd-text>
        <!-- De teller zelf wordt niet voorgelezen: elke seconde een melding is
             voor een schermlezer alleen ruis. -->
        <nldd-text class="recorder__clock" aria-hidden="true">
          {{ formatDuration(recorder.elapsedSeconds.value) }} / {{ formatDuration(MAX_DURATION_SECONDS) }}
        </nldd-text>
      </div>
      <nldd-banner
        v-if="state === 'recording' && remaining <= WARN_SECONDS"
        variant="warning"
        size="sm"
        :text="`Nog ${Math.ceil(remaining / 60)} minuten`"
        :supporting-text="`Een opname stopt vanzelf na ${MAX_DURATION_SECONDS / 3600} uur.`"
      />
      <nldd-banner
        v-if="state === 'stopped' && stoppedAtLimit"
        variant="neutral"
        size="sm"
        :text="`De opname is na ${MAX_DURATION_SECONDS / 3600} uur vanzelf gestopt.`"
      />

      <div v-if="state === 'stopped' && recorder.recordingUrl.value" class="recorder__result">
        <nldd-text>
          Opname van {{ formatDuration(recorder.elapsedSeconds.value) }}
          ({{ formatBytes(recorder.recording.value?.size ?? 0) }}). Luister hem eventueel terug.
        </nldd-text>
        <audio :src="recorder.recordingUrl.value" controls preload="metadata" class="recorder__audio">
          Je browser kan de opname niet afspelen.
        </audio>
      </div>


      <!-- Eén regio voor statuswissels, zodat een schermlezer hoort wat er gebeurt. -->
      <p class="visually-hidden" role="status">{{ announcement }}</p>

      <nldd-button-group>
        <nldd-button
          v-if="state !== 'recording'"
          ref="startButton"
          :appearance="state === 'stopped' ? 'secondary' : 'primary'"
          start-icon="microphone"
          :text="state === 'stopped' ? 'Opnieuw opnemen' : 'Start opname'"
          :loading="state === 'requesting'"
          loading-text="Microfoon starten"
          :disabled="disabled"
          @click="recorder.start()"
        />
        <nldd-button
          v-else
          ref="stopButton"
          appearance="destructive"
          start-icon="media-stop-filled"
          text="Stop opname"
          @click="recorder.stop()"
        />
        <nldd-button
          v-if="state === 'stopped'"
          appearance="primary"
          text="Transcriberen"
          :disabled="disabled"
          @click="submit"
        />
        <nldd-button
          v-if="state === 'stopped'"
          appearance="neutral-transparent"
          start-icon="trash"
          text="Verwijderen"
          :disabled="disabled"
          @click="recorder.discard()"
        />
      </nldd-button-group>
    </template>
  </nldd-container>
</template>

<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import { extensionFor, isRecordingSupported, useRecorder } from '../composables/useRecorder'
import { MAX_DURATION_SECONDS } from '../services/transcriptionService'
import { formatBytes, formatDuration } from '../utils/formatDuration'
import { focusWhenRendered } from '../utils/focusWhenRendered'

defineProps<{ disabled?: boolean }>()
const emit = defineEmits<{
  submit: [audio: Blob, filename: string]
  'recording-change': [recording: boolean]
}>()

const supported = isRecordingSupported()
const recorder = useRecorder()
const state = recorder.state

const startButton = ref<HTMLElement | null>(null)
const stopButton = ref<HTMLElement | null>(null)

// Waarschuwen in de laatste vijf minuten, en op de grens zelf stoppen: een
// langere opname zou de server toch weigeren. 32 kbit/s maakt van twee uur zo'n
// 30 MB, ruim onder de uploadgrens.
const WARN_SECONDS = 5 * 60
const remaining = computed(() => MAX_DURATION_SECONDS - recorder.elapsedSeconds.value)
const stoppedAtLimit = ref(false)

watch(remaining, (left) => {
  if (state.value === 'recording' && left <= 0) {
    stoppedAtLimit.value = true
    recorder.stop()
  }
})

const announcement = computed(() => {
  switch (state.value) {
    case 'recording':
      return 'Opname gestart.'
    case 'stopped':
      return 'Opname gestopt. Je kunt hem nu transcriberen.'
    default:
      return ''
  }
})

// De start- en stopknop wisselen van plaats; zonder dit valt de focus terug
// op de body en moet een toetsenbordgebruiker opnieuw beginnen met tabben.
watch(state, async (now, before) => {
  emit('recording-change', now === 'recording')
  if (now === 'recording') stoppedAtLimit.value = false
  await nextTick()
  if (now === 'recording') focusWhenRendered(stopButton.value)
  else if (before === 'recording') focusWhenRendered(startButton.value)
})

function submit() {
  const blob = recorder.recording.value
  if (!blob) return
  const stamp = new Date().toISOString().slice(0, 16).replace('T', '_').replace(':', '-')
  emit('submit', blob, `opname-${stamp}.${extensionFor(blob.type)}`)
}
</script>

<style scoped>
.recorder__live {
  display: flex;
  align-items: center;
  gap: 8px;
}

.recorder__dot {
  inline-size: 12px;
  block-size: 12px;
  border-radius: 50%;
  background: var(--semantics-content-critical-color);
  animation: recorder-pulse 1.2s ease-in-out infinite;
}

.recorder__clock {
  font-variant-numeric: tabular-nums;
}

.recorder__result {
  display: grid;
  gap: 8px;
}

.recorder__audio {
  inline-size: 100%;
  max-inline-size: 480px;
}

@keyframes recorder-pulse {
  50% {
    opacity: 0.3;
  }
}

@media (prefers-reduced-motion: reduce) {
  .recorder__dot {
    animation: none;
  }
}
</style>
