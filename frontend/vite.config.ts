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
  // Libraries reached only through a lazily loaded panel are found by the dev
  // server when that panel is first opened; it then bundles them and reloads
  // the page, which drops whatever was on screen — a PDF, a diagram, the 3D
  // graph. Bundled at start instead, so a fresh dev server never reloads.
  optimizeDeps: {
    include: [
      "mermaid",
      "pdfjs-dist",
      "three",
      "three/addons/controls/OrbitControls.js",
      "echarts/core",
      "echarts/charts",
      "echarts/components",
      "echarts/renderers",
    ],
  },
  server: {
    port: 5173,
    allowedHosts: true,
  },
})
