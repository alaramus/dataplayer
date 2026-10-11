import { VueQueryPlugin } from "@tanstack/vue-query"
import { createPinia } from "pinia"
import { IconSet, Notify, Quasar } from "quasar"
import symbolsOutlined from "quasar/icon-set/material-symbols-outlined"
import { createApp } from "vue"

import "@fontsource-variable/inter/wght.css"
import "@fontsource-variable/inter/wght-italic.css"
import "@quasar/extras/material-symbols-outlined/material-symbols-outlined.css"
import "quasar/src/css/index.sass"
// After Quasar's own stylesheet: the colours the application draws itself
// with, both themes of them.
import "@/shared/ui/layers.css"
import "@/shared/ui/metrics.css"
import "@/shared/ui/typography.css"
import "@/shared/ui/theme.css"

import App from "@/App.vue"
import { router } from "@/router"
import { configureApiClient, createQueryClient } from "@/shared/api/configure"
import { applyLanguage, i18n, initialLanguage } from "@/shared/i18n"
import { watchSessionAcrossTabs } from "@/shared/auth/session"
import { symbolIcon } from "@/shared/ui/symbolIcons"
import { useThemeStore } from "@/stores/theme"

const app = createApp(App)

// Pinia is installed first: both the client setup and the navigation guard
// read the auth store.
app.use(createPinia())
configureApiClient()

const queryClient = createQueryClient()
watchSessionAcrossTabs(queryClient)

app
  .use(Quasar, { plugins: { Notify }, iconSet: symbolsOutlined })
  .use(router)
  .use(i18n)
  .use(VueQueryPlugin, { queryClient })

IconSet.iconMapFn = symbolIcon

/*
 * After Quasar and before the mount, and neither half of that is arbitrary.
 *
 * Installing the Dark plugin writes a theme to the document itself — light,
 * since nothing configures it — so a choice applied any earlier is overwritten
 * on the next line. Applied any later, the first frame is drawn light and a
 * dark theme opens with a flash of the other one.
 */
useThemeStore().apply()

// Mounted once the language is loaded, so the first frame is in it rather than
// in English for as long as the chunk takes to arrive.
void applyLanguage(initialLanguage()).finally(() => app.mount("#app"))
