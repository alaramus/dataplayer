import js from "@eslint/js"
import { defineConfigWithVueTs, vueTsConfigs } from "@vue/eslint-config-typescript"
import pluginVue from "eslint-plugin-vue"

export default defineConfigWithVueTs(
  // src/client генерируется openapi-ts и правкам не подлежит.
  { ignores: ["dist/**", "src/client/**", "node_modules/**"] },
  js.configs.recommended,
  pluginVue.configs["flat/recommended"],
  vueTsConfigs.recommended,
  {
    rules: {
      "vue/multi-word-component-names": "off",
    },
  }
)
