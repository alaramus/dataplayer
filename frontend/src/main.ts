import { VueQueryPlugin } from "@tanstack/vue-query"
import { createPinia } from "pinia"
import { Dialog, Notify, Quasar } from "quasar"
import { createApp } from "vue"

import "@quasar/extras/material-icons/material-icons.css"
import "quasar/src/css/index.sass"

import App from "@/App.vue"
import { router } from "@/router"

createApp(App)
  // Pinia устанавливается до маршрутизатора: навигационный сторож обращается
  // к хранилищу аутентификации.
  .use(createPinia())
  .use(Quasar, { plugins: { Notify, Dialog } })
  .use(router)
  .use(VueQueryPlugin)
  .mount("#app")
