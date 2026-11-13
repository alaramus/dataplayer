import type { McpServerCreateWritable, McpServerPublic, McpServerUpdateWritable } from "@/client"

/** One header row of the server's window. A value left empty on a header the
    server already has keeps the value it had: values are never sent back. */
export interface HeaderRow {
  name: string
  value: string
}

/** What the window holds. An empty token keeps the one that is set. */
export interface ServerForm {
  name: string
  url: string
  token: string
  clearToken: boolean
  headers: HeaderRow[]
  enabled: boolean
}

export function formOf(server: McpServerPublic | null): ServerForm {
  return {
    name: server?.name ?? "",
    url: server?.url ?? "",
    token: "",
    clearToken: false,
    headers: (server?.header_names ?? []).map((name) => ({ name, value: "" })),
    enabled: server?.enabled ?? true,
  }
}

function namedRows(rows: HeaderRow[]): HeaderRow[] {
  return rows
    .map((row) => ({ name: row.name.trim(), value: row.value }))
    .filter((row) => row.name !== "")
}

export function createBody(form: ServerForm): McpServerCreateWritable {
  return {
    name: form.name.trim(),
    url: form.url.trim(),
    token: form.token === "" ? null : form.token,
    headers: Object.fromEntries(namedRows(form.headers).map((row) => [row.name, row.value])),
    enabled: form.enabled,
  }
}

export function updateBody(form: ServerForm, server: McpServerPublic): McpServerUpdateWritable {
  const rows = namedRows(form.headers)
  const sameHeaders =
    rows.length === server.header_names.length &&
    rows.every((row) => row.value === "" && server.header_names.includes(row.name))
  return {
    name: form.name.trim(),
    url: form.url.trim(),
    token: form.token === "" ? null : form.token,
    clear_token: form.token === "" && form.clearToken,
    headers: sameHeaders
      ? null
      : Object.fromEntries(rows.map((row) => [row.name, row.value === "" ? null : row.value])),
    enabled: form.enabled,
  }
}
