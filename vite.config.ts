/// <reference types="vitest/config" />
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// Lokaal draait de backend (uvicorn) op :8010 (8000 is vaak al bezet); de Vite-devserver stuurt /api
// daarheen door, zoals in productie alles van één origin komt.
const API_TARGET = process.env.API_TARGET || 'http://127.0.0.1:8010'

export default defineConfig(() => {
  return {
    plugins: [
      vue({
        template: {
          compilerOptions: {
            // NLDD levert Lit-webcomponents. Zonder dit ziet Vue elke <nldd-*>
            // als onbekend Vue-component; hiermee worden het gewone elementen.
            isCustomElement: (tag) => tag.startsWith('nldd-'),
          },
        },
      }),
    ],
    server: {
      proxy: {
        // Uploads van tot 500 MB en lange taken: geen time-out op de proxy.
        '/api': { target: API_TARGET, changeOrigin: true, timeout: 0, proxyTimeout: 0 },
      },
    },
    test: {
      environment: 'jsdom',
    },
  }
})
