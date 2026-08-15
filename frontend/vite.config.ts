import { fileURLToPath, URL } from "node:url"
import { quasar, transformAssetUrls } from "@quasar/vite-plugin"
import vue from "@vitejs/plugin-vue"
import { defineConfig } from "vite"

export default defineConfig({
  build: {
    outDir: "../backend/app/frontend",
    emptyOutDir: true,
  },
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url)),
    },
  },
  css: {
    preprocessorOptions: {
      sass: {
        // node_modules поднят в корень bun-монорепозитория, поэтому quasar
        // лежит вне frontend/ и не может разрешить относительный импорт
        // переменных, который добавляет плагин.
        loadPaths: [fileURLToPath(new URL(".", import.meta.url))],
      },
    },
  },
  plugins: [
    vue({ template: { transformAssetUrls } }),
    quasar({ sassVariables: "src/quasar-variables.sass" }),
  ],
  server: {
    port: 5173,
  },
})
