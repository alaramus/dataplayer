# План реализации: реестр коннекторов, фронтенд

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Экран, на котором пользователь заводит подключение к PostgreSQL по форме, построенной из схемы адаптера, проверяет соединение и видит результат.

**Architecture:** Директория `frontend/` пересоздаётся на Vue 3 вместо React. Типизированный клиент по-прежнему генерируется из OpenAPI через `@hey-api/openapi-ts` — он от фреймворка не зависит. Серверное состояние живёт в `@tanstack/vue-query`, Pinia хранит только клиентское. Форма подключения строится в рантайме из JSON Schema, которую отдаёт `GET /api/v1/adapter-types/`.

**Tech Stack:** Vue 3, TypeScript, Vite, Quasar (через `@quasar/vite-plugin`), Vue Router, Pinia, `@tanstack/vue-query`, zod, `@hey-api/openapi-ts` с клиентом на axios, Vitest + `@vue/test-utils`, Playwright, ESLint + Prettier, bun как раннер.

Спек: [2026-08-15-connector-registry-design.md](../2026-08-15-connector-registry-design.md)
Бэкенд: [2026-08-15-connector-registry-backend.md](2026-08-15-connector-registry-backend.md) — должен быть выполнен полностью до начала этого плана.

## Global Constraints

- Пакеты ставятся и запускаются через `bun`; корневой `package.json` объявляет workspace `frontend`.
- `bun run --filter frontend type-check` (`vue-tsc --noEmit`) проходит без ошибок после каждой задачи.
- `bun run --filter frontend lint` проходит без ошибок после каждой задачи.
- Composition API и `<script setup lang="ts">` во всех новых SFC.
- Серверное состояние — только в `@tanstack/vue-query`. В Pinia не хранится ничего, что можно перезапросить у сервера.
- Секретные поля никогда не подставляются в форму редактирования: они приходят пустыми и отправляются, только если заполнены.
- Vite слушает порт 5173 — на него настроен `frontend/playwright.config.ts`.
- Бэкенд для ручной проверки поднимается командой `docker compose up -d db backend`.

## Замена React на Vue: что удаляется и что сохраняется

**Сохраняется:** `frontend/openapi-ts.config.ts`, `frontend/playwright.config.ts`, `frontend/tests/config.ts`, `frontend/.env`, `frontend/public/`, `frontend/index.html` (правится точечно), `scripts/generate-client.sh`, корневой `package.json`.

**Удаляется:** весь `frontend/src/` кроме сгенерированного `frontend/src/client/`, все спеки в `frontend/tests/` кроме `config.ts`, `frontend/biome.json`, `frontend/components.json`, `frontend/.tanstack/`.

---

### Task 1: Каркас Vue-приложения

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
- Consumes: ничего.
- Produces:
  - `@/stores/auth` — `useAuthStore()` с полями `token: Ref<string | null>`, `isLoggedIn: ComputedRef<boolean>` и методами `setToken(value: string): void`, `clear(): void`
  - `@/router` — экспорт `router`
  - алиас `@` указывает на `frontend/src`

- [ ] **Step 1: Удалить исходники React**

```bash
cd frontend
git rm -r --quiet src/components src/hooks src/lib src/routes
git rm --quiet src/main.tsx src/utils.ts src/index.css src/routeTree.gen.ts biome.json components.json
rm -rf .tanstack
```

Директория `src/client/` не трогается: она сгенерирована и переиспользуется.

- [ ] **Step 2: Переписать package.json**

Полностью заменить содержимое `frontend/package.json`:

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

Библиотека форм намеренно отсутствует. Схема валидации строится в рантайме из JSON Schema, поэтому типизация, ради которой обычно берут `vee-validate` с `toTypedSchema`, здесь всё равно недостижима; проверка через `schema.safeParse()` в небольшом композабле занимает меньше кода, чем настройка зависимости.

- [ ] **Step 3: Установить зависимости**

Run: `cd frontend && rm -rf node_modules && cd .. && bun install`
Expected: установка завершается успешно, React-пакеты в `bun.lock` отсутствуют.

- [ ] **Step 4: Переписать vite.config.ts**

Полностью заменить содержимое `frontend/vite.config.ts`:

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

- [ ] **Step 5: Настроить TypeScript**

Заменить содержимое `frontend/tsconfig.json`:

```json
{
  "files": [],
  "references": [
    { "path": "./tsconfig.build.json" },
    { "path": "./tsconfig.node.json" }
  ]
}
```

Заменить содержимое `frontend/tsconfig.build.json`:

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

Добавить `@vue/tsconfig` в `devDependencies` `frontend/package.json`:

```json
    "@vue/tsconfig": "^0.8.1",
```

и переустановить: `cd .. && bun install`.

Заменить содержимое `frontend/tsconfig.node.json`:

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

Добавить `@tsconfig/node22` в `devDependencies`:

```json
    "@tsconfig/node22": "^22.0.2",
```

Создать `frontend/env.d.ts`:

```ts
/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_URL: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
```

- [ ] **Step 6: Настроить линтер и форматирование**

Создать `frontend/eslint.config.js`:

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

Директория `src/client/` исключена: она генерируется и правкам не подлежит.

Добавить `@eslint/js` в `devDependencies`:

```json
    "@eslint/js": "^9.39.0",
```

Создать `frontend/.prettierrc.json`:

```json
{
  "semi": false,
  "singleQuote": false,
  "printWidth": 100,
  "trailingComma": "es5"
}
```

- [ ] **Step 7: Настроить Vitest**

Создать `frontend/vitest.config.ts`:

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

Модульные тесты лежат рядом с кодом и оканчиваются на `.spec.ts`; Playwright берёт свои файлы только из `frontend/tests/`, поэтому наборы не пересекаются.

- [ ] **Step 8: Создать точку входа**

Заменить содержимое `frontend/index.html`:

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

Создать `frontend/src/quasar-variables.sass`:

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

Создать `frontend/src/App.vue`:

```vue
<template>
  <router-view />
</template>
```

Создать `frontend/src/main.ts`:

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

Порядок важен: Pinia устанавливается до маршрутизатора, потому что навигационный сторож обращается к хранилищу.

- [ ] **Step 9: Создать хранилище аутентификации**

Создать `frontend/src/stores/auth.ts`:

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

- [ ] **Step 10: Создать маршрутизатор с заглушками**

Создать `frontend/src/router/index.ts`:

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

Создать временные заглушки, чтобы приложение собиралось до появления настоящих экранов.

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

- [ ] **Step 11: Проверить, что приложение собирается и запускается**

Run: `cd frontend && bun run type-check`
Expected: без ошибок.

Run: `cd frontend && bun run lint`
Expected: без ошибок.

Run: `cd frontend && bun run dev`
Expected: Vite стартует на `http://localhost:5173`. Открыть адрес в браузере — виден текст `login` (сторож перенаправляет неавторизованного пользователя). Остановить сервер.

- [ ] **Step 12: Commit**

```bash
git add -A frontend bun.lock
git commit -m "feat: заменить React-каркас фронтенда на Vue 3 с Quasar"
```

---

### Task 2: Клиент API и настройка запросов

**Files:**
- Create: `frontend/src/shared/api/configure.ts`
- Modify: `frontend/src/main.ts`
- Modify: `scripts/generate-client.sh`

**Interfaces:**
- Consumes: `useAuthStore` из задачи 1.
- Produces:
  - `@/shared/api/configure` — `configureApiClient(): void` и `createQueryClient(): QueryClient`
  - пересозданный `frontend/src/client/` с типами `ConnectorPublic`, `ConnectorsPublic`, `ConnectorCreate`, `ConnectorUpdate`, `ConnectionCheckResult`, `AdapterTypeInfo` и сервисами `ConnectorsService`, `AdapterTypesService`, `LoginService`, `UsersService`

- [ ] **Step 1: Перегенерировать клиент из OpenAPI бэкенда**

Убедиться, что бэкенд из первого плана выполнен и БД поднята.

Run: `docker compose up -d db`
Expected: контейнер `db` running.

В `scripts/generate-client.sh` последняя строка вызывает `bun run lint`, который теперь работает через ESLint и упал бы на сгенерированном коде. Заменить её на форматирование:

```bash
bun run --filter frontend format
```

Run: `bash scripts/generate-client.sh`
Expected: скрипт завершается успешно; в `frontend/src/client/types.gen.ts` присутствуют типы `ConnectorPublic`, `ConnectorCreate`, `ConnectionCheckResult`, `AdapterTypeInfo`.

- [ ] **Step 2: Проверить имена сервисов в сгенерированном коде**

Run: `cd frontend && grep -n "export class .*Service" src/client/sdk.gen.ts`
Expected: в выводе присутствуют `ConnectorsService` и `AdapterTypesService`. Если имена отличаются, использовать фактические имена во всех последующих задачах.

- [ ] **Step 3: Реализовать настройку клиента**

Создать `frontend/src/shared/api/configure.ts`:

```ts
import { MutationCache, QueryCache, QueryClient } from "@tanstack/vue-query"
import { AxiosError } from "axios"

import { client } from "@/client/client.gen"
import { router } from "@/router"
import { useAuthStore } from "@/stores/auth"

export function configureApiClient() {
  client.setConfig({
    baseURL: import.meta.env.VITE_API_URL ?? "",
    // Клиент сам подставляет схему Bearer по описанию безопасности из OpenAPI.
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

- [ ] **Step 4: Подключить настройку в точке входа**

Заменить содержимое `frontend/src/main.ts`:

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
// Настройка клиента обращается к хранилищу, поэтому идёт после установки Pinia.
configureApiClient()

app
  .use(Quasar, { plugins: { Notify, Dialog } })
  .use(router)
  .use(VueQueryPlugin, { queryClient: createQueryClient() })
  .mount("#app")
```

- [ ] **Step 5: Проверить типы и стиль**

Run: `cd frontend && bun run type-check && bun run lint`
Expected: без ошибок.

- [ ] **Step 6: Commit**

```bash
git add frontend/src scripts/generate-client.sh
git commit -m "feat: генерация клиента API и настройка запросов на Vue"
```

---

### Task 3: Вход в систему и оболочка приложения

**Files:**
- Create: `frontend/src/features/auth/api.ts`
- Modify: `frontend/src/features/auth/LoginPage.vue`
- Create: `frontend/src/shared/ui/AppLayout.vue`
- Modify: `frontend/src/App.vue`

**Interfaces:**
- Consumes: `useAuthStore`, `router`, сгенерированный `LoginService`.
- Produces:
  - `@/features/auth/api` — `useLogin()` с полями `mutate(credentials: { username: string; password: string })`, `isPending: Ref<boolean>`, `error: Ref<Error | null>`
  - `@/shared/ui/AppLayout.vue` — оболочка с шапкой и кнопкой выхода, содержимое подставляется через слот по умолчанию

- [ ] **Step 1: Реализовать вызов входа**

Создать `frontend/src/features/auth/api.ts`:

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

- [ ] **Step 2: Реализовать экран входа**

Заменить содержимое `frontend/src/features/auth/LoginPage.vue`:

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
            <div class="text-h6">Вход</div>
          </q-card-section>
          <q-form @submit.prevent="submit">
            <q-card-section class="q-gutter-md">
              <q-input
                v-model="username"
                label="Электронная почта"
                type="email"
                autocomplete="username"
                data-testid="login-email"
                :rules="[(value: string) => !!value || 'Укажите почту']"
              />
              <q-input
                v-model="password"
                label="Пароль"
                type="password"
                autocomplete="current-password"
                data-testid="login-password"
                :rules="[(value: string) => !!value || 'Укажите пароль']"
              />
              <q-banner v-if="failed" dense class="bg-negative text-white" data-testid="login-error">
                Не удалось войти. Проверьте почту и пароль.
              </q-banner>
            </q-card-section>
            <q-card-actions>
              <q-btn
                type="submit"
                color="primary"
                class="full-width"
                label="Войти"
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

Атрибуты `data-testid` нужны сценариям Playwright из задачи 8: подписи на русском языке могут поменяться, идентификаторы — нет.

- [ ] **Step 3: Реализовать оболочку**

Создать `frontend/src/shared/ui/AppLayout.vue`:

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
        <q-btn flat dense label="Выйти" data-testid="logout" @click="logout" />
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

Кеш `vue-query` очищается при выходе: иначе данные предыдущего пользователя останутся видимыми следующему.

- [ ] **Step 4: Проверить вход вручную**

Run: `docker compose up -d db backend`
Expected: оба контейнера running.

Run: `cd frontend && bun run dev`
Expected: Vite на 5173.

Открыть `http://localhost:5173`, войти с учётными данными `FIRST_SUPERUSER` и `FIRST_SUPERUSER_PASSWORD` из корневого `.env`.
Expected: переход на `/`, виден текст `connectors`. При неверном пароле показывается баннер с ошибкой. Остановить сервер.

- [ ] **Step 5: Проверить типы и стиль**

Run: `cd frontend && bun run type-check && bun run lint`
Expected: без ошибок.

- [ ] **Step 6: Commit**

```bash
git add frontend/src
git commit -m "feat: вход в систему и оболочка приложения"
```

---

### Task 4: Преобразование JSON Schema в схему валидации и описание полей

Чистые функции без привязки к Vue — единственная часть фронтенда, покрываемая модульными тестами полностью.

**Files:**
- Create: `frontend/src/features/connectors/SchemaForm/jsonSchema.ts`
- Create: `frontend/src/features/connectors/SchemaForm/jsonSchema.spec.ts`

**Interfaces:**
- Consumes: `zod`.
- Produces:
  - `@/features/connectors/SchemaForm/jsonSchema` — тип `JsonSchema`, тип `FieldSpec` с полями `name: string`, `label: string`, `kind: "text" | "password" | "number" | "boolean" | "select"`, `required: boolean`, `defaultValue?: unknown`, `choices?: string[]`
  - `schemaToFields(schema: JsonSchema): FieldSpec[]`
  - `jsonSchemaToZod(schema: JsonSchema): z.ZodObject`
  - `defaultValues(fields: FieldSpec[]): Record<string, unknown>`

- [ ] **Step 1: Написать падающие тесты**

Создать `frontend/src/features/connectors/SchemaForm/jsonSchema.spec.ts`:

```ts
import { describe, expect, it } from "vitest"

import { defaultValues, jsonSchemaToZod, schemaToFields } from "./jsonSchema"
import type { JsonSchema } from "./jsonSchema"

// Форма, в которой Pydantic отдаёт схему PostgresOptions.
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

- [ ] **Step 2: Запустить тесты и убедиться, что они падают**

Run: `cd frontend && bun run test:unit`
Expected: FAIL — модуль `./jsonSchema` не найден.

- [ ] **Step 3: Реализовать преобразование**

Создать `frontend/src/features/connectors/SchemaForm/jsonSchema.ts`:

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
      // Обязательное строковое поле не должно проходить проверку пустым.
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

- [ ] **Step 4: Запустить тесты и убедиться, что они проходят**

Run: `cd frontend && bun run test:unit`
Expected: PASS, 15 тестов.

Если тест `defaults booleans to false` или `uses schema defaults and blanks for the rest` не сошёлся по типу `null` для числового поля без значения по умолчанию — в наборе таких полей нет, `port` имеет `default`. Расхождение означает ошибку в `defaultValues`.

- [ ] **Step 5: Проверить типы и стиль**

Run: `cd frontend && bun run type-check && bun run lint`
Expected: без ошибок.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/features/connectors/SchemaForm
git commit -m "feat: преобразование JSON Schema в схему валидации и описание полей"
```

---

### Task 5: Компонент полей формы

**Files:**
- Create: `frontend/src/features/connectors/SchemaForm/SchemaFields.vue`
- Create: `frontend/src/features/connectors/SchemaForm/SchemaFields.spec.ts`
- Create: `frontend/src/features/connectors/SchemaForm/useSchemaForm.ts`
- Create: `frontend/src/features/connectors/SchemaForm/useSchemaForm.spec.ts`

**Interfaces:**
- Consumes: `FieldSpec`, `jsonSchemaToZod`, `defaultValues` из задачи 4.
- Produces:
  - `@/features/connectors/SchemaForm/SchemaFields.vue` — свойства `fields: FieldSpec[]`, `modelValue: Record<string, unknown>`, `errors: Record<string, string>`, `secretPlaceholder?: string`; событие `update:modelValue`
  - `@/features/connectors/SchemaForm/useSchemaForm` — `useSchemaForm()` возвращает `values: Ref<Record<string, unknown>>`, `errors: Ref<Record<string, string>>`, `validate(schema): boolean`, `applyServerErrors(detail): void`, `reset(fields): void`

- [ ] **Step 1: Написать падающие тесты для композабла**

Создать `frontend/src/features/connectors/SchemaForm/useSchemaForm.spec.ts`:

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

- [ ] **Step 2: Запустить тесты и убедиться, что они падают**

Run: `cd frontend && bun run test:unit`
Expected: FAIL — модуль `./useSchemaForm` не найден.

- [ ] **Step 3: Реализовать композабл**

Создать `frontend/src/features/connectors/SchemaForm/useSchemaForm.ts`:

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
      // Путь имеет вид ["body", "options", "<поле>"]; всё короче поля не касается.
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

- [ ] **Step 4: Запустить тесты и убедиться, что они проходят**

Run: `cd frontend && bun run test:unit`
Expected: PASS, 20 тестов.

- [ ] **Step 5: Написать падающие тесты для компонента**

Создать `frontend/src/features/connectors/SchemaForm/SchemaFields.spec.ts`:

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

- [ ] **Step 6: Запустить тесты и убедиться, что они падают**

Run: `cd frontend && bun run test:unit`
Expected: FAIL — компонент `SchemaFields.vue` не найден.

- [ ] **Step 7: Реализовать компонент**

Создать `frontend/src/features/connectors/SchemaForm/SchemaFields.vue`:

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

- [ ] **Step 8: Запустить тесты и убедиться, что они проходят**

Run: `cd frontend && bun run test:unit`
Expected: PASS, 25 тестов.

- [ ] **Step 9: Проверить типы и стиль**

Run: `cd frontend && bun run type-check && bun run lint`
Expected: без ошибок.

- [ ] **Step 10: Commit**

```bash
git add frontend/src/features/connectors/SchemaForm
git commit -m "feat: компонент полей формы, построенной из схемы адаптера"
```

---

### Task 6: Экран коннекторов со списком

**Files:**
- Create: `frontend/src/features/connectors/api.ts`
- Modify: `frontend/src/features/connectors/ConnectorsPage.vue`
- Create: `frontend/src/features/connectors/ConnectorTable.vue`

**Interfaces:**
- Consumes: сгенерированные `ConnectorsService`, `AdapterTypesService`; `AppLayout` из задачи 3.
- Produces:
  - `@/features/connectors/api` — `useConnectors()`, `useAdapterTypes()`, `useCreateConnector()`, `useUpdateConnector()`, `useDeleteConnector()`, `useCheckConnector()`, `useCheckDraft()`, константа `connectorsKey`
  - `@/features/connectors/ConnectorTable.vue` — свойства `rows: ConnectorPublic[]`, `loading: boolean`; события `edit`, `remove`, `check` с полезной нагрузкой `ConnectorPublic`

- [ ] **Step 1: Реализовать слой запросов**

Создать `frontend/src/features/connectors/api.ts`:

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
    // Реестр типов меняется только при развёртывании — перезапрашивать нечего.
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

Имена методов сервисов взяты из соглашения генератора: имя операции без префикса тега. Если шаг 2 задачи 2 показал другие имена, использовать фактические.

- [ ] **Step 2: Реализовать таблицу**

Создать `frontend/src/features/connectors/ConnectorTable.vue`:

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
  { name: "name", label: "Название", field: "name", align: "left" as const, sortable: true },
  { name: "adapter_type", label: "Тип", field: "adapter_type", align: "left" as const },
  { name: "host", label: "Хост", field: "host", align: "left" as const },
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
    no-data-label="Пока нет ни одного подключения"
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
          <q-tooltip>Проверить соединение</q-tooltip>
        </q-btn>
        <q-btn
          dense
          flat
          icon="edit"
          :data-testid="`edit-${cellProps.row.name}`"
          @click="$emit('edit', cellProps.row)"
        >
          <q-tooltip>Изменить</q-tooltip>
        </q-btn>
        <q-btn
          dense
          flat
          icon="delete"
          color="negative"
          :data-testid="`delete-${cellProps.row.name}`"
          @click="$emit('remove', cellProps.row)"
        >
          <q-tooltip>Удалить</q-tooltip>
        </q-btn>
      </q-td>
    </template>
  </q-table>
</template>
```

- [ ] **Step 3: Реализовать страницу**

Заменить содержимое `frontend/src/features/connectors/ConnectorsPage.vue`:

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
      ? `${result.message} (${String(result.latency_ms)} мс)`
      : result.message,
  })
}

function confirmRemove(connector: ConnectorPublic) {
  quasar
    .dialog({
      title: "Удалить подключение",
      message: `Подключение «${connector.name}» будет удалено безвозвратно.`,
      cancel: true,
      ok: { label: "Удалить", color: "negative" },
    })
    .onOk(() => {
      void removeConnector.mutateAsync(connector.id).then(() => {
        quasar.notify({ type: "positive", message: "Подключение удалено" })
      })
    })
}
</script>

<template>
  <AppLayout>
    <div class="row items-center justify-between q-mb-md">
      <div class="text-h5">Подключения</div>
      <q-btn
        color="primary"
        icon="add"
        label="Новое подключение"
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

Диалог сюда ещё не подключается: он появится в задаче 7, и тогда же в этот файл добавятся импорт и разметка. Переменные `dialogOpen` и `editing` объявлены заранее, потому что от них зависят обработчики `openCreate` и `openEdit`.

- [ ] **Step 4: Проверить, что список показывается**

Run: `docker compose up -d db backend && cd frontend && bun run dev`
Expected: после входа виден заголовок «Подключения», таблица с текстом «Пока нет ни одного подключения» и кнопка «Новое подключение». Нажатие кнопки пока ничего не открывает — это ожидаемо. Остановить сервер.

- [ ] **Step 5: Проверить типы и стиль**

Run: `cd frontend && bun run type-check && bun run lint`
Expected: без ошибок.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/features/connectors
git commit -m "feat: экран коннекторов со списком подключений"
```

---

### Task 7: Диалог создания и редактирования с проверкой соединения

**Files:**
- Create: `frontend/src/features/connectors/ConnectorDialog.vue`
- Create: `frontend/src/features/connectors/ConnectionCheck.vue`

**Interfaces:**
- Consumes: всё из задач 4, 5, 6.
- Produces:
  - `@/features/connectors/ConnectorDialog.vue` — свойства `modelValue: boolean`, `connector: ConnectorPublic | null`; событие `update:modelValue`
  - `@/features/connectors/ConnectionCheck.vue` — свойство `result: ConnectionCheckResult | null`

- [ ] **Step 1: Реализовать показ результата проверки**

Создать `frontend/src/features/connectors/ConnectionCheck.vue`:

```vue
<script setup lang="ts">
import { computed } from "vue"

import type { ConnectionCheckResult } from "@/client"

const props = defineProps<{
  result: ConnectionCheckResult | null
}>()

const KIND_LABELS: Record<string, string> = {
  auth: "Ошибка аутентификации",
  network: "Сервер недоступен",
  timeout: "Превышено время ожидания",
  config: "Ошибка в параметрах",
  unknown: "Неизвестная ошибка",
}

const text = computed(() => {
  if (!props.result) return ""
  if (props.result.ok) {
    return `${props.result.message} (${String(props.result.latency_ms)} мс)`
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

Результат показывается строкой внутри диалога, а не всплывающим уведомлением: его читают рядом с полями, которые правят.

- [ ] **Step 2: Реализовать диалог**

Создать `frontend/src/features/connectors/ConnectorDialog.vue`:

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

// Разбираем композабл на отдельные ref-ы: в шаблоне Vue разворачивает только
// ref-ы верхнего уровня, поэтому form.values пришлось бы писать как
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

// В режиме редактирования секретные поля приходят пустыми: сервер их не отдаёт.
const secretPlaceholder = computed(() => (isEdit.value ? "Оставить без изменений" : undefined))

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
  // Пустые секретные поля не отправляются: сервер сохранит прежние значения.
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
  nameError.value = name.value.trim() === "" ? "Укажите название" : ""
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
      quasar.notify({ type: "negative", message: "Не удалось выполнить проверку" })
    }
  }
}

async function submit() {
  if (!adapterType.value || !selectedSchema.value) return
  const nameValid = validateName()
  // В режиме редактирования пустой пароль допустим, поэтому схема проверяется
  // только по фактически заполненным значениям.
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
    quasar.notify({ type: "positive", message: "Подключение сохранено" })
    emit("update:modelValue", false)
  } catch (error) {
    const serverErrors = serverErrorsFrom(error)
    if (serverErrors) {
      applyServerErrors(serverErrors)
    } else {
      quasar.notify({ type: "negative", message: "Не удалось сохранить подключение" })
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
          {{ isEdit ? "Изменить подключение" : "Новое подключение" }}
        </div>
      </q-card-section>

      <q-card-section class="q-gutter-md">
        <q-input
          v-model="name"
          label="Название"
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
          label="Тип источника"
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
        <q-btn flat label="Отмена" @click="emit('update:modelValue', false)" />
        <q-btn
          flat
          color="primary"
          label="Проверить"
          data-testid="check-draft"
          :disable="!adapterType"
          :loading="checkDraft.isPending.value"
          @click="check"
        />
        <q-btn
          color="primary"
          label="Сохранить"
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

- [ ] **Step 3: Подключить диалог к странице**

В `frontend/src/features/connectors/ConnectorsPage.vue` добавить импорт в блок `<script setup>`:

```ts
import ConnectorDialog from "@/features/connectors/ConnectorDialog.vue"
```

и добавить в шаблон, сразу после `<ConnectorTable ... />` и перед закрывающим `</AppLayout>`:

```vue
    <ConnectorDialog v-model="dialogOpen" :connector="editing" />
```

- [ ] **Step 4: Проверить сценарий вручную**

Run: `docker compose up -d db backend && cd frontend && bun run dev`

Пройти сценарий:
1. Войти, нажать «Новое подключение».
2. Выбрать тип «PostgreSQL» — появляются поля Host, Port, Database, User, Password; у Password тип `password`, у Port значение 5432.
3. Заполнить параметрами БД из корневого `.env`, нажать «Проверить».
Expected: зелёная строка с текстом об успехе и временем отклика.
4. Испортить пароль, нажать «Проверить».
Expected: красная строка «Ошибка аутентификации», пароль в тексте отсутствует.
5. Вернуть пароль, нажать «Сохранить».
Expected: уведомление об успехе, диалог закрывается, строка появляется в таблице.
6. Нажать «Изменить» у созданной строки.
Expected: поле Password пустое с подсказкой «Оставить без изменений», выбор типа заблокирован.
7. Изменить только Port и нажать «Проверить».
Expected: проверка отрабатывает — пароль подставлен сервером из сохранённой записи.

Остановить сервер.

- [ ] **Step 5: Проверить типы, стиль и модульные тесты**

Run: `cd frontend && bun run type-check && bun run lint && bun run test:unit`
Expected: без ошибок, 25 модульных тестов проходят.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/features/connectors
git commit -m "feat: диалог создания и редактирования подключения с проверкой соединения"
```

---

### Task 8: Сценарий Playwright и раздача сборки бэкендом

**Files:**
- Delete: `frontend/tests/admin.spec.ts`, `items.spec.ts`, `login.spec.ts`, `reset-password.spec.ts`, `sign-up.spec.ts`, `user-settings.spec.ts`, `auth.setup.ts`, `frontend/tests/utils/`
- Create: `frontend/tests/connectors.spec.ts`
- Create: `frontend/tests/utils/login.ts`
- Modify: `backend/app/main.py`

**Interfaces:**
- Consumes: всё предыдущее.
- Produces: сценарий e2e, подтверждающий критерий готовности среза.

- [ ] **Step 1: Удалить сценарии, написанные под React-интерфейс**

```bash
cd frontend
git rm --quiet tests/admin.spec.ts tests/items.spec.ts tests/login.spec.ts
git rm --quiet tests/reset-password.spec.ts tests/sign-up.spec.ts tests/user-settings.spec.ts
git rm --quiet tests/auth.setup.ts
git rm -r --quiet tests/utils
```

Файл `tests/config.ts` сохраняется: он читает `FIRST_SUPERUSER` и `FIRST_SUPERUSER_PASSWORD` из корневого `.env`.

- [ ] **Step 2: Убрать из конфигурации Playwright проект setup**

В `frontend/playwright.config.ts` удалить из массива `projects` запись

```ts
    { name: 'setup', testMatch: /.*\.setup\.ts/ },
```

и, если у проекта `chromium` присутствуют поля `dependencies: ['setup']` или `storageState`, удалить и их: вход выполняется внутри сценария.

- [ ] **Step 3: Написать вспомогательную функцию входа**

Создать `frontend/tests/utils/login.ts`:

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

- [ ] **Step 4: Написать сценарий**

Создать `frontend/tests/connectors.spec.ts`:

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

test("создание подключения, проверка соединения и удаление", async ({ page }) => {
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
  await page.getByRole("button", { name: "Удалить" }).click()
  await expect(page.getByTestId("connector-table")).not.toContainText(CONNECTOR_NAME)
})

test("неверный пароль показывает ошибку аутентификации без утечки пароля", async ({ page }) => {
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
  await expect(result).toContainText("Ошибка аутентификации")
  await expect(result).not.toContainText(wrongPassword)
})
```

- [ ] **Step 5: Прогнать сценарий на чистой базе**

Run: `docker compose down -v && docker compose up -d db backend`
Expected: контейнеры подняты, база пустая, суперпользователь создан скриптом инициализации.

Run: `cd frontend && bun run dev`
Expected: Vite на 5173. Оставить запущенным в отдельном терминале.

Run: `cd frontend && bunx playwright test`
Expected: PASS, 2 сценария.

Это критерий готовности первого среза из спека.

- [ ] **Step 6: Вернуть раздачу собранного фронтенда бэкендом**

Задача 1 плана бэкенда удалила из `backend/app/main.py` раздачу статики, потому что директории сборки не существовало и от неё зависел импорт приложения в тестах. Теперь сборка Vue кладётся в тот же путь, и раздачу можно вернуть безопасно — с проверкой существования директории, чтобы тесты бэкенда не требовали собранного фронтенда.

Run: `cd frontend && bun run build`
Expected: сборка завершается успешно, появляется `backend/app/frontend/index.html`.

В `backend/app/main.py` добавить в начало файла

```python
from pathlib import Path
```

и в конец файла

```python
FRONTEND_DIR = Path(__file__).parent / "frontend"

if FRONTEND_DIR.is_dir():
    app.frontend("/", directory=FRONTEND_DIR)
```

- [ ] **Step 7: Проверить, что бэкенд поднимается с раздачей и без неё**

Run: `cd backend && uv run python -c "import app.main; print('импорт с собранным фронтендом OK')"`
Expected: сообщение без трассировки.

Run: `rm -rf backend/app/frontend && cd backend && uv run python -c "import app.main; print('импорт без сборки OK')"`
Expected: сообщение без трассировки.

Run: `cd backend && uv run pytest tests/ -q`
Expected: PASS целиком.

Метод `app.frontend()` в установленной версии FastAPI (0.141.1) присутствует — это проверено при выполнении задачи 1 плана бэкенда. Там же выяснено, что он бросает `RuntimeError`, если директории нет; именно поэтому здесь стоит проверка `is_dir()`.

- [ ] **Step 8: Проверить типы и стиль**

Run: `cd frontend && bun run type-check && bun run lint && bun run test:unit`
Expected: без ошибок.

Run: `cd backend && uv run ruff check app`
Expected: без ошибок.

- [ ] **Step 9: Commit**

```bash
git add -A frontend backend/app/main.py
git commit -m "test: сценарий Playwright для коннекторов и раздача сборки бэкендом"
```

---

## Итог

После задачи 8 срез завершён целиком:

- пользователь входит в систему, видит список своих подключений;
- заводит подключение к PostgreSQL по форме, построенной из схемы адаптера в рантайме;
- проверяет соединение до сохранения и после;
- редактирует подключение, не вводя пароль заново;
- сценарий Playwright проходит на чистой базе — критерий готовности из спека выполнен.

## Что осталось за пределами среза

Согласно спеку, дальше идут подпроекты 2а (расформирование `models.py` и `crud.py` по модулям), 3 (каталог), 4 (выборка данных и пул соединений), 5 (реестр действий), 6 (второй, не-SQL адаптер) и далее realtime, AI и грид. Каждый получает собственный спек и план.

Отдельной задачей в бэклоге остаётся ограничение SSRF в `check-draft`: список разрешённых адресов перед подключением.
