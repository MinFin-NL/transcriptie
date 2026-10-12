import { createApp } from 'vue'
import App from './App.vue'
// Alleen de NLDD-componenten die deze app gebruikt. Elke import registreert
// zijn <nldd-*> custom element(s) (customElements.define), dus ze moeten er
// staan ook al gebruik je niets uit de module. Het hele pakket in één keer
// ('@nldd/design-system') kost ~1,4 MB extra aan o.a. de code-editor.
// Een nieuw nldd-*-element in een template? Voeg hier zijn import toe.
import '@nldd/design-system/app-view'
import '@nldd/design-system/banner'
import '@nldd/design-system/button'
import '@nldd/design-system/button-group'
import '@nldd/design-system/card'
import '@nldd/design-system/container'
import '@nldd/design-system/file-field'
import '@nldd/design-system/form-field'
import '@nldd/design-system/multi-line-text-field'
import '@nldd/design-system/notification'
import '@nldd/design-system/page'
import '@nldd/design-system/page-footer'
import '@nldd/design-system/progress-bar'
import '@nldd/design-system/rich-text'
import '@nldd/design-system/segmented-control'
import '@nldd/design-system/simple-section'
import '@nldd/design-system/skip-link'
import '@nldd/design-system/status-bar'
import '@nldd/design-system/text'
import '@nldd/design-system/title'
import '@nldd/design-system/top-navigation-bar'
import './assets/main.css'

createApp(App).mount('#app')
