import type { ConnectorPublic } from "@/client"
import type { FieldSpec } from "@/shared/SchemaForm/jsonSchema"

export interface TunnelWords {
  /** The empty choice: the server is dialled at its own address. */
  directly: string
  /** A tunnel this person cannot see: the connection was shared with them. */
  someone_elses: string
}

/**
 * A field that names the SSH connection a database goes through (D282),
 * offered as a choice of the person's own SSH connections.
 *
 * The schema says what the field is for (`x-ui-purpose: ssh-connection`);
 * only this screen knows which connections there are. One the form holds and
 * the list does not — a connection shared by its owner — stays in the choice
 * under a name of its own, so opening the form does not change what it says.
 */
export function withTunnelChoices(
  fields: FieldSpec[],
  connections: readonly ConnectorPublic[],
  values: Record<string, unknown>,
  words: TunnelWords
): FieldSpec[] {
  const own = connections.filter(
    (connection) => connection.adapter_type === "ssh" && connection.access === "own"
  )
  return fields.map((field) => {
    if (field.purpose !== "ssh-connection") return field
    const held = values[field.name]
    const unseen =
      typeof held === "string" && held !== "" && !own.some((one) => one.id === held)
        ? [{ value: held, label: words.someone_elses }]
        : []
    return {
      ...field,
      kind: "select",
      choices: [
        { value: "", label: words.directly },
        ...own.map((connection) => ({ value: connection.id, label: connection.name })),
        ...unseen,
      ],
    }
  })
}
