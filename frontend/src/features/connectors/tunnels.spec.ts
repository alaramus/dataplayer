import { describe, expect, it } from "vitest"

import type { AdapterTypeInfo, ConnectorPublic, TunnelTarget } from "@/client"
import type { FieldSpec } from "@/shared/SchemaForm/jsonSchema"

import { carriersOf, portFor, withTunnelChoices, withTunnelHost } from "./tunnels"
import type { Carrier } from "./tunnels"

const WORDS = {
  directly: "Directly",
  someone_elses: "The owner's connection",
  asSeenBy: (name: string) => `As ${name} sees it`,
  oneOf: (name: string) => `Where ${name} leads`,
}

const CARRIERS: Record<string, Carrier> = {
  ssh: { title: "SSH", port: true, socket: true, lists: false },
  kubernetes: { title: "Kubernetes", port: true, socket: false, lists: true },
}

function connection(overrides: Partial<ConnectorPublic>): ConnectorPublic {
  return {
    id: "c1",
    name: "bastion",
    adapter_type: "ssh",
    config: {},
    enabled: true,
    access: "own",
    execution_policy: "confirm_writes",
    ...overrides,
  } as ConnectorPublic
}

const host: FieldSpec = { name: "host", label: "Host", kind: "text", required: true, group: "general", row: "address" }
const port: FieldSpec = { name: "port", label: "Port", kind: "number", required: true, group: "general", row: "address" }
const tunnel: FieldSpec = {
  name: "ssh_tunnel",
  label: "Reach through",
  kind: "text",
  required: false,
  defaultValue: "",
  purpose: "ssh-connection",
  group: "general",
  tunnel: { carries: "port", host: "host", port: "port" },
}
const socket: FieldSpec = {
  ...tunnel,
  name: "ssh_connection",
  required: true,
  tunnel: { carries: "socket" },
}
const bastion = connection({ id: "s1", name: "bastion" })
const cluster = connection({ id: "k1", name: "k3s", adapter_type: "kubernetes" })
const TARGETS: TunnelTarget[] = [
  { host: "pg.data.svc", label: "Service pg in data · PostgreSQL", ports: [5433, 9187] },
  { host: "pg-0.data.pod", label: "Pod pg-0 in data", ports: [5432] },
]

describe("carriersOf", () => {
  it("reads what each type carries off its capabilities", () => {
    const types = [
      { name: "ssh", title: "SSH", capabilities: [{ code: "tunnel" }, { code: "socket_tunnel" }] },
      { name: "kubernetes", title: "Kubernetes", capabilities: [{ code: "tunnel" }, { code: "tunnel_targets" }] },
      { name: "postgres", title: "PostgreSQL", capabilities: [{ code: "search" }] },
    ] as unknown as AdapterTypeInfo[]

    expect(carriersOf(types)).toEqual(CARRIERS)
  })
})

describe("withTunnelChoices", () => {
  it("offers directly first, then the person's own carriers, each with its type", () => {
    const [field] = withTunnelChoices(
      [tunnel],
      [
        bastion,
        cluster,
        connection({ id: "s2", name: "shared with me", access: "read" }),
        connection({ id: "p1", name: "warehouse", adapter_type: "postgres" }),
      ],
      {},
      WORDS,
      CARRIERS
    )

    expect(field?.kind).toBe("select")
    expect(field?.choices).toEqual([
      { value: "", label: "Directly" },
      { value: "s1", label: "SSH · bastion" },
      { value: "k1", label: "Kubernetes · k3s" },
    ])
  })

  it("offers a socket field only what reaches a socket, and no directly when it is required", () => {
    const [field] = withTunnelChoices([socket], [bastion, cluster], {}, WORDS, CARRIERS)

    expect(field?.choices).toEqual([{ value: "s1", label: "SSH · bastion" }])
  })

  it("puts the field before the row of the host it governs", () => {
    const fields = withTunnelChoices([host, port, tunnel], [], {}, WORDS, CARRIERS)

    expect(fields.map((field) => field.name)).toEqual(["ssh_tunnel", "host", "port"])
  })

  it("keeps a tunnel this person cannot see, under a name of its own", () => {
    const [field] = withTunnelChoices([tunnel], [], { ssh_tunnel: "theirs" }, WORDS, CARRIERS)

    expect(field?.choices).toContainEqual({ value: "theirs", label: "The owner's connection" })
  })

  it("leaves every other field as it is", () => {
    expect(withTunnelChoices([host], [bastion], {}, WORDS, CARRIERS)).toEqual([host])
  })
})

describe("withTunnelHost", () => {
  it("says whose view the host is through a carrier that lists nothing", () => {
    const fields = withTunnelHost([tunnel, host], { ssh_tunnel: "s1" }, [bastion], undefined, WORDS)

    expect(fields[1]?.description).toBe("As bastion sees it")
    expect(fields[1]?.kind).toBe("text")
  })

  it("offers the places a cluster leads to, keeping a host it does not list", () => {
    const fields = withTunnelHost(
      [tunnel, host],
      { ssh_tunnel: "k1", host: "typed.data.svc" },
      [cluster],
      TARGETS,
      WORDS
    )

    expect(fields[1]?.kind).toBe("select")
    expect(fields[1]?.choices?.map((choice) => choice.value)).toEqual([
      "pg.data.svc",
      "pg-0.data.pod",
      "typed.data.svc",
    ])
  })

  it("leaves the host alone when the server is dialled directly", () => {
    expect(withTunnelHost([tunnel, host], { ssh_tunnel: "" }, [bastion], TARGETS, WORDS)).toEqual([tunnel, host])
  })
})

describe("portFor", () => {
  it("brings a chosen place's first port, unless the port is already one of its own", () => {
    expect(portFor(TARGETS, "pg.data.svc", 5432)).toBe(5433)
    expect(portFor(TARGETS, "pg.data.svc", 9187)).toBeNull()
    expect(portFor(TARGETS, "elsewhere", 1)).toBeNull()
    expect(portFor(undefined, "pg.data.svc", 1)).toBeNull()
  })
})
