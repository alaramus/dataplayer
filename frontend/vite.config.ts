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
        // node_modules is hoisted to the root of the bun monorepo, so quasar
        // sits outside frontend/ and cannot resolve the relative variables
        // import that the plugin injects.
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
    allowedHosts: true,
  },
})
