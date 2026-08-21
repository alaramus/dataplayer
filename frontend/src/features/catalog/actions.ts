import type { ActionInfo } from "@/client"
import { schemaToFields } from "@/shared/SchemaForm/jsonSchema"
import type { FieldSpec, JsonSchema } from "@/shared/SchemaForm/jsonSchema"

/**
 * One action, ready to be offered as a button.
 *
 * Nothing here is keyed by the name of an action: the label, whether it asks
 * for confirmation and what its form contains all come from the answer of the
 * server. A source that gains an action tomorrow needs no change on this side.
 */
export interface ActionCommand {
  name: string
  label: string
  destructive: boolean
  takesFile: boolean
  fields: FieldSpec[]
}

export function toCommands(actions: ActionInfo[]): ActionCommand[] {
  return actions.map((action) => ({
    name: action.name,
    label: action.title,
    destructive: action.destructive,
    takesFile: action.takes_file,
    fields: schemaToFields(action.params_schema as unknown as JsonSchema),
  }))
}
