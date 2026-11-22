import { toListNodes } from "@/features/catalog/nodes"
import { useNodePathLoader } from "@/features/catalog/api"
import { useWorkspaceActions } from "@/features/workspace/state"
import { messageOf } from "@/shared/api/errors"
import { t } from "@/shared/i18n"
import { useToast } from "@/shared/ui"

/**
 * Open a node a view links to, as the catalog would have opened it (D420).
 *
 * The id came from the source and is not taken apart (D21): the source's own
 * path to it says what the node is, so a level is shown in the catalog and a
 * node that opens is opened by its first representation.
 */
export function useOpenLinkedNode(connectorId: () => string) {
  const workspace = useWorkspaceActions()
  const loadPath = useNodePathLoader()
  const toast = useToast()
  return async function open(nodeId: string, label: string) {
    try {
      const path = await loadPath(connectorId(), nodeId)
      const last = path[path.length - 1]
      const node = last === undefined ? undefined : toListNodes([last])[0]
      if (node === undefined) throw new Error(label)
      const walked = node.role !== "leaf" || !node.readable
      await workspace.openIntent(
        {
          connectorId: connectorId(),
          nodeId,
          view: walked ? "catalog" : "preferred",
          title: node.label,
          describable: node.describable,
          representations: node.representations,
          ancestors: path.slice(0, -1).map((one) => ({ id: one.id, label: one.name })),
        },
        { float: false }
      )
    } catch (cause) {
      toast.error(messageOf(cause, t("content.view.open_failed", { name: label })))
    }
  }
}
