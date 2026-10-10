# Implementation plan: connector registry, frontend

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A screen where the user creates a PostgreSQL connection through a form built from the adapter's schema, checks the connection and sees the result.

**Architecture:** The `frontend/` directory is recreated on Vue 3 instead of React. The typed client is still generated from OpenAPI through `@hey-api/openapi-ts` — it does not depend on the framework. Server state lives in `@tanstack/vue-query`; Pinia holds only client state. The connection form is built at runtime from the JSON Schema returned by `GET /api/v1/adapter-types/`.

**Tech Stack:** Vue 3, TypeScript, Vite, Quasar (through `@quasar/vite-plugin`), Vue Router, Pinia, `@tanstack/vue-query`, zod, `@hey-api/openapi-ts` with an axios client, Vitest + `@vue/test-utils`, Playwright, ESLint + Prettier, bun as the runner.

Spec: [2026-08-15-connector-registry-design.md](../2026-08-15-connector-registry-design.md)
Backend: [2026-08-15-connector-registry-backend.md](2026-08-15-connector-registry-backend.md) — must be fully completed before this plan starts.

## Global Constraints

- Packages are installed and run through `bun`; the root `package.json` declares the `frontend` workspace.
- `bun run --filter frontend type-check` (`vue-tsc --noEmit`) passes without errors after every task.
- `bun run --filter frontend lint` passes without errors after every task.
- Composition API and `<script setup lang="ts">` in all new SFCs.
- Server state lives only in `@tanstack/vue-query`. Pinia holds nothing that can be re-requested from the server.
- Secret fields are never filled into the edit form: they arrive empty and are sent only if filled in.
- Vite listens on port 5173 — `frontend/playwright.config.ts` is configured for it.
- The backend for manual checks is started with `docker compose up -d db backend`.

## Replacing React with Vue: what is removed and what is kept

**Kept:** `frontend/openapi-ts.config.ts`, `frontend/playwright.config.ts`, `frontend/tests/config.ts`, `frontend/.env`, `frontend/public/`, `frontend/index.html` (edited in place), `scripts/generate-client.sh`, the root `package.json`.

**Removed:** all of `frontend/src/` except the generated `frontend/src/client/`, all specs in `frontend/tests/` except `config.ts`, `frontend/biome.json`, `frontend/components.json`, `frontend/.tanstack/`.

---

### Task 1: Vue application skeleton

**Files:**
- Modify: `frontend/package.json`
- Modify: `frontend/vite.config.ts`
- Modify: `frontend/tsconfig.json`, `frontend/tsconfig.build.json`, `frontend/tsconfig.node.json`
- Modify: `frontend/index.html`
- Create: `frontend/eslint.config.js`
- Create: `frontend/.prettierrc.json`
- Create: `frontend/env.d.ts`
- Create: `frontend/vitest.config.ts`
- Create: `frontend/src/main.ts`
- Create: `frontend/src/App.vue`
- Create: `frontend/src/quasar-variables.sass`
- Create: `frontend/src/router/index.ts`
- Create: `frontend/src/stores/auth.ts`
- Delete: `frontend/src/components/`, `frontend/src/hooks/`, `frontend/src/lib/`, `frontend/src/routes/`, `frontend/src/main.tsx`, `frontend/src/utils.ts`, `frontend/src/index.css`, `frontend/src/routeTree.gen.ts`, `frontend/biome.json`, `frontend/components.json`, `frontend/.tanstack/`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `@/stores/auth` — `useAuthStore()` with fields `token: Ref<string | null>`, `isLoggedIn: ComputedRef<boolean>` and methods `setToken(value: string): void`, `clear(): void`
  - `@/router` — exports `router`
  - the `@` alias points to `frontend/src`

- [ ] **Step 1: Remove the React sources**

```bash
cd frontend
git rm -r --quiet src/components src/hooks src/lib src/routes
git rm --quiet src/main.tsx src/utils.ts src/index.css src/routeTree.gen.ts biome.json components.json
rm -rf .tanstack
```

The `src/client/` directory is left alone: it is generated and reused.

- [ ] **Step 2: Rewrite package.json**

Replace the whole content of `frontend/package.json`:

```json
{
  "name": "frontend",
  "private": true,
  "version": "0.0.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "vue-tsc -b && vite build",
    "type-check": "vue-tsc --noEmit",
    "lint": "eslint . --fix",
    "format": "prettier --write src/",
    "preview": "vite preview",
    "generate-client": "openapi-ts",
    "test:unit": "vitest run",
    "test": "bunx playwright test",
    "test:ui": "bunx playwright test --ui"
  },
  "dependencies": {
    "@quasar/extras": "^1.17.0",
    "@tanstack/vue-query": "^5.101.4",
    "axios": "1.18.0",
    "pinia": "^3.0.3",
    "quasar": "^2.18.5",
    "vue": "^3.5.22",
    "vue-router": "^4.5.1",
    "zod": "^4.4.3"
  },
  "devDependencies": {
    "@hey-api/openapi-ts": "0.97.3",
    "@playwright/test": "1.62.1",
    "@quasar/vite-plugin": "^1.10.0",
    "@types/node": "^26.1.2",
    "@vitejs/plugin-vue": "^6.0.1",
    "@vue/eslint-config-typescript": "^14.6.0",
    "@vue/test-utils": "^2.4.6",
    "dotenv": "^17.4.2",
    "eslint": "^9.39.0",
    "eslint-plugin-vue": "^10.5.0",
    "jsdom": "^26.1.0",
    "prettier": "^3.6.2",
    "sass-embedded": "^1.94.1",
    "typescript": "^6.0.3",
    "vite": "^8.2.0",
    "vitest": "^3.2.4",
    "vue-tsc": "^3.1.1"
  }
}
```

A form library is deliberately absent. The validation schema is built at runtime from JSON Schema, so the typing that is usually the reason to take `vee-validate` with `toTypedSchema` is unreachable here anyway; validation through `schema.safeParse()` in a small composable takes less code than configuring the dependency.

- [ ] **Step 3: Install dependencies**

Run: `cd frontend && rm -rf node_modules && cd .. && bun install`
Expected: installation succeeds, no React packages in `bun.lock`.

- [ ] **Step 4: Rewrite vite.config.ts**

Replace the whole content of `frontend/vite.config.ts`:

```ts
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
  plugins: [
    vue({ template: { transformAssetUrls } }),
    quasar({ sassVariables: "src/quasar-variables.sass" }),
  ],
  server: {
    port: 5173,
  },
})
```

- [ ] **Step 5: Configure TypeScript**

Replace the content of `frontend/tsconfig.json`:

```json
{
  "files": [],
  "references": [
    { "path": "./tsconfig.build.json" },
    { "path": "./tsconfig.node.json" }
  ]
}
```

Replace the content of `frontend/tsconfig.build.json`:

```json
{
  "extends": "@vue/tsconfig/tsconfig.dom.json",
  "include": ["env.d.ts", "src/**/*", "src/**/*.vue"],
  "exclude": ["src/**/__tests__/*"],
  "compilerOptions": {
    "composite": true,
    "noEmit": true,
    "tsBuildInfoFile": "./node_modules/.tmp/tsconfig.build.tsbuildinfo",
    "baseUrl": ".",
    "paths": { "@/*": ["./src/*"] },
    "strict": true,
    "types": ["vite/client"]
  }
}
```

Add `@vue/tsconfig` to `devDependencies` of `frontend/package.json`:

```json
    "@vue/tsconfig": "^0.8.1",
```

and reinstall: `cd .. && bun install`.

Replace the content of `frontend/tsconfig.node.json`:

```json
{
  "extends": "@tsconfig/node22/tsconfig.json",
  "include": ["vite.config.ts", "vitest.config.ts", "playwright.config.ts", "openapi-ts.config.ts"],
  "compilerOptions": {
    "composite": true,
    "noEmit": true,
    "tsBuildInfoFile": "./node_modules/.tmp/tsconfig.node.tsbuildinfo",
    "module": "ESNext",
    "moduleResolution": "Bundler",
    "types": ["node"]
  }
}
```

Add `@tsconfig/node22` to `devDependencies`:

```json
    "@tsconfig/node22": "^22.0.2",
```

Create `frontend/env.d.ts`:

```ts
/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_URL: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
```

- [ ] **Step 6: Configure the linter and formatting**

Create `frontend/eslint.config.js`:

```js
import js from "@eslint/js"
import vueTsConfigs from "@vue/eslint-config-typescript"
import pluginVue from "eslint-plugin-vue"

export default [
  { ignores: ["dist/**", "src/client/**", "node_modules/**"] },
  js.configs.recommended,
  ...pluginVue.configs["flat/recommended"],
  ...vueTsConfigs.configs.recommended,
  {
    rules: {
      "vue/multi-word-component-names": "off",
    },
  },
]
```

The `src/client/` directory is excluded: it is generated and not to be edited.

Add `@eslint/js` to `devDependencies`:

```json
    "@eslint/js": "^9.39.0",
```

Create `frontend/.prettierrc.json`:

```json
{
  "semi": false,
  "singleQuote": false,
  "printWidth": 100,
  "trailingComma": "es5"
}
```

- [ ] **Step 7: Configure Vitest**

Create `frontend/vitest.config.ts`:

```ts
import { fileURLToPath, URL } from "node:url"
import vue from "@vitejs/plugin-vue"
import { defineConfig } from "vitest/config"

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url)),
    },
  },
  test: {
    environment: "jsdom",
    include: ["src/**/*.spec.ts"],
  },
})
```

Unit tests sit next to the code and end in `.spec.ts`; Playwright takes its files only from `frontend/tests/`, so the suites do not overlap.

- [ ] **Step 8: Create the entry point**

Replace the content of `frontend/index.html`:

```html
<!doctype html>
<html lang="ru">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>DataPlayer</title>
  </head>
  <body>
    <div id="app"></div>
    <script type="module" src="/src/main.ts"></script>
  </body>
</html>
```

Create `frontend/src/quasar-variables.sass`:

```sass
$primary   : #1976d2
$secondary : #26a69a
$accent    : #9c27b0

$dark      : #1d1d1d

$positive  : #21ba45
$negative  : #c10015
$info      : #31ccec
$warning   : #f2c037
```

Create `frontend/src/App.vue`:

```vue
<template>
  <router-view />
</template>
```

Create `frontend/src/main.ts`:

```ts
import { VueQueryPlugin } from "@tanstack/vue-query"
import { createPinia } from "pinia"
import { Dialog, Notify, Quasar } from "quasar"
import { createApp } from "vue"

import "@quasar/extras/material-icons/material-icons.css"
import "quasar/src/css/index.sass"

import App from "@/App.vue"
import { router } from "@/router"

createApp(App)
  .use(createPinia())
  .use(Quasar, { plugins: { Notify, Dialog } })
  .use(router)
  .use(VueQueryPlugin)
  .mount("#app")
```

Order matters: Pinia is installed before the router, because the navigation guard accesses the store.

- [ ] **Step 9: Create the authentication store**

Create `frontend/src/stores/auth.ts`:

```ts
import { defineStore } from "pinia"
import { computed, ref } from "vue"

const TOKEN_KEY = "access_token"

export const useAuthStore = defineStore("auth", () => {
  const token = ref<string | null>(localStorage.getItem(TOKEN_KEY))
  const isLoggedIn = computed(() => token.value !== null)

  function setToken(value: string) {
    token.value = value
    localStorage.setItem(TOKEN_KEY, value)
  }

  function clear() {
    token.value = null
    localStorage.removeItem(TOKEN_KEY)
  }

  return { token, isLoggedIn, setToken, clear }
})
```

- [ ] **Step 10: Create the router with placeholders**

Create `frontend/src/router/index.ts`:

```ts
import { createRouter, createWebHistory } from "vue-router"

import { useAuthStore } from "@/stores/auth"

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: "/login",
      name: "login",
      component: () => import("@/features/auth/LoginPage.vue"),
    },
    {
      path: "/",
      name: "connectors",
      component: () => import("@/features/connectors/ConnectorsPage.vue"),
      meta: { requiresAuth: true },
    },
  ],
})

router.beforeEach((to) => {
  const auth = useAuthStore()
  if (to.meta.requiresAuth && !auth.isLoggedIn) {
    return { name: "login" }
  }
  if (to.name === "login" && auth.isLoggedIn) {
    return { name: "connectors" }
  }
  return true
})
```

Create temporary placeholders so the application builds before the real screens exist.

`frontend/src/features/auth/LoginPage.vue`:

```vue
<template>
  <div>login</div>
</template>
```

`frontend/src/features/connectors/ConnectorsPage.vue`:

```vue
<template>
  <div>connectors</div>
</template>
```

- [ ] **Step 11: Check that the application builds and starts**

Run: `cd frontend && bun run type-check`
Expected: no errors.

Run: `cd frontend && bun run lint`
Expected: no errors.

Run: `cd frontend && bun run dev`
Expected: Vite starts on `http://localhost:5173`. Open the address in a browser — the text `login` is visible (the guard redirects an unauthenticated user). Stop the server.

- [ ] **Step 12: Commit**

```bash
git add -A frontend bun.lock
git commit -m "feat: replace the React frontend skeleton with Vue 3 and Quasar"
```

---

### Task 2: API client and request configuration

**Files:**
- Create: `frontend/src/shared/api/configure.ts`
- Modify: `frontend/src/main.ts`
- Modify: `scripts/generate-client.sh`

**Interfaces:**
- Consumes: `useAuthStore` from task 1.
- Produces:
  - `@/shared/api/configure` — `configureApiClient(): void` and `createQueryClient(): QueryClient`
  - a regenerated `frontend/src/client/` with types `ConnectorPublic`, `ConnectorsPublic`, `ConnectorCreate`, `ConnectorUpdate`, `ConnectionCheckResult`, `AdapterTypeInfo` and services `ConnectorsService`, `AdapterTypesService`, `LoginService`, `UsersService`

- [ ] **Step 1: Regenerate the client from the backend's OpenAPI**

Make sure the backend from the first plan is done and the database is up.

Run: `docker compose up -d db`
Expected: container `db` running.

In `scripts/generate-client.sh` the last line calls `bun run lint`, which now runs ESLint and would fail on the generated code. Replace it with formatting:

```bash
bun run --filter frontend format
```

Run: `bash scripts/generate-client.sh`
Expected: the script succeeds; `frontend/src/client/types.gen.ts` contains the types `ConnectorPublic`, `ConnectorCreate`, `ConnectionCheckResult`, `AdapterTypeInfo`.

- [ ] **Step 2: Check the service names in the generated code**

Run: `cd frontend && grep -n "export class .*Service" src/client/sdk.gen.ts`
Expected: the output contains `ConnectorsService` and `AdapterTypesService`. If the names differ, use the actual names in all following tasks.

- [ ] **Step 3: Implement the client configuration**

Create `frontend/src/shared/api/configure.ts`:

```ts
import { MutationCache, QueryCache, QueryClient } from "@tanstack/vue-query"
import { AxiosError } from "axios"

import { client } from "@/client/client.gen"
import { router } from "@/router"
import { useAuthStore } from "@/stores/auth"

export function configureApiClient() {
  client.setConfig({
    baseURL: import.meta.env.VITE_API_URL ?? "",
    // The client adds the Bearer scheme itself from the OpenAPI security description.
    auth: () => useAuthStore().token ?? "",
  })
}

function handleApiError(error: Error) {
  if (error instanceof AxiosError && [401, 403].includes(error.response?.status ?? 0)) {
    useAuthStore().clear()
    void router.push({ name: "login" })
  }
}

export function createQueryClient() {
  return new QueryClient({
    queryCache: new QueryCache({ onError: handleApiError }),
    mutationCache: new MutationCache({ onError: handleApiError }),
  })
}
```

- [ ] **Step 4: Wire the configuration into the entry point**

Replace the content of `frontend/src/main.ts`:

```ts
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

app.use(createPinia())
// Client configuration accesses the store, so it comes after Pinia is installed.
configureApiClient()

app
  .use(Quasar, { plugins: { Notify, Dialog } })
  .use(router)
  .use(VueQueryPlugin, { queryClient: createQueryClient() })
  .mount("#app")
```

- [ ] **Step 5: Check types and style**

Run: `cd frontend && bun run type-check && bun run lint`
Expected: no errors.

- [ ] **Step 6: Commit**

```bash
git add frontend/src scripts/generate-client.sh
git commit -m "feat: API client generation and request configuration on Vue"
```

---

### Task 3: Login and application shell

**Files:**
- Create: `frontend/src/features/auth/api.ts`
- Modify: `frontend/src/features/auth/LoginPage.vue`
- Create: `frontend/src/shared/ui/AppLayout.vue`
- Modify: `frontend/src/App.vue`

**Interfaces:**
- Consumes: `useAuthStore`, `router`, the generated `LoginService`.
- Produces:
  - `@/features/auth/api` — `useLogin()` with fields `mutate(credentials: { username: string; password: string })`, `isPending: Ref<boolean>`, `error: Ref<Error | null>`
  - `@/shared/ui/AppLayout.vue` — a shell with a header and a logout button, content goes into the default slot

- [ ] **Step 1: Implement the login call**

Create `frontend/src/features/auth/api.ts`:

```ts
import { useMutation } from "@tanstack/vue-query"

import { LoginService } from "@/client"
import { useAuthStore } from "@/stores/auth"

export interface Credentials {
  username: string
  password: string
}

export function useLogin() {
  const auth = useAuthStore()

  return useMutation({
    mutationFn: async (credentials: Credentials) => {
      const response = await LoginService.loginAccessToken({ body: credentials })
      return response.data
    },
    onSuccess: (data) => {
      auth.setToken(data.access_token)
    },
  })
}
```

- [ ] **Step 2: Implement the login screen**

Replace the content of `frontend/src/features/auth/LoginPage.vue`:

```vue
<script setup lang="ts">
import { ref } from "vue"
import { useRouter } from "vue-router"

import { useLogin } from "@/features/auth/api"

const router = useRouter()
const login = useLogin()

const username = ref("")
const password = ref("")
const failed = ref(false)

async function submit() {
  failed.value = false
  try {
    await login.mutateAsync({ username: username.value, password: password.value })
    await router.push({ name: "connectors" })
  } catch {
    failed.value = true
  }
}
</script>

<template>
  <q-layout view="hHh lpR fFf">
    <q-page-container>
      <q-page class="flex flex-center">
        <q-card style="width: 360px" class="q-pa-md">
          <q-card-section>
            <div class="text-h6">Log in</div>
          </q-card-section>
          <q-form @submit.prevent="submit">
            <q-card-section class="q-gutter-md">
              <q-input
                v-model="username"
                label="Email"
                type="email"
                autocomplete="username"
                data-testid="login-email"
                :rules="[(value: string) => !!value || 'Enter your email']"
              />
              <q-input
                v-model="password"
                label="Password"
                type="password"
                autocomplete="current-password"
                data-testid="login-password"
                :rules="[(value: string) => !!value || 'Enter your password']"
              />
              <q-banner v-if="failed" dense class="bg-negative text-white" data-testid="login-error">
                Could not log in. Check your email and password.
              </q-banner>
            </q-card-section>
            <q-card-actions>
              <q-btn
                type="submit"
                color="primary"
                class="full-width"
                label="Log in"
                data-testid="login-submit"
                :loading="login.isPending.value"
              />
            </q-card-actions>
          </q-form>
        </q-card>
      </q-page>
    </q-page-container>
  </q-layout>
</template>
```

The `data-testid` attributes are needed by the Playwright scenarios of task 8: Russian-language labels may change, identifiers do not.

- [ ] **Step 3: Implement the shell**

Create `frontend/src/shared/ui/AppLayout.vue`:

```vue
<script setup lang="ts">
import { useQueryClient } from "@tanstack/vue-query"
import { useRouter } from "vue-router"

import { useAuthStore } from "@/stores/auth"

const auth = useAuthStore()
const router = useRouter()
const queryClient = useQueryClient()

async function logout() {
  auth.clear()
  queryClient.clear()
  await router.push({ name: "login" })
}
</script>

<template>
  <q-layout view="hHh lpR fFf">
    <q-header elevated>
      <q-toolbar>
        <q-toolbar-title>DataPlayer</q-toolbar-title>
        <q-btn flat dense label="Log out" data-testid="logout" @click="logout" />
      </q-toolbar>
    </q-header>
    <q-page-container>
      <q-page padding>
        <slot />
      </q-page>
    </q-page-container>
  </q-layout>
</template>
```

The `vue-query` cache is cleared on logout: otherwise the previous user's data stays visible to the next one.

- [ ] **Step 4: Check login manually**

Run: `docker compose up -d db backend`
Expected: both containers running.

Run: `cd frontend && bun run dev`
Expected: Vite on 5173.

Open `http://localhost:5173`, log in with the `FIRST_SUPERUSER` and `FIRST_SUPERUSER_PASSWORD` credentials from the root `.env`.
Expected: navigation to `/`, the text `connectors` is visible. A wrong password shows an error banner. Stop the server.

- [ ] **Step 5: Check types and style**

Run: `cd frontend && bun run type-check && bun run lint`
Expected: no errors.

- [ ] **Step 6: Commit**

```bash
git add frontend/src
git commit -m "feat: login and application shell"
```

---

### Task 4: Converting JSON Schema into a validation schema and field descriptions

Pure functions with no tie to Vue — the only part of the frontend fully covered by unit tests.

**Files:**
- Create: `frontend/src/features/connectors/SchemaForm/jsonSchema.ts`
- Create: `frontend/src/features/connectors/SchemaForm/jsonSchema.spec.ts`

**Interfaces:**
- Consumes: `zod`.
- Produces:
  - `@/features/connectors/SchemaForm/jsonSchema` — type `JsonSchema`, type `FieldSpec` with fields `name: string`, `label: string`, `kind: "text" | "password" | "number" | "boolean" | "select"`, `required: boolean`, `defaultValue?: unknown`, `choices?: string[]`
  - `schemaToFields(schema: JsonSchema): FieldSpec[]`
  - `jsonSchemaToZod(schema: JsonSchema): z.ZodObject`
  - `defaultValues(fields: FieldSpec[]): Record<string, unknown>`

- [ ] **Step 1: Write failing tests**

Create `frontend/src/features/connectors/SchemaForm/jsonSchema.spec.ts`:

```ts
import { describe, expect, it } from "vitest"

import { defaultValues, jsonSchemaToZod, schemaToFields } from "./jsonSchema"
import type { JsonSchema } from "./jsonSchema"

// The shape in which Pydantic returns the PostgresOptions schema.
const POSTGRES_SCHEMA: JsonSchema = {
  type: "object",
  title: "PostgresOptions",
  required: ["host", "database", "user", "password"],
  properties: {
    host: { type: "string", title: "Host", minLength: 1 },
    port: { type: "integer", title: "Port", default: 5432, minimum: 1, maximum: 65535 },
    database: { type: "string", title: "Database", minLength: 1 },
    user: { type: "string", title: "User", minLength: 1 },
    password: { type: "string", title: "Password", format: "password", writeOnly: true },
  },
}

describe("schemaToFields", () => {
  it("keeps the order of properties", () => {
    const names = schemaToFields(POSTGRES_SCHEMA).map((field) => field.name)

    expect(names).toEqual(["host", "port", "database", "user", "password"])
  })

  it("uses the title as the label", () => {
    const [host] = schemaToFields(POSTGRES_SCHEMA)

    expect(host.label).toBe("Host")
  })

  it("falls back to the property name when there is no title", () => {
    const fields = schemaToFields({
      type: "object",
      properties: { plain_name: { type: "string" } },
    })

    expect(fields[0].label).toBe("plain_name")
  })

  it("marks password-formatted strings as secret", () => {
    const password = schemaToFields(POSTGRES_SCHEMA).find((f) => f.name === "password")

    expect(password?.kind).toBe("password")
  })

  it("maps integers to the number kind", () => {
    const port = schemaToFields(POSTGRES_SCHEMA).find((f) => f.name === "port")

    expect(port?.kind).toBe("number")
    expect(port?.defaultValue).toBe(5432)
  })

  it("maps booleans and enums", () => {
    const fields = schemaToFields({
      type: "object",
      properties: {
        ssl: { type: "boolean", title: "SSL", default: false },
        mode: { type: "string", title: "Mode", enum: ["require", "disable"] },
      },
    })

    expect(fields[0].kind).toBe("boolean")
    expect(fields[1].kind).toBe("select")
    expect(fields[1].choices).toEqual(["require", "disable"])
  })

  it("marks required fields", () => {
    const fields = schemaToFields(POSTGRES_SCHEMA)

    expect(fields.find((f) => f.name === "host")?.required).toBe(true)
    expect(fields.find((f) => f.name === "port")?.required).toBe(false)
  })

  it("throws on an unsupported property type", () => {
    expect(() =>
      schemaToFields({
        type: "object",
        properties: { weird: { type: "array" } },
      })
    ).toThrow(/unsupported/i)
  })
})

describe("jsonSchemaToZod", () => {
  it("accepts valid values", () => {
    const schema = jsonSchemaToZod(POSTGRES_SCHEMA)

    const result = schema.safeParse({
      host: "localhost",
      port: 5432,
      database: "app",
      user: "postgres",
      password: "secret",
    })

    expect(result.success).toBe(true)
  })

  it("rejects a missing required field", () => {
    const schema = jsonSchemaToZod(POSTGRES_SCHEMA)

    const result = schema.safeParse({ host: "localhost" })

    expect(result.success).toBe(false)
  })

  it("rejects an empty required string", () => {
    const schema = jsonSchemaToZod(POSTGRES_SCHEMA)

    const result = schema.safeParse({
      host: "",
      database: "app",
      user: "postgres",
      password: "secret",
    })

    expect(result.success).toBe(false)
  })

  it("rejects a port outside the allowed range", () => {
    const schema = jsonSchemaToZod(POSTGRES_SCHEMA)

    const result = schema.safeParse({
      host: "localhost",
      port: 70000,
      database: "app",
      user: "postgres",
      password: "secret",
    })

    expect(result.success).toBe(false)
  })

  it("allows omitting an optional field", () => {
    const schema = jsonSchemaToZod(POSTGRES_SCHEMA)

    const result = schema.safeParse({
      host: "localhost",
      database: "app",
      user: "postgres",
      password: "secret",
    })

    expect(result.success).toBe(true)
  })
})

describe("defaultValues", () => {
  it("uses schema defaults and blanks for the rest", () => {
    expect(defaultValues(schemaToFields(POSTGRES_SCHEMA))).toEqual({
      host: "",
      port: 5432,
      database: "",
      user: "",
      password: "",
    })
  })

  it("defaults booleans to false", () => {
    const fields = schemaToFields({
      type: "object",
      properties: { ssl: { type: "boolean" } },
    })

    expect(defaultValues(fields)).toEqual({ ssl: false })
  })
})
```

- [ ] **Step 2: Run the tests and make sure they fail**

Run: `cd frontend && bun run test:unit`
Expected: FAIL — module `./jsonSchema` not found.

- [ ] **Step 3: Implement the conversion**

Create `frontend/src/features/connectors/SchemaForm/jsonSchema.ts`:

```ts
import { z } from "zod"

export interface JsonSchemaProperty {
  type?: string
  title?: string
  format?: string
  writeOnly?: boolean
  default?: unknown
  enum?: string[]
  minLength?: number
  minimum?: number
  maximum?: number
}

export interface JsonSchema {
  type?: string
  title?: string
  required?: string[]
  properties: Record<string, JsonSchemaProperty>
}

export type FieldKind = "text" | "password" | "number" | "boolean" | "select"

export interface FieldSpec {
  name: string
  label: string
  kind: FieldKind
  required: boolean
  defaultValue?: unknown
  choices?: string[]
  minLength?: number
  minimum?: number
  maximum?: number
}

function kindOf(property: JsonSchemaProperty, name: string): FieldKind {
  if (property.enum) return "select"
  switch (property.type) {
    case "string":
      return property.format === "password" ? "password" : "text"
    case "integer":
    case "number":
      return "number"
    case "boolean":
      return "boolean"
    default:
      throw new Error(
        `Unsupported property type "${property.type}" for field "${name}"`
      )
  }
}

export function schemaToFields(schema: JsonSchema): FieldSpec[] {
  const required = new Set(schema.required ?? [])

  return Object.entries(schema.properties).map(([name, property]) => ({
    name,
    label: property.title ?? name,
    kind: kindOf(property, name),
    required: required.has(name),
    defaultValue: property.default,
    choices: property.enum,
    minLength: property.minLength,
    minimum: property.minimum,
    maximum: property.maximum,
  }))
}

function zodForField(field: FieldSpec): z.ZodType {
  switch (field.kind) {
    case "select":
      return z.enum(field.choices as [string, ...string[]])
    case "boolean":
      return z.boolean()
    case "number": {
      let schema = z.number()
      if (field.minimum !== undefined) schema = schema.min(field.minimum)
      if (field.maximum !== undefined) schema = schema.max(field.maximum)
      return schema
    }
    default: {
      let schema = z.string()
      // A required string field must not pass validation when empty.
      const minLength = field.minLength ?? (field.required ? 1 : 0)
      if (minLength > 0) schema = schema.min(minLength)
      return schema
    }
  }
}

export function jsonSchemaToZod(schema: JsonSchema) {
  const shape: Record<string, z.ZodType> = {}

  for (const field of schemaToFields(schema)) {
    const fieldSchema = zodForField(field)
    shape[field.name] = field.required ? fieldSchema : fieldSchema.optional()
  }

  return z.object(shape)
}

export function defaultValues(fields: FieldSpec[]): Record<string, unknown> {
  const values: Record<string, unknown> = {}

  for (const field of fields) {
    if (field.defaultValue !== undefined) {
      values[field.name] = field.defaultValue
    } else if (field.kind === "boolean") {
      values[field.name] = false
    } else if (field.kind === "number") {
      values[field.name] = null
    } else {
      values[field.name] = ""
    }
  }

  return values
}
```

- [ ] **Step 4: Run the tests and make sure they pass**

Run: `cd frontend && bun run test:unit`
Expected: PASS, 15 tests.

If the test `defaults booleans to false` or `uses schema defaults and blanks for the rest` fails on a `null` type for a numeric field without a default — the suite has no such fields, `port` has a `default`. A mismatch means a bug in `defaultValues`.

- [ ] **Step 5: Check types and style**

Run: `cd frontend && bun run type-check && bun run lint`
Expected: no errors.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/features/connectors/SchemaForm
git commit -m "feat: convert JSON Schema into a validation schema and field descriptions"
```

---

### Task 5: Form fields component

**Files:**
- Create: `frontend/src/features/connectors/SchemaForm/SchemaFields.vue`
- Create: `frontend/src/features/connectors/SchemaForm/SchemaFields.spec.ts`
- Create: `frontend/src/features/connectors/SchemaForm/useSchemaForm.ts`
- Create: `frontend/src/features/connectors/SchemaForm/useSchemaForm.spec.ts`

**Interfaces:**
- Consumes: `FieldSpec`, `jsonSchemaToZod`, `defaultValues` from task 4.
- Produces:
  - `@/features/connectors/SchemaForm/SchemaFields.vue` — props `fields: FieldSpec[]`, `modelValue: Record<string, unknown>`, `errors: Record<string, string>`, `secretPlaceholder?: string`; event `update:modelValue`
  - `@/features/connectors/SchemaForm/useSchemaForm` — `useSchemaForm()` returns `values: Ref<Record<string, unknown>>`, `errors: Ref<Record<string, string>>`, `validate(schema): boolean`, `applyServerErrors(detail): void`, `reset(fields): void`

- [ ] **Step 1: Write failing tests for the composable**

Create `frontend/src/features/connectors/SchemaForm/useSchemaForm.spec.ts`:

```ts
import { describe, expect, it } from "vitest"

import { jsonSchemaToZod, schemaToFields } from "./jsonSchema"
import type { JsonSchema } from "./jsonSchema"
import { useSchemaForm } from "./useSchemaForm"

const SCHEMA: JsonSchema = {
  type: "object",
  required: ["host"],
  properties: {
    host: { type: "string", title: "Host", minLength: 1 },
    port: { type: "integer", title: "Port", default: 5432 },
  },
}

describe("useSchemaForm", () => {
  it("fills values with schema defaults on reset", () => {
    const form = useSchemaForm()

    form.reset(schemaToFields(SCHEMA))

    expect(form.values.value).toEqual({ host: "", port: 5432 })
  })

  it("reports a validation error for an empty required field", () => {
    const form = useSchemaForm()
    form.reset(schemaToFields(SCHEMA))

    const valid = form.validate(jsonSchemaToZod(SCHEMA))

    expect(valid).toBe(false)
    expect(form.errors.value.host).toBeTruthy()
  })

  it("clears errors once the values become valid", () => {
    const form = useSchemaForm()
    form.reset(schemaToFields(SCHEMA))
    form.validate(jsonSchemaToZod(SCHEMA))

    form.values.value.host = "localhost"
    const valid = form.validate(jsonSchemaToZod(SCHEMA))

    expect(valid).toBe(true)
    expect(form.errors.value).toEqual({})
  })

  it("maps a server 422 detail onto field errors", () => {
    const form = useSchemaForm()
    form.reset(schemaToFields(SCHEMA))

    form.applyServerErrors([
      { loc: ["body", "options", "host"], msg: "Host is unreachable", type: "value_error" },
    ])

    expect(form.errors.value.host).toBe("Host is unreachable")
  })

  it("ignores server errors that do not point at a field", () => {
    const form = useSchemaForm()
    form.reset(schemaToFields(SCHEMA))

    form.applyServerErrors([{ loc: ["body"], msg: "Invalid body", type: "value_error" }])

    expect(form.errors.value).toEqual({})
  })
})
```

- [ ] **Step 2: Run the tests and make sure they fail**

Run: `cd frontend && bun run test:unit`
Expected: FAIL — module `./useSchemaForm` not found.

- [ ] **Step 3: Implement the composable**

Create `frontend/src/features/connectors/SchemaForm/useSchemaForm.ts`:

```ts
import { ref } from "vue"
import type { ZodType } from "zod"

import { defaultValues } from "./jsonSchema"
import type { FieldSpec } from "./jsonSchema"

export interface ServerError {
  loc: (string | number)[]
  msg: string
  type: string
}

export function useSchemaForm() {
  const values = ref<Record<string, unknown>>({})
  const errors = ref<Record<string, string>>({})

  function reset(fields: FieldSpec[], initial: Record<string, unknown> = {}) {
    values.value = { ...defaultValues(fields), ...initial }
    errors.value = {}
  }

  function validate(schema: ZodType): boolean {
    const result = schema.safeParse(values.value)
    if (result.success) {
      errors.value = {}
      return true
    }

    const collected: Record<string, string> = {}
    for (const issue of result.error.issues) {
      const name = String(issue.path[0] ?? "")
      if (name && !collected[name]) {
        collected[name] = issue.message
      }
    }
    errors.value = collected
    return false
  }

  function applyServerErrors(detail: ServerError[]) {
    const collected: Record<string, string> = {}
    for (const error of detail) {
      // The path looks like ["body", "options", "<field>"]; anything shorter does not concern a field.
      const name = error.loc.at(-1)
      if (typeof name === "string" && error.loc.length > 2) {
        collected[name] = error.msg
      }
    }
    errors.value = collected
  }

  return { values, errors, reset, validate, applyServerErrors }
}
```

- [ ] **Step 4: Run the tests and make sure they pass**

Run: `cd frontend && bun run test:unit`
Expected: PASS, 20 tests.

- [ ] **Step 5: Write failing tests for the component**

Create `frontend/src/features/connectors/SchemaForm/SchemaFields.spec.ts`:

```ts
import { mount } from "@vue/test-utils"
import { Quasar } from "quasar"
import { describe, expect, it } from "vitest"

import SchemaFields from "./SchemaFields.vue"
import { schemaToFields } from "./jsonSchema"
import type { JsonSchema } from "./jsonSchema"

const SCHEMA: JsonSchema = {
  type: "object",
  required: ["host", "password"],
  properties: {
    host: { type: "string", title: "Host" },
    port: { type: "integer", title: "Port", default: 5432 },
    password: { type: "string", title: "Password", format: "password" },
    ssl: { type: "boolean", title: "SSL" },
  },
}

function mountFields(errors: Record<string, string> = {}) {
  return mount(SchemaFields, {
    global: { plugins: [Quasar] },
    props: {
      fields: schemaToFields(SCHEMA),
      modelValue: { host: "localhost", port: 5432, password: "", ssl: false },
      errors,
    },
  })
}

describe("SchemaFields", () => {
  it("renders one control per field", () => {
    const wrapper = mountFields()

    expect(wrapper.findAll("[data-testid^='field-']")).toHaveLength(4)
  })

  it("renders a secret field as a password input", () => {
    const wrapper = mountFields()

    const input = wrapper.find("[data-testid='field-password'] input")
    expect(input.attributes("type")).toBe("password")
  })

  it("renders a boolean field as a toggle", () => {
    const wrapper = mountFields()

    expect(wrapper.find("[data-testid='field-ssl'] .q-toggle").exists()).toBe(true)
  })

  it("shows the error text for a field", () => {
    const wrapper = mountFields({ host: "Host is required" })

    expect(wrapper.text()).toContain("Host is required")
  })

  it("emits an update when a value changes", async () => {
    const wrapper = mountFields()

    await wrapper.find("[data-testid='field-host'] input").setValue("db.internal")

    const emitted = wrapper.emitted("update:modelValue")
    expect(emitted).toBeTruthy()
    expect((emitted!.at(-1)![0] as Record<string, unknown>).host).toBe("db.internal")
  })
})
```

- [ ] **Step 6: Run the tests and make sure they fail**

Run: `cd frontend && bun run test:unit`
Expected: FAIL — component `SchemaFields.vue` not found.

- [ ] **Step 7: Implement the component**

Create `frontend/src/features/connectors/SchemaForm/SchemaFields.vue`:

```vue
<script setup lang="ts">
import type { FieldSpec } from "./jsonSchema"

const props = defineProps<{
  fields: FieldSpec[]
  modelValue: Record<string, unknown>
  errors: Record<string, string>
  secretPlaceholder?: string
}>()

const emit = defineEmits<{
  "update:modelValue": [value: Record<string, unknown>]
}>()

function update(name: string, value: unknown) {
  emit("update:modelValue", { ...props.modelValue, [name]: value })
}
</script>

<template>
  <div class="q-gutter-md">
    <template v-for="field in fields" :key="field.name">
      <q-toggle
        v-if="field.kind === 'boolean'"
        :data-testid="`field-${field.name}`"
        :model-value="Boolean(modelValue[field.name])"
        :label="field.label"
        @update:model-value="update(field.name, $event)"
      />

      <q-select
        v-else-if="field.kind === 'select'"
        :data-testid="`field-${field.name}`"
        :model-value="modelValue[field.name]"
        :options="field.choices"
        :label="field.label"
        :error="Boolean(errors[field.name])"
        :error-message="errors[field.name]"
        @update:model-value="update(field.name, $event)"
      />

      <q-input
        v-else
        :data-testid="`field-${field.name}`"
        :model-value="modelValue[field.name] as string | number | null"
        :label="field.label"
        :type="field.kind === 'password' ? 'password' : field.kind === 'number' ? 'number' : 'text'"
        :placeholder="field.kind === 'password' ? secretPlaceholder : undefined"
        :error="Boolean(errors[field.name])"
        :error-message="errors[field.name]"
        @update:model-value="
          update(field.name, field.kind === 'number' ? Number($event) : $event)
        "
      />
    </template>
  </div>
</template>
```

- [ ] **Step 8: Run the tests and make sure they pass**

Run: `cd frontend && bun run test:unit`
Expected: PASS, 25 tests.

- [ ] **Step 9: Check types and style**

Run: `cd frontend && bun run type-check && bun run lint`
Expected: no errors.

- [ ] **Step 10: Commit**

```bash
git add frontend/src/features/connectors/SchemaForm
git commit -m "feat: fields component for a form built from the adapter schema"
```

---

### Task 6: Connectors screen with a list

**Files:**
- Create: `frontend/src/features/connectors/api.ts`
- Modify: `frontend/src/features/connectors/ConnectorsPage.vue`
- Create: `frontend/src/features/connectors/ConnectorTable.vue`

**Interfaces:**
- Consumes: the generated `ConnectorsService`, `AdapterTypesService`; `AppLayout` from task 3.
- Produces:
  - `@/features/connectors/api` — `useConnectors()`, `useAdapterTypes()`, `useCreateConnector()`, `useUpdateConnector()`, `useDeleteConnector()`, `useCheckConnector()`, `useCheckDraft()`, constant `connectorsKey`
  - `@/features/connectors/ConnectorTable.vue` — props `rows: ConnectorPublic[]`, `loading: boolean`; events `edit`, `remove`, `check` with a `ConnectorPublic` payload

- [ ] **Step 1: Implement the query layer**

Create `frontend/src/features/connectors/api.ts`:

```ts
import { useMutation, useQuery, useQueryClient } from "@tanstack/vue-query"

import { AdapterTypesService, ConnectorsService } from "@/client"
import type { ConnectorCreate, ConnectorUpdate } from "@/client"

export const connectorsKey = ["connectors"] as const
export const adapterTypesKey = ["adapter-types"] as const

export function useConnectors() {
  return useQuery({
    queryKey: connectorsKey,
    queryFn: async () => (await ConnectorsService.readConnectors()).data,
  })
}

export function useAdapterTypes() {
  return useQuery({
    queryKey: adapterTypesKey,
    queryFn: async () => (await AdapterTypesService.readAdapterTypes()).data,
    // The type registry changes only on deployment — there is nothing to re-request.
    staleTime: Number.POSITIVE_INFINITY,
  })
}

export function useCreateConnector() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (body: ConnectorCreate) =>
      (await ConnectorsService.createConnector({ body })).data,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: connectorsKey }),
  })
}

export function useUpdateConnector() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (payload: { connectorId: string; body: ConnectorUpdate }) =>
      (
        await ConnectorsService.updateConnector({
          path: { connector_id: payload.connectorId },
          body: payload.body,
        })
      ).data,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: connectorsKey }),
  })
}

export function useDeleteConnector() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (connectorId: string) =>
      (
        await ConnectorsService.deleteConnector({
          path: { connector_id: connectorId },
        })
      ).data,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: connectorsKey }),
  })
}

export function useCheckConnector() {
  return useMutation({
    mutationFn: async (connectorId: string) =>
      (
        await ConnectorsService.checkConnector({
          path: { connector_id: connectorId },
        })
      ).data,
  })
}

export function useCheckDraft() {
  return useMutation({
    mutationFn: async (body: {
      adapter_type: string
      options: Record<string, unknown>
      connector_id?: string | null
    }) => (await ConnectorsService.checkDraft({ body })).data,
  })
}
```

The service method names follow the generator's convention: the operation name without the tag prefix. If step 2 of task 2 showed different names, use the actual ones.

- [ ] **Step 2: Implement the table**

Create `frontend/src/features/connectors/ConnectorTable.vue`:

```vue
<script setup lang="ts">
import type { ConnectorPublic } from "@/client"

defineProps<{
  rows: ConnectorPublic[]
  loading: boolean
}>()

defineEmits<{
  edit: [connector: ConnectorPublic]
  remove: [connector: ConnectorPublic]
  check: [connector: ConnectorPublic]
}>()

const columns = [
  { name: "name", label: "Name", field: "name", align: "left" as const, sortable: true },
  { name: "adapter_type", label: "Type", field: "adapter_type", align: "left" as const },
  { name: "host", label: "Host", field: "host", align: "left" as const },
  { name: "actions", label: "", field: "actions", align: "right" as const },
]

function hostOf(connector: ConnectorPublic): string {
  const config = connector.config as Record<string, unknown>
  const host = config.host
  const port = config.port
  if (typeof host !== "string") return "—"
  return port === undefined ? host : `${host}:${String(port)}`
}
</script>

<template>
  <q-table
    :rows="rows"
    :columns="columns"
    :loading="loading"
    row-key="id"
    flat
    bordered
    data-testid="connector-table"
    no-data-label="No connections yet"
  >
    <template #body-cell-host="cellProps">
      <q-td :props="cellProps">{{ hostOf(cellProps.row) }}</q-td>
    </template>

    <template #body-cell-adapter_type="cellProps">
      <q-td :props="cellProps">
        <q-badge color="primary" :label="cellProps.row.adapter_type" />
      </q-td>
    </template>

    <template #body-cell-actions="cellProps">
      <q-td :props="cellProps" class="q-gutter-xs">
        <q-btn
          dense
          flat
          icon="bolt"
          :data-testid="`check-${cellProps.row.name}`"
          @click="$emit('check', cellProps.row)"
        >
          <q-tooltip>Check connection</q-tooltip>
        </q-btn>
        <q-btn
          dense
          flat
          icon="edit"
          :data-testid="`edit-${cellProps.row.name}`"
          @click="$emit('edit', cellProps.row)"
        >
          <q-tooltip>Edit</q-tooltip>
        </q-btn>
        <q-btn
          dense
          flat
          icon="delete"
          color="negative"
          :data-testid="`delete-${cellProps.row.name}`"
          @click="$emit('remove', cellProps.row)"
        >
          <q-tooltip>Delete</q-tooltip>
        </q-btn>
      </q-td>
    </template>
  </q-table>
</template>
```

- [ ] **Step 3: Implement the page**

Replace the content of `frontend/src/features/connectors/ConnectorsPage.vue`:

```vue
<script setup lang="ts">
import { useQuasar } from "quasar"
import { computed, ref } from "vue"

import type { ConnectorPublic } from "@/client"
import ConnectorTable from "@/features/connectors/ConnectorTable.vue"
import { useCheckConnector, useConnectors, useDeleteConnector } from "@/features/connectors/api"
import AppLayout from "@/shared/ui/AppLayout.vue"

const quasar = useQuasar()
const connectors = useConnectors()
const removeConnector = useDeleteConnector()
const checkConnector = useCheckConnector()

const dialogOpen = ref(false)
const editing = ref<ConnectorPublic | null>(null)

const rows = computed(() => connectors.data.value?.data ?? [])

function openCreate() {
  editing.value = null
  dialogOpen.value = true
}

function openEdit(connector: ConnectorPublic) {
  editing.value = connector
  dialogOpen.value = true
}

async function check(connector: ConnectorPublic) {
  const result = await checkConnector.mutateAsync(connector.id)
  quasar.notify({
    type: result.ok ? "positive" : "negative",
    message: result.ok
      ? `${result.message} (${String(result.latency_ms)} ms)`
      : result.message,
  })
}

function confirmRemove(connector: ConnectorPublic) {
  quasar
    .dialog({
      title: "Delete connection",
      message: `Connection "${connector.name}" will be deleted permanently.`,
      cancel: true,
      ok: { label: "Delete", color: "negative" },
    })
    .onOk(() => {
      void removeConnector.mutateAsync(connector.id).then(() => {
        quasar.notify({ type: "positive", message: "Connection deleted" })
      })
    })
}
</script>

<template>
  <AppLayout>
    <div class="row items-center justify-between q-mb-md">
      <div class="text-h5">Connections</div>
      <q-btn
        color="primary"
        icon="add"
        label="New connection"
        data-testid="add-connector"
        @click="openCreate"
      />
    </div>

    <ConnectorTable
      :rows="rows"
      :loading="connectors.isLoading.value"
      @edit="openEdit"
      @remove="confirmRemove"
      @check="check"
    />
  </AppLayout>
</template>
```

The dialog is not wired in here yet: it appears in task 7, and the import and markup are added to this file then. The `dialogOpen` and `editing` variables are declared in advance because the `openCreate` and `openEdit` handlers depend on them.

- [ ] **Step 4: Check that the list is shown**

Run: `docker compose up -d db backend && cd frontend && bun run dev`
Expected: after login the heading "Connections" is visible, a table with the text "No connections yet" and a "New connection" button. Clicking the button opens nothing yet — this is expected. Stop the server.

- [ ] **Step 5: Check types and style**

Run: `cd frontend && bun run type-check && bun run lint`
Expected: no errors.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/features/connectors
git commit -m "feat: connectors screen with a list of connections"
```

---

### Task 7: Create and edit dialog with a connection check

**Files:**
- Create: `frontend/src/features/connectors/ConnectorDialog.vue`
- Create: `frontend/src/features/connectors/ConnectionCheck.vue`

**Interfaces:**
- Consumes: everything from tasks 4, 5, 6.
- Produces:
  - `@/features/connectors/ConnectorDialog.vue` — props `modelValue: boolean`, `connector: ConnectorPublic | null`; event `update:modelValue`
  - `@/features/connectors/ConnectionCheck.vue` — prop `result: ConnectionCheckResult | null`

- [ ] **Step 1: Implement showing the check result**

Create `frontend/src/features/connectors/ConnectionCheck.vue`:

```vue
<script setup lang="ts">
import { computed } from "vue"

import type { ConnectionCheckResult } from "@/client"

const props = defineProps<{
  result: ConnectionCheckResult | null
}>()

const KIND_LABELS: Record<string, string> = {
  auth: "Authentication error",
  network: "Server unreachable",
  timeout: "Timed out",
  config: "Invalid parameters",
  unknown: "Unknown error",
}

const text = computed(() => {
  if (!props.result) return ""
  if (props.result.ok) {
    return `${props.result.message} (${String(props.result.latency_ms)} ms)`
  }
  const kind = props.result.error_kind
  const prefix = kind ? KIND_LABELS[kind] : undefined
  return prefix ? `${prefix}: ${props.result.message}` : props.result.message
})
</script>

<template>
  <q-banner
    v-if="result"
    dense
    class="text-white"
    :class="result.ok ? 'bg-positive' : 'bg-negative'"
    data-testid="check-result"
  >
    <template #avatar>
      <q-icon :name="result.ok ? 'check_circle' : 'error'" />
    </template>
    {{ text }}
  </q-banner>
</template>
```

The result is shown as a line inside the dialog, not as a pop-up notification: it is read next to the fields being edited.

- [ ] **Step 2: Implement the dialog**

Create `frontend/src/features/connectors/ConnectorDialog.vue`:

```vue
<script setup lang="ts">
import { AxiosError } from "axios"
import { useQuasar } from "quasar"
import { computed, ref, watch } from "vue"

import type { ConnectionCheckResult, ConnectorPublic } from "@/client"
import ConnectionCheck from "@/features/connectors/ConnectionCheck.vue"
import SchemaFields from "@/features/connectors/SchemaForm/SchemaFields.vue"
import { jsonSchemaToZod, schemaToFields } from "@/features/connectors/SchemaForm/jsonSchema"
import type { JsonSchema } from "@/features/connectors/SchemaForm/jsonSchema"
import { useSchemaForm } from "@/features/connectors/SchemaForm/useSchemaForm"
import type { ServerError } from "@/features/connectors/SchemaForm/useSchemaForm"
import {
  useAdapterTypes,
  useCheckDraft,
  useCreateConnector,
  useUpdateConnector,
} from "@/features/connectors/api"

const props = defineProps<{
  modelValue: boolean
  connector: ConnectorPublic | null
}>()

const emit = defineEmits<{ "update:modelValue": [value: boolean] }>()

const quasar = useQuasar()
const adapterTypes = useAdapterTypes()
const createConnector = useCreateConnector()
const updateConnector = useUpdateConnector()
const checkDraft = useCheckDraft()

// Destructure the composable into separate refs: in a template Vue unwraps only
// top-level refs, so form.values would otherwise have to be written as
// form.values.value.
const {
  values: optionValues,
  errors: optionErrors,
  reset: resetOptions,
  validate: validateOptions,
  applyServerErrors,
} = useSchemaForm()

const name = ref("")
const nameError = ref("")
const adapterType = ref<string | null>(null)
const checkResult = ref<ConnectionCheckResult | null>(null)

const isEdit = computed(() => props.connector !== null)

const typeOptions = computed(() =>
  (adapterTypes.data.value ?? []).map((type) => ({ label: type.title, value: type.name }))
)

const selectedSchema = computed<JsonSchema | null>(() => {
  const type = (adapterTypes.data.value ?? []).find((item) => item.name === adapterType.value)
  return type ? (type.options_schema as unknown as JsonSchema) : null
})

const fields = computed(() => (selectedSchema.value ? schemaToFields(selectedSchema.value) : []))

// In edit mode secret fields arrive empty: the server does not return them.
const secretPlaceholder = computed(() => (isEdit.value ? "Leave unchanged" : undefined))

watch(
  () => props.modelValue,
  (open) => {
    if (!open) return
    checkResult.value = null
    nameError.value = ""
    if (props.connector) {
      name.value = props.connector.name
      adapterType.value = props.connector.adapter_type
      resetOptions(fields.value, props.connector.config as Record<string, unknown>)
    } else {
      name.value = ""
      adapterType.value = null
      resetOptions([])
    }
  }
)

watch(adapterType, () => {
  checkResult.value = null
  if (props.connector && adapterType.value === props.connector.adapter_type) {
    resetOptions(fields.value, props.connector.config as Record<string, unknown>)
  } else {
    resetOptions(fields.value)
  }
})

function filledOptions(): Record<string, unknown> {
  // Empty secret fields are not sent: the server keeps the previous values.
  const result: Record<string, unknown> = {}
  for (const field of fields.value) {
    const value = optionValues.value[field.name]
    if (field.kind === "password" && (value === "" || value === null)) continue
    result[field.name] = value
  }
  return result
}

function serverErrorsFrom(error: unknown): ServerError[] | null {
  if (!(error instanceof AxiosError) || error.response?.status !== 422) return null
  const detail = error.response.data?.detail
  return Array.isArray(detail) ? (detail as ServerError[]) : null
}

function validateName(): boolean {
  nameError.value = name.value.trim() === "" ? "Enter a name" : ""
  return nameError.value === ""
}

async function check() {
  if (!adapterType.value) return
  checkResult.value = null
  try {
    checkResult.value = await checkDraft.mutateAsync({
      adapter_type: adapterType.value,
      options: filledOptions(),
      connector_id: props.connector?.id ?? null,
    })
  } catch (error) {
    const serverErrors = serverErrorsFrom(error)
    if (serverErrors) {
      applyServerErrors(serverErrors)
    } else {
      quasar.notify({ type: "negative", message: "Could not run the check" })
    }
  }
}

async function submit() {
  if (!adapterType.value || !selectedSchema.value) return
  const nameValid = validateName()
  // In edit mode an empty password is allowed, so the schema is checked
  // only against the values actually filled in.
  const schema = jsonSchemaToZod(selectedSchema.value)
  const valuesValid = isEdit.value ? true : validateOptions(schema)
  if (!nameValid || !valuesValid) return

  try {
    if (props.connector) {
      await updateConnector.mutateAsync({
        connectorId: props.connector.id,
        body: { name: name.value, options: filledOptions() },
      })
    } else {
      await createConnector.mutateAsync({
        name: name.value,
        adapter_type: adapterType.value,
        options: filledOptions(),
      })
    }
    quasar.notify({ type: "positive", message: "Connection saved" })
    emit("update:modelValue", false)
  } catch (error) {
    const serverErrors = serverErrorsFrom(error)
    if (serverErrors) {
      applyServerErrors(serverErrors)
    } else {
      quasar.notify({ type: "negative", message: "Could not save the connection" })
    }
  }
}

const saving = computed(
  () => createConnector.isPending.value || updateConnector.isPending.value
)
</script>

<template>
  <q-dialog
    :model-value="modelValue"
    @update:model-value="emit('update:modelValue', $event)"
  >
    <q-card style="width: 520px; max-width: 90vw">
      <q-card-section>
        <div class="text-h6">
          {{ isEdit ? "Edit connection" : "New connection" }}
        </div>
      </q-card-section>

      <q-card-section class="q-gutter-md">
        <q-input
          v-model="name"
          label="Name"
          data-testid="connector-name"
          :error="Boolean(nameError)"
          :error-message="nameError"
        />

        <q-select
          v-model="adapterType"
          :options="typeOptions"
          option-value="value"
          option-label="label"
          emit-value
          map-options
          label="Source type"
          data-testid="connector-type"
          :disable="isEdit"
          :loading="adapterTypes.isLoading.value"
        />

        <SchemaFields
          v-if="fields.length"
          v-model="optionValues"
          :fields="fields"
          :errors="optionErrors"
          :secret-placeholder="secretPlaceholder"
        />

        <ConnectionCheck :result="checkResult" />
      </q-card-section>

      <q-card-actions align="right">
        <q-btn flat label="Cancel" @click="emit('update:modelValue', false)" />
        <q-btn
          flat
          color="primary"
          label="Check"
          data-testid="check-draft"
          :disable="!adapterType"
          :loading="checkDraft.isPending.value"
          @click="check"
        />
        <q-btn
          color="primary"
          label="Save"
          data-testid="save-connector"
          :disable="!adapterType"
          :loading="saving"
          @click="submit"
        />
      </q-card-actions>
    </q-card>
  </q-dialog>
</template>
```

- [ ] **Step 3: Wire the dialog into the page**

In `frontend/src/features/connectors/ConnectorsPage.vue` add the import to the `<script setup>` block:

```ts
import ConnectorDialog from "@/features/connectors/ConnectorDialog.vue"
```

and add to the template, right after `<ConnectorTable ... />` and before the closing `</AppLayout>`:

```vue
    <ConnectorDialog v-model="dialogOpen" :connector="editing" />
```

- [ ] **Step 4: Check the scenario manually**

Run: `docker compose up -d db backend && cd frontend && bun run dev`

Walk through the scenario:
1. Log in, click "New connection".
2. Choose the type "PostgreSQL" — the fields Host, Port, Database, User, Password appear; Password has type `password`, Port has value 5432.
3. Fill in the database parameters from the root `.env`, click "Check".
Expected: a green line with a success text and the response time.
4. Break the password, click "Check".
Expected: a red line "Authentication error", the password is absent from the text.
5. Restore the password, click "Save".
Expected: a success notification, the dialog closes, the row appears in the table.
6. Click "Edit" on the created row.
Expected: the Password field is empty with the hint "Leave unchanged", the type selection is disabled.
7. Change only Port and click "Check".
Expected: the check succeeds — the server fills in the password from the saved record.

Stop the server.

- [ ] **Step 5: Check types, style and unit tests**

Run: `cd frontend && bun run type-check && bun run lint && bun run test:unit`
Expected: no errors, 25 unit tests pass.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/features/connectors
git commit -m "feat: dialog to create and edit a connection with a connection check"
```

---

### Task 8: Playwright scenario and serving the build from the backend

**Files:**
- Delete: `frontend/tests/admin.spec.ts`, `items.spec.ts`, `login.spec.ts`, `reset-password.spec.ts`, `sign-up.spec.ts`, `user-settings.spec.ts`, `auth.setup.ts`, `frontend/tests/utils/`
- Create: `frontend/tests/connectors.spec.ts`
- Create: `frontend/tests/utils/login.ts`
- Modify: `backend/app/main.py`

**Interfaces:**
- Consumes: everything above.
- Produces: an e2e scenario confirming the slice's completion criterion.

- [ ] **Step 1: Remove the scenarios written for the React interface**

```bash
cd frontend
git rm --quiet tests/admin.spec.ts tests/items.spec.ts tests/login.spec.ts
git rm --quiet tests/reset-password.spec.ts tests/sign-up.spec.ts tests/user-settings.spec.ts
git rm --quiet tests/auth.setup.ts
git rm -r --quiet tests/utils
```

The file `tests/config.ts` is kept: it reads `FIRST_SUPERUSER` and `FIRST_SUPERUSER_PASSWORD` from the root `.env`.

- [ ] **Step 2: Remove the setup project from the Playwright configuration**

In `frontend/playwright.config.ts` remove from the `projects` array the entry

```ts
    { name: 'setup', testMatch: /.*\.setup\.ts/ },
```

and, if the `chromium` project has `dependencies: ['setup']` or `storageState` fields, remove them too: login happens inside the scenario.

- [ ] **Step 3: Write a login helper**

Create `frontend/tests/utils/login.ts`:

```ts
import type { Page } from "@playwright/test"

import { firstSuperuser, firstSuperuserPassword } from "../config"

export async function login(page: Page) {
  await page.goto("/login")
  await page.getByTestId("login-email").locator("input").fill(firstSuperuser)
  await page.getByTestId("login-password").locator("input").fill(firstSuperuserPassword)
  await page.getByTestId("login-submit").click()
  await page.waitForURL("/")
}
```

- [ ] **Step 4: Write the scenario**

Create `frontend/tests/connectors.spec.ts`:

```ts
import { expect, test } from "@playwright/test"

import { login } from "./utils/login"

const CONNECTOR_NAME = `e2e-postgres-${Date.now()}`

const DATABASE = {
  host: process.env.POSTGRES_SERVER ?? "localhost",
  port: process.env.POSTGRES_PORT ?? "5432",
  database: process.env.POSTGRES_DB ?? "app",
  user: process.env.POSTGRES_USER ?? "postgres",
  password: process.env.POSTGRES_PASSWORD ?? "",
}

test("creating a connection, checking the connection and deleting it", async ({ page }) => {
  await login(page)

  await page.getByTestId("add-connector").click()
  await page.getByTestId("connector-name").locator("input").fill(CONNECTOR_NAME)

  await page.getByTestId("connector-type").click()
  await page.getByRole("option", { name: "PostgreSQL" }).click()

  await page.getByTestId("field-host").locator("input").fill(DATABASE.host)
  await page.getByTestId("field-port").locator("input").fill(DATABASE.port)
  await page.getByTestId("field-database").locator("input").fill(DATABASE.database)
  await page.getByTestId("field-user").locator("input").fill(DATABASE.user)
  await page.getByTestId("field-password").locator("input").fill(DATABASE.password)

  await page.getByTestId("check-draft").click()
  const result = page.getByTestId("check-result")
  await expect(result).toBeVisible()
  await expect(result).toHaveClass(/bg-positive/)

  await page.getByTestId("save-connector").click()
  await expect(page.getByTestId("connector-table")).toContainText(CONNECTOR_NAME)

  await page.getByTestId(`check-${CONNECTOR_NAME}`).click()
  await expect(page.locator(".q-notification").first()).toBeVisible()

  await page.getByTestId(`delete-${CONNECTOR_NAME}`).click()
  await page.getByRole("button", { name: "Delete" }).click()
  await expect(page.getByTestId("connector-table")).not.toContainText(CONNECTOR_NAME)
})

test("a wrong password shows an authentication error without leaking the password", async ({ page }) => {
  const wrongPassword = "definitely-not-the-password"
  await login(page)

  await page.getByTestId("add-connector").click()
  await page.getByTestId("connector-name").locator("input").fill(`e2e-bad-${Date.now()}`)
  await page.getByTestId("connector-type").click()
  await page.getByRole("option", { name: "PostgreSQL" }).click()

  await page.getByTestId("field-host").locator("input").fill(DATABASE.host)
  await page.getByTestId("field-port").locator("input").fill(DATABASE.port)
  await page.getByTestId("field-database").locator("input").fill(DATABASE.database)
  await page.getByTestId("field-user").locator("input").fill(DATABASE.user)
  await page.getByTestId("field-password").locator("input").fill(wrongPassword)

  await page.getByTestId("check-draft").click()

  const result = page.getByTestId("check-result")
  await expect(result).toBeVisible()
  await expect(result).toHaveClass(/bg-negative/)
  await expect(result).toContainText("Authentication error")
  await expect(result).not.toContainText(wrongPassword)
})
```

- [ ] **Step 5: Run the scenario on a clean database**

Run: `docker compose down -v && docker compose up -d db backend`
Expected: containers are up, the database is empty, the superuser is created by the initialisation script.

Run: `cd frontend && bun run dev`
Expected: Vite on 5173. Leave it running in a separate terminal.

Run: `cd frontend && bunx playwright test`
Expected: PASS, 2 scenarios.

This is the completion criterion of the first slice from the spec.

- [ ] **Step 6: Bring back serving the built frontend from the backend**

Task 1 of the backend plan removed static file serving from `backend/app/main.py`, because the build directory did not exist and importing the application in tests depended on it. Now the Vue build is placed at the same path, and serving can be brought back safely — with a check that the directory exists, so that backend tests do not require a built frontend.

Run: `cd frontend && bun run build`
Expected: the build succeeds, `backend/app/frontend/index.html` appears.

In `backend/app/main.py` add at the top of the file

```python
from pathlib import Path
```

and at the end of the file

```python
FRONTEND_DIR = Path(__file__).parent / "frontend"

if FRONTEND_DIR.is_dir():
    app.frontend("/", directory=FRONTEND_DIR)
```

- [ ] **Step 7: Check that the backend starts with and without serving**

Run: `cd backend && uv run python -c "import app.main; print('import with built frontend OK')"`
Expected: the message without a traceback.

Run: `rm -rf backend/app/frontend && cd backend && uv run python -c "import app.main; print('import without build OK')"`
Expected: the message without a traceback.

Run: `cd backend && uv run pytest tests/ -q`
Expected: PASS in full.

The `app.frontend()` method is present in the installed FastAPI version (0.141.1) — this was checked while doing task 1 of the backend plan. It was also found there that it raises `RuntimeError` if the directory does not exist; that is why the `is_dir()` check is here.

- [ ] **Step 8: Check types and style**

Run: `cd frontend && bun run type-check && bun run lint && bun run test:unit`
Expected: no errors.

Run: `cd backend && uv run ruff check app`
Expected: no errors.

- [ ] **Step 9: Commit**

```bash
git add -A frontend backend/app/main.py
git commit -m "test: Playwright scenario for connectors and serving the build from the backend"
```

---

## Outcome

After task 8 the slice is complete:

- the user logs in and sees a list of their connections;
- creates a PostgreSQL connection through a form built from the adapter schema at runtime;
- checks the connection before and after saving;
- edits a connection without re-entering the password;
- the Playwright scenario passes on a clean database — the completion criterion from the spec is met.

## What is left outside the slice

According to the spec, next come subprojects 2a (splitting `models.py` and `crud.py` into modules), 3 (catalog), 4 (data fetching and connection pool), 5 (action registry), 6 (a second, non-SQL adapter) and then realtime, AI and the grid. Each gets its own spec and plan.

A separate backlog task remains: SSRF restriction in `check-draft` — an allowlist of addresses before connecting.
