/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_URL: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}

/**
 * `markdown-it-task-lists` ships no types. It is a plain markdown-it plugin, so
 * the shape it is used with is the whole contract.
 */
declare module "markdown-it-task-lists" {
  const plugin: (parser: unknown, options?: { enabled?: boolean; label?: boolean }) => void
  export default plugin
}

// ECharts ships its locales as plain modules without declarations.
declare module "echarts/lib/i18n/langRU.js" {
  const locale: Parameters<typeof import("echarts/core").registerLocale>[1]
  export default locale
}

declare module "echarts/lib/i18n/langDE.js" {
  const locale: Parameters<typeof import("echarts/core").registerLocale>[1]
  export default locale
}

declare module "echarts/lib/i18n/langFR.js" {
  const locale: Parameters<typeof import("echarts/core").registerLocale>[1]
  export default locale
}
