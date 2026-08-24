import { fileURLToPath, URL } from "node:url"
import { quasar, transformAssetUrls } from "@quasar/vite-plugin"
import vue from "@vitejs/plugin-vue"
import { defineConfig } from "vitest/config"

export default defineConfig({
  plugins: [
    vue({ template: { transformAssetUrls } }),
    // Without the plugin Vitest picks up the Quasar server build, which cannot
    // install itself under jsdom.
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
    setupFiles: ["./vitest.setup.ts"],
    // A spy on a shared prototype outlives the test that installed it.
    restoreMocks: true,
    server: {
      deps: {
        inline: ["quasar"],
      },
    },
    // Playwright only picks files from tests/, so the suites do not overlap.
    include: ["src/**/*.spec.ts"],
  },
})
