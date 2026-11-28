import type { CloudCluster } from "@/client"
import type { FieldSpec } from "@/shared/SchemaForm/jsonSchema"

/**
 * A field naming a managed Kubernetes cluster, offered as a choice of those
 * the form's account may see (D477). Left typed while there is no list — no
 * account chosen yet, or Google did not answer — and a cluster the form holds
 * and the list does not stays among the choices.
 */
export function withClusterChoices(
  fields: FieldSpec[],
  clusters: readonly CloudCluster[],
  values: Record<string, unknown>
): FieldSpec[] {
  if (clusters.length === 0) return fields
  return fields.map((field) => {
    if (field.purpose !== "gke-cluster") return field
    return { ...field, kind: "select", choices: clusterChoices(clusters, values[field.name]) }
  })
}

function clusterChoices(clusters: readonly CloudCluster[], held: unknown) {
  const unseen =
    typeof held === "string" && held !== "" && !clusters.some((one) => one.name === held)
      ? [{ value: held, label: held }]
      : []
  return [...clusters.map((one) => ({ value: one.name, label: one.title })), ...unseen]
}

/** The account a form's cluster list is asked of: the one its account field holds. */
export function clusterAccount(fields: FieldSpec[], values: Record<string, unknown>): string | undefined {
  if (!fields.some((one) => one.purpose === "gke-cluster")) return undefined
  const field = fields.find((one) => one.purpose === "cloud-account")
  const held = field === undefined ? undefined : values[field.name]
  return typeof held === "string" && held !== "" ? held : undefined
}
