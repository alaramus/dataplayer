import { describe, expect, it } from "vitest"

import type { ConnectorPublic } from "@/client"
import type { FieldSpec } from "@/shared/SchemaForm/jsonSchema"

import { withTunnelChoices } from "./tunnels"

const WORDS = { directly: "Directly", someone_elses: "The owner's SSH connection" }

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

const tunnel: FieldSpec = {
  name: "ssh_tunnel",
  label: "SSH tunnel",
  kind: "text",
  required: false,
  defaultValue: "",
  purpose: "ssh-connection",
  group: "general",
}
const host: FieldSpec = { name: "host", label: "Host", kind: "text", required: true, group: "general" }

describe("withTunnelChoices", () => {
  it("offers directly first, then the person's own SSH connections", () => {
    const [field] = withTunnelChoices(
      [tunnel],
      [
        connection({ id: "s1", name: "bastion" }),
        connection({ id: "s2", name: "shared with me", access: "read" }),
        connection({ id: "p1", name: "warehouse", adapter_type: "postgres" }),
      ],
      {},
      WORDS
    )

    expect(field?.kind).toBe("select")
    expect(field?.choices).toEqual([
      { value: "", label: "Directly" },
      { value: "s1", label: "bastion" },
    ])
  })

  it("keeps a tunnel this person cannot see, under a name of its own", () => {
    const [field] = withTunnelChoices([tunnel], [], { ssh_tunnel: "theirs" }, WORDS)

    expect(field?.choices).toContainEqual({ value: "theirs", label: "The owner's SSH connection" })
  })

  it("leaves every other field as it is", () => {
    expect(withTunnelChoices([host], [connection({})], {}, WORDS)).toEqual([host])
  })
})
