import type { AdapterTypeInfo, ConnectorPublic, TunnelTarget } from "@/client"
import type { FieldSpec } from "@/shared/SchemaForm/jsonSchema"

export interface TunnelWords {
  /** The empty choice: the server is dialled at its own address. */
  directly: string
  /** A tunnel this person cannot see: the connection was shared with them. */
  someone_elses: string
  /** Under the host, once a connection that lists nothing is chosen. */
  asSeenBy: (name: string) => string
  /** Under the host, once a connection that lists where it leads is chosen. */
  oneOf: (name: string) => string
}

/** A type of connection that carries others, as the server describes it. */
export interface Carrier {
  title: string
  port: boolean
  socket: boolean
  /** Whether it says where it leads (`tunnel_targets`), so the host is chosen. */
  lists: boolean
}

/**
 * Which types carry what, from their capabilities (D282, D405, D474): the
 * server's word, not a list of type names here.
 */
export function carriersOf(types: readonly AdapterTypeInfo[]): Record<string, Carrier> {
  const found: Record<string, Carrier> = {}
  for (const type of types) {
    const codes = new Set(type.capabilities.map((one) => one.code))
    if (!codes.has("tunnel") && !codes.has("socket_tunnel")) continue
    found[type.name] = {
      title: type.title,
      port: codes.has("tunnel"),
      socket: codes.has("socket_tunnel"),
      lists: codes.has("tunnel_targets"),
    }
  }
  return found
}

function isTunnel(field: FieldSpec): boolean {
  return field.purpose === "ssh-connection"
}

/**
 * A field that names the connection a database goes through (D282, D479),
 * offered as a choice of the person's own connections that carry what it
 * needs — a port, or a socket for a Docker daemon (D405) — each labelled
 * with its type, and "directly" first unless the field is required. It is
 * moved before the host it governs, since it changes what that host means.
 *
 * One the form holds and the list does not — a connection shared by its
 * owner — stays in the choice under a name of its own, so opening the form
 * does not change what it says.
 */
export function withTunnelChoices(
  fields: FieldSpec[],
  connections: readonly ConnectorPublic[],
  values: Record<string, unknown>,
  words: TunnelWords,
  carriers: Readonly<Record<string, Carrier>>
): FieldSpec[] {
  const chosen = fields.map((field) => {
    if (!isTunnel(field)) return field
    const carries = field.tunnel?.carries ?? "port"
    const own = connections.filter(
      (connection) => connection.access === "own" && carriers[connection.adapter_type]?.[carries] === true
    )
    const held = values[field.name]
    const unseen =
      typeof held === "string" && held !== "" && !own.some((one) => one.id === held)
        ? [{ value: held, label: words.someone_elses }]
        : []
    const directly = field.required ? [] : [{ value: "", label: words.directly }]
    return {
      ...field,
      kind: "select" as const,
      choices: [
        ...directly,
        ...own.map((connection) => ({
          value: connection.id,
          label: `${carriers[connection.adapter_type]?.title ?? connection.adapter_type} · ${connection.name}`,
        })),
        ...unseen,
      ],
    }
  })
  return beforeItsHost(chosen)
}

/** The tunnel field placed just before the host it governs, in its row's place. */
function beforeItsHost(fields: FieldSpec[]): FieldSpec[] {
  const tunnel = fields.find((field) => isTunnel(field) && field.tunnel?.host !== undefined)
  if (tunnel === undefined) return fields
  const rest = fields.filter((field) => field !== tunnel)
  const host = rest.findIndex((field) => field.name === tunnel.tunnel?.host)
  if (host < 0) return fields
  // The host's row may begin before it; the tunnel goes before the row.
  const row = rest[host]?.row
  const start = row === undefined ? host : rest.findIndex((field) => field.row === row)
  return [...rest.slice(0, start), { ...tunnel, row: undefined }, ...rest.slice(start)]
}

/** The connection the form's tunnel field names, if any. */
export function chosenTunnel(
  fields: readonly FieldSpec[],
  values: Record<string, unknown>,
  connections: readonly ConnectorPublic[]
): { field: FieldSpec; connection: ConnectorPublic } | null {
  const field = fields.find((one) => isTunnel(one) && one.tunnel?.host !== undefined)
  const held = field === undefined ? undefined : values[field.name]
  const connection = connections.find((one) => one.id === held)
  return field === undefined || connection === undefined ? null : { field, connection }
}

/**
 * The host as the chosen tunnel sees it (D479): a choice of the places a
 * connection that lists them leads to, or a word under the host saying whose
 * view it is. A host the list does not hold stays, typed as it was.
 */
export function withTunnelHost(
  fields: FieldSpec[],
  values: Record<string, unknown>,
  connections: readonly ConnectorPublic[],
  targets: readonly TunnelTarget[] | undefined,
  words: TunnelWords
): FieldSpec[] {
  const chosen = chosenTunnel(fields, values, connections)
  if (chosen === null) return fields
  const hostName = chosen.field.tunnel?.host
  const name = chosen.connection.name
  return fields.map((field) => {
    if (field.name !== hostName) return field
    if (targets === undefined) return { ...field, description: words.asSeenBy(name) }
    const held = values[field.name]
    const unseen =
      typeof held === "string" && held !== "" && !targets.some((one) => one.host === held)
        ? [{ value: held, label: held }]
        : []
    return {
      ...field,
      kind: "select" as const,
      description: words.oneOf(name),
      choices: [...targets.map((one) => ({ value: one.host, label: one.label })), ...unseen],
    }
  })
}

/**
 * The port to put beside a host just chosen from a tunnel's places: its first,
 * unless the port already holds one of them.
 */
export function portFor(
  targets: readonly TunnelTarget[] | undefined,
  host: unknown,
  port: unknown
): number | null {
  const ports = targets?.find((one) => one.host === host)?.ports ?? []
  if (ports.length === 0) return null
  const current = typeof port === "number" ? port : Number(port)
  return ports.includes(current) ? null : (ports[0] ?? null)
}
