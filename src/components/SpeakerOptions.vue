<template>
  <nldd-container gap="16">
    <nldd-switch-field
      label="Sprekers herkennen"
      :checked="modelValue.enabled"
      :disabled="disabled"
      @change="onToggle"
    />
    <nldd-text size="sm" color="secondary" class="options__hint">
      Handig voor overleggen en interviews: je ziet per beurt wie er sprak. Het uitschrijven duurt iets langer.
    </nldd-text>

    <nldd-form-field
      v-if="modelValue.enabled"
      label="Hoeveel mensen spreken er?"
      supporting-label="Weet je het, dan worden de sprekers beter uit elkaar gehouden."
    >
      <nldd-dropdown :disabled="disabled" @change="onCount">
        <select :value="String(modelValue.count ?? '')">
          <option value="">Weet ik niet</option>
          <option v-for="n in COUNTS" :key="n" :value="String(n)">{{ n }}</option>
        </select>
      </nldd-dropdown>
    </nldd-form-field>
  </nldd-container>
</template>

<script setup lang="ts">
import type { SpeakerOptions } from '../services/transcriptionService'

const props = defineProps<{ modelValue: SpeakerOptions; disabled?: boolean }>()
const emit = defineEmits<{ 'update:modelValue': [value: SpeakerOptions] }>()

const COUNTS = [2, 3, 4, 5, 6, 7, 8, 9, 10]

function onToggle(event: Event) {
  const checked = !!(event as CustomEvent<{ checked?: boolean }>).detail?.checked
  emit('update:modelValue', { ...props.modelValue, enabled: checked })
}

function onCount(event: Event) {
  const raw = (event as CustomEvent<{ value?: string }>).detail?.value ?? (event.target as HTMLSelectElement)?.value
  const count = Number(raw) || undefined
  emit('update:modelValue', { ...props.modelValue, count })
}
</script>

<style scoped>
/* De uitleg hoort bij de schakelaar erboven, niet bij het veld eronder. */
.options__hint {
  margin-block-start: calc(-1 * var(--primitives-space-12));
}
</style>
