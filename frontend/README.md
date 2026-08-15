# Фронтенд

Vue 3 + TypeScript + Quasar, сборка на Vite. Типизированный клиент API
генерируется из OpenAPI бэкенда и лежит в `src/client` — руками не правится.

## Команды

```sh
bun run dev           # сервер разработки на http://localhost:5173
bun run build         # production-сборка в ../backend/app/frontend
bun run build:checked # то же, но с предварительной проверкой типов
bun run type-check    # vue-tsc, требует Node (см. ниже)
bun run lint          # ESLint с автоисправлением
bun run format        # Prettier по src/
bun run test:unit     # Vitest
bun run test          # Playwright
```

## vue-tsc требует Node, а не bun

`vue-tsc` не работает на рантайме bun: он не регистрирует расширение `.vue`,
поэтому все компоненты молча выпадают из программы компилятора, а импорты
вида `@/App.vue` начинают выглядеть несуществующими. Проверено замером —
под Node в программу попадают все `.vue`, под bun ни одного.

Следствия:

- `type-check` и `build:checked` запускайте там, где установлен настоящий
  Node. На Windows это происходит само: обёртка `.cmd` вызывает Node.
- В образе `oven/bun:1` настоящего Node нет, поэтому `build` намеренно
  выполняет только `vite build`. Бандлеру типы не нужны — он их отбрасывает.

## Генерация клиента

```sh
bash scripts/generate-client.sh   # из корня репозитория
```

Скрипт поднимает OpenAPI из бэкенда и перегенерирует `src/client`.
