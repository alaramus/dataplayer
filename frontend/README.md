# Frontend

Vue 3 + TypeScript + Quasar, built with Vite. The typed API client is generated
from the backend's OpenAPI and lives in `src/client` — it is never edited by
hand.

## Commands

```sh
bun run dev           # dev server on http://localhost:5173
bun run build         # production build into ../backend/app/frontend
bun run build:checked # the same, with a type check first
bun run type-check    # vue-tsc; needs Node, see below
bun run lint          # ESLint with auto-fix
bun run format        # Prettier over src/
bun run test:unit     # Vitest
bun run test          # Playwright
```

## vue-tsc needs Node, not bun

`vue-tsc` does not work under the bun runtime: it fails to register the `.vue`
extension, so every component silently drops out of the compiler program and
imports such as `@/App.vue` start to look like they point at nothing. Measured:
under Node every `.vue` file is in the program, under bun none of them is.

What follows from that:

- run `type-check` and `build:checked` where a real Node is installed. On
  Windows this happens by itself: the `.cmd` shim invokes Node.
- the `oven/bun:1` image has no real Node, so `build` deliberately runs
  `vite build` alone. The bundler does not need the types — it strips them.

## Generating the client

```sh
bash scripts/generate-client.sh   # from the repository root
```

The script dumps OpenAPI from the backend and regenerates `src/client`.
