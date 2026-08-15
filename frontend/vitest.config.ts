import { fileURLToPath, URL } from "node:url"
import { quasar, transformAssetUrls } from "@quasar/vite-plugin"
import vue from "@vitejs/plugin-vue"
import { defineConfig } from "vitest/config"

export default defineConfig({
  plugins: [
    vue({ template: { transformAssetUrls } }),
    // Без плагина Vitest подхватывает серверную сборку Quasar, которая в jsdom
    // не устанавливается.
    quasar({ sassVariables: "src/quasar-variables.sass" }),
  ],
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url)),
    },
  },
  css: {
    preprocessorOptions: {
      sass: {
        loadPaths: [fileURLToPath(new URL(".", import.meta.url))],
      },
    },
  },
  test: {
    environment: "jsdom",
    server: {
      deps: {
        inline: ["quasar"],
      },
    },
    // Playwright берёт свои файлы только из tests/, наборы не пересекаются.
    include: ["src/**/*.spec.ts"],
  },
})
