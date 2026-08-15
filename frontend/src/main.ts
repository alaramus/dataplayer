import { VueQueryPlugin } from "@tanstack/vue-query"
import { createPinia } from "pinia"
import { Dialog, Notify, Quasar } from "quasar"
import { createApp } from "vue"

import "@quasar/extras/material-icons/material-icons.css"
import "quasar/src/css/index.sass"

import App from "@/App.vue"
import { router } from "@/router"
import { configureApiClient, createQueryClient } from "@/shared/api/configure"

const app = createApp(App)

// Pinia устанавливается первой: и настройка клиента, и навигационный сторож
// обращаются к хранилищу аутентификации.
app.use(createPinia())
configureApiClient()

app
  .use(Quasar, { plugins: { Notify, Dialog } })
  .use(router)
  .use(VueQueryPlugin, { queryClient: createQueryClient() })
  .mount("#app")
