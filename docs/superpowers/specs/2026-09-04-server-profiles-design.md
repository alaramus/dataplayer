# Choosing a DataPlayer server

## Decision

D99: a browser tab works with one immutable backend context for the lifetime of
its document. A deliberate server switch navigates to a fresh document, with
independent credentials and persisted source state for the destination.

## User experience

The configured server is selected by default. Saved servers have a name and a
full HTTP(S) installation URL. The current server is visible in the application
footer and on the login page, where it can be changed even if the backend is
unavailable. A server can be checked, added, renamed, edited or removed; the
configured default remains available.

The saved list belongs to the browser, while the active server belongs to each
browser tab. Switching one tab does not switch another. Editing a profile's
address does not retarget other open tabs or transfer credentials to that
address. Accounts are independent on each server.

## Context and transport

- Normalize HTTP(S) URLs, preserve deployment path prefixes, and reject embedded
  credentials, query strings and fragments. The canonical URL is the server's
  identity; names are display labels only.
- HTTP, WebSocket, media tickets and downloads use that same context. Full
  navigation discards old in-memory queries, sockets and transient stores. A
  late response can only affect the old document and its old storage namespace.
- Tokens and source-dependent browser state are separated by server URL. Legacy
  storage keys remain assigned to the original configured server, recorded
  once, so changing the build's default later cannot send its old token elsewhere.
  Theme and general presentation preferences may remain browser-wide.
- The active profile is remembered in session storage. Navigation to a known
  saved server can select it for the new document. An unknown server named by a
  shared link requires explicit selection before any authenticated request.
- Share links carry the backend URL as well as the existing share token; the
  backend grant model is unchanged. Old links without a server use the configured
  default, rather than whichever unrelated server happens to be selected.

## Switching and compatibility

Before leaving, existing panel and window close guards are consulted. Unsaved
file content is guarded, SQL drafts are kept in the old server's session
namespace, and live transactions use their existing rollback confirmation.
Pending saves block switching until they settle. Unsaved edits to remembered
queries require an explicit leave confirmation; a session shadow is not a
promise of recovery after another writer changes the remote revision. Open
table editing/import forms are also confirmed before navigation.
Server-owned jobs continue on the server that owns them.
Active browser-owned work is confirmed separately because navigating away
stops its uploads and other client-side processing.

`GET /api/v1/utils/server-info` is public and returns a fixed product identifier
and the supported client API generation. Checking another server uses an
independent client with no credentials, a timeout and runtime response validation.
An incompatible or unreachable server is explained before login or switching.
CORS remains an explicit server configuration; the browser's transport rules
are not bypassed by a proxy.
Each backend's `FRONTEND_HOST` must allow this frontend's origin. An HTTPS
frontend accepts HTTPS backends; a deployment under a path prefix must proxy
both `/api/v1` HTTP routes and `/api/v1/ws` under that prefix. The configured
default comes from `VITE_API_URL`, falling back to the frontend origin.

## Legacy evidence

`myquasar/src/myapp/components/ServersList/` and
`stores/LocalSettingsStore.ts` saved server addresses, ports and TLS flags, then
reloaded on switching. The new implementation retains the workflow without
sharing the selected server across browser tabs or reusing a single auth token.

## Validation

Write tests for URL normalization, legacy ownership, independent sessions and
storage, anonymous compatibility probing, shared-link routing, leave guards
and the visible server-selection workflow. Tests and checks remain deferred at
the user's request.
