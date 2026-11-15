/** How a mailbox's folders are listed in its tab (D368). */
import type { MailFolder } from "@/client"

export interface ShownFolder {
  id: string
  /** The role's word where the server said what the folder is for. */
  label: string
  /** How far under another folder it sits. */
  depth: number
  unseen: number
  selectable: boolean
  role: MailFolder["role"]
}

/**
 * The folders in the server's order, which already puts the inbox and the
 * other roles first; a nested folder by its last name, indented.
 */
export function shownFolders(
  folders: readonly MailFolder[],
  roleWord: (role: NonNullable<MailFolder["role"]>) => string
): ShownFolder[] {
  return folders.map((folder) => {
    const parts =
      folder.delimiter && folder.role === null
        ? folder.name.split(folder.delimiter)
        : [folder.name]
    return {
      id: folder.id,
      label: folder.role === null ? (parts[parts.length - 1] ?? folder.name) : roleWord(folder.role),
      depth: parts.length - 1,
      unseen: folder.unseen ?? 0,
      selectable: folder.selectable,
      role: folder.role,
    }
  })
}

/** Where a mailbox opens: its inbox, else the first folder that opens. */
export function firstFolder(folders: readonly MailFolder[]): string | null {
  return (
    folders.find((folder) => folder.role === "inbox")?.id ??
    folders.find((folder) => folder.selectable)?.id ??
    null
  )
}
