import { readdirSync, readFileSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'

// main.ts importeert NLDD per component. Vergeet je bij een nieuw <nldd-*> in
// een template de import, dan blijft het element stil een lege, ongestylede
// tag. Deze test vangt dat: elk gebruikt element moet geregistreerd zijn.
const SRC = join(__dirname, '..')

function vueFiles(dir: string): string[] {
  return readdirSync(dir, { withFileTypes: true }).flatMap((e) =>
    e.isDirectory() ? vueFiles(join(dir, e.name)) : e.name.endsWith('.vue') ? [join(dir, e.name)] : [],
  )
}

describe('NLDD registration', () => {
  it('registers every nldd-* element used in a template', async () => {
    // jsdom kent geen matchMedia; NLDD vraagt het op bij het laden.
    window.matchMedia ??= ((query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener() {},
      removeListener() {},
      addEventListener() {},
      removeEventListener() {},
      dispatchEvent: () => false,
    })) as typeof window.matchMedia

    const main = readFileSync(join(SRC, 'main.ts'), 'utf8')
    for (const [, spec] of main.matchAll(/import '(@nldd\/design-system\/[^']+)'/g)) {
      await import(/* @vite-ignore */ spec)
    }

    const used = new Set(vueFiles(SRC).flatMap((f) => readFileSync(f, 'utf8').match(/<nldd-[a-z-]+/g) ?? []))
    const missing = [...used].map((t) => t.slice(1)).filter((tag) => !customElements.get(tag))
    expect(missing).toEqual([])
  })
})
