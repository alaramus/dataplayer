import { VueQueryPlugin } from "@tanstack/vue-query"
import { createPinia } from "pinia"
import { Notify, Quasar } from "quasar"
import { createApp } from "vue"

import "@quasar/extras/material-icons/material-icons.css"
import "quasar/src/css/index.sass"
// After Quasar's own stylesheet: the colours the application draws itself
// with, both themes of them.
import "@/shared/ui/layers.css"
import "@/shared/ui/theme.css"

import App from "@/App.vue"
import { router } from "@/router"
import { configureApiClient, createQueryClient } from "@/shared/api/configure"
import { watchSessionAcrossTabs } from "@/shared/auth/session"
import { useThemeStore } from "@/stores/theme"

const app = createApp(App)

// Pinia is installed first: both the client setup and the navigation guard
// read the auth store.
app.use(createPinia())
configureApiClient()

const queryClient = createQueryClient()
watchSessionAcrossTabs(queryClient)

app
  .use(Quasar, { plugins: { Notify } })
  .use(router)
  .use(VueQueryPlugin, { queryClient })

/*
 * After Quasar and before the mount, and neither half of that is arbitrary.
 *
 * Installing the Dark plugin writes a theme to the document itself — light,
 * since nothing configures it — so a choice applied any earlier is overwritten
 * on the next line. Applied any later, the first frame is drawn light and a
 * dark theme opens with a flash of the other one.
 */
useThemeStore().apply()

app.mount("#app")
