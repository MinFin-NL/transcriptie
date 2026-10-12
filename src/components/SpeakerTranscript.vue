<template>
  <nldd-container gap="24">
    <!-- Sprekers: hier een naam geven werkt meteen door in elke beurt en in de
         export. Namen blijven in de browser. -->
    <section aria-labelledby="sprekers-titel">
      <nldd-container gap="12">
        <nldd-title
          id="sprekers-titel"
          size="5"
          heading-level="3"
          text="Sprekers"
          supporting-text="Geef sprekers een naam. Die staat dan bij elke beurt en in de export. Namen blijven in je browser."
        />
        <ul class="speakers">
          <li v-for="id in ids" :key="id" class="speaker" :style="colorStyle(id)">
            <nldd-avatar class="speaker__avatar" :name="label(id)" color="inherit" size="40" decorative />
            <nldd-container gap="4" class="speaker__main">
              <nldd-text-field
                :value="names[id] ?? ''"
                :placeholder="defaultLabel(id)"
                :accessible-label="`Naam voor ${defaultLabel(id)}`"
                autocomplete="off"
                @input="onRename(id, $event)"
                @change="announceRename(id)"
              />
              <nldd-text size="sm" color="secondary">{{ statsText(id) }}</nldd-text>
            </nldd-container>
            <nldd-button
              v-if="ids.length > 1"
              appearance="neutral-transparent"
              size="sm"
              start-icon="git-merge"
              text="Samenvoegen"
              :accessible-label="`${label(id)} samenvoegen met een andere spreker`"
              expandable
            >
              <nldd-menu slot="popup">
                <nldd-menu-group :text="`${label(id)} is eigenlijk…`">
                  <nldd-menu-item
                    v-for="other in ids.filter((o) => o !== id)"
                    :key="other"
                    :text="label(other)"
                    @select="merge(id, other)"
                  />
                </nldd-menu-group>
              </nldd-menu>
            </nldd-button>
          </li>
        </ul>
      </nldd-container>
    </section>

    <!-- De beurten. Een lijst, zodat een schermlezer zegt hoeveel het er zijn;
         elke beurt begint met de naam als tekst. -->
    <section aria-labelledby="beurten-titel">
      <nldd-container gap="12">
        <nldd-title
          id="beurten-titel"
          size="5"
          heading-level="3"
          text="Beurten"
          supporting-text="Je kunt de tekst per beurt aanpassen, of een beurt aan een andere spreker geven."
        />
        <ol class="turns">
          <li v-for="(seg, i) in segments" :key="`${seg.speaker}-${seg.start}`" class="turn" :style="colorStyle(seg.speaker)">
            <div class="turn__head">
              <nldd-avatar class="turn__avatar" :name="label(seg.speaker)" color="inherit" size="24" decorative />
              <nldd-text weight="bold">{{ label(seg.speaker) }}</nldd-text>
              <nldd-text size="sm" color="secondary">
                <span aria-hidden="true">{{ timestamp(seg.start) }}</span>
                <span class="visually-hidden">, vanaf {{ spokenTime(seg.start) }}</span>
              </nldd-text>
              <nldd-icon-button
                v-if="ids.length > 1"
                class="turn__action"
                appearance="neutral-transparent"
                size="sm"
                icon="swap"
                text="Andere spreker"
                :accessible-label="`Beurt van ${label(seg.speaker)} op ${spokenTime(seg.start)} aan een andere spreker geven`"
              >
                <nldd-menu slot="popup">
                  <nldd-menu-group text="Deze beurt is van…">
                    <nldd-menu-item
                      v-for="other in ids.filter((o) => o !== seg.speaker)"
                      :key="other"
                      :text="label(other)"
                      @select="reassign(i, other)"
                    />
                  </nldd-menu-group>
                </nldd-menu>
              </nldd-icon-button>
            </div>
            <nldd-multi-line-text-field
              :value="seg.text"
              rows="2"
              resize="auto"
              :accessible-label="`Tekst van ${label(seg.speaker)}, ${spokenTime(seg.start)}`"
              @input="onEdit(i, $event)"
            />
          </li>
        </ol>
      </nldd-container>
    </section>

    <!-- Meldt wat een hernoeming of samenvoeging deed; het effect staat soms
         ver buiten beeld. -->
    <div role="status" class="visually-hidden">{{ announcement }}</div>
  </nldd-container>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { timestamp } from '../services/exportService'
import type { Segment } from '../services/transcriptionService'
import { speakerIds, speakerLabel, speakerStats, type Names } from '../utils/turns'

const props = defineProps<{ segments: Segment[]; names: Names }>()
const emit = defineEmits<{
  rename: [speaker: string, name: string]
  merge: [from: string, into: string]
  reassign: [index: number, speaker: string]
  edit: [index: number, text: string]
}>()

const announcement = ref('')

const ids = computed(() => {
  // Volgorde van eerste keer spreken, op het nummer: na samenvoegen blijft
  // Spreker 3 op zijn plek.
  return speakerIds(props.segments).sort((a, b) => num(a) - num(b))
})
const stats = computed(() => speakerStats(props.segments))

// Kleur helpt herkennen, maar draagt geen informatie: de naam staat er altijd
// als tekst bij (WCAG 1.4.1).
const PALETTE = ['lintblauw', 'oranje', 'groen', 'violet', 'robijnrood', 'hemelblauw', 'bruin', 'mosgroen']

function num(id: string): number {
  return Number(/^S(\d+)$/.exec(id)?.[1] ?? 999)
}

function colorStyle(id: string) {
  const family = PALETTE[(num(id) - 1) % PALETTE.length] ?? 'neutral'
  return { '--speaker-color': `var(--primitives-color-${family}-600)` }
}

function label(id: string) {
  return speakerLabel(id, props.names)
}

function defaultLabel(id: string) {
  return speakerLabel(id)
}

function statsText(id: string) {
  const st = stats.value[id]
  if (!st) return ''
  const turns = st.turns === 1 ? '1 beurt' : `${st.turns} beurten`
  const time = st.seconds < 60 ? `${Math.round(st.seconds)} s` : `${Math.round(st.seconds / 60)} min`
  return `${turns} · ${time}`
}

/** 72 → "1 minuut en 12 seconden": de toegankelijke naam van een tijd. */
function spokenTime(seconds: number): string {
  const t = Math.floor(seconds)
  const h = Math.floor(t / 3600)
  const m = Math.floor((t % 3600) / 60)
  const s = t % 60
  const parts = [
    h ? `${h} uur` : '',
    m ? `${m} ${m === 1 ? 'minuut' : 'minuten'}` : '',
    s || (!h && !m) ? `${s} ${s === 1 ? 'seconde' : 'seconden'}` : '',
  ].filter(Boolean)
  return parts.length > 1 ? `${parts.slice(0, -1).join(', ')} en ${parts.at(-1)}` : parts[0]!
}

function valueOf(event: Event): string {
  return (event as CustomEvent<{ value?: string }>).detail?.value ?? (event.target as HTMLInputElement)?.value ?? ''
}

function onRename(id: string, event: Event) {
  emit('rename', id, valueOf(event))
}

function announceRename(id: string) {
  const n = stats.value[id]?.turns ?? 0
  const name = props.names[id]?.trim()
  announcement.value = name
    ? `${defaultLabel(id)} heet nu ${name}, ${n === 1 ? '1 beurt' : `${n} beurten`} aangepast.`
    : `${defaultLabel(id)} heeft geen naam meer.`
}

function merge(from: string, into: string) {
  const n = stats.value[from]?.turns ?? 0
  const fromLabel = label(from)
  emit('merge', from, into)
  announcement.value = `${fromLabel} samengevoegd met ${label(into)}, ${n === 1 ? '1 beurt' : `${n} beurten`} verplaatst.`
}

function reassign(index: number, speaker: string) {
  emit('reassign', index, speaker)
  announcement.value = `Beurt gegeven aan ${label(speaker)}.`
}

function onEdit(index: number, event: Event) {
  emit('edit', index, valueOf(event))
}
</script>

<style scoped>
.speakers,
.turns {
  list-style: none;
  margin: 0;
  padding: 0;
  display: grid;
  gap: var(--primitives-space-16);
}

.speaker {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  align-items: start;
  gap: var(--primitives-space-12);
}

.speaker__avatar,
.turn__avatar {
  color: var(--speaker-color);
}

.speaker__avatar {
  inline-size: 40px;
  block-size: 40px;
}

.turn {
  display: grid;
  gap: var(--primitives-space-8);
  padding-inline-start: var(--primitives-space-12);
  border-inline-start: 3px solid var(--speaker-color);
}

.turn__head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--primitives-space-8);
}

.turn__avatar {
  inline-size: 24px;
  block-size: 24px;
}

.turn__action {
  margin-inline-start: auto;
}

@media (max-width: 640px) {
  .speaker {
    grid-template-columns: auto minmax(0, 1fr);
  }

  .speaker > nldd-button {
    grid-column: 2;
  }
}
</style>
