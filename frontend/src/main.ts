import { VueQueryPlugin } from "@tanstack/vue-query"
import { createPinia } from "pinia"
import { Dialog, Notify, Quasar } from "quasar"
import { createApp } from "vue"

import "@quasar/extras/material-icons/material-icons.css"
import "quasar/src/css/index.sass"

import App from "@/App.vue"
import { router } from "@/router"
import { configureApiClient, createQueryClient } from "@/shared/api/configure"
import { watchSessionAcrossTabs } from "@/shared/auth/session"

const app = createApp(App)

// Pinia is installed first: both the client setup and the navigation guard
// read the auth store.
app.use(createPinia())
configureApiClient()

const queryClient = createQueryClient()
watchSessionAcrossTabs(queryClient)

app
  .use(Quasar, { plugins: { Notify, Dialog } })
  .use(router)
  .use(VueQueryPlugin, { queryClient })
  .mount("#app")
