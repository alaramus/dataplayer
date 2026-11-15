import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/vue-query"
import { computed } from "vue"
import type { Ref } from "vue"

import { MailService } from "@/client"
import type { MarkRequest, MessageSelection, MoveRequest } from "@/client"
import { filenameFromDisposition, saveBrowserDownload } from "@/shared/download"

import type { Draft } from "./letter"
import { outgoingOf } from "./letter"

export const PAGE_SIZE = 50

export interface MessageRef {
  folder: string
  uid: number
}

export const mailKey = (connectorId: string) => ["mail", connectorId] as const

export function useMailFolders(connectorId: Ref<string>) {
  return useQuery({
    queryKey: computed(() => [...mailKey(connectorId.value), "folders"] as const),
    queryFn: async () =>
      (await MailService.mailFolders({ path: { connector_id: connectorId.value } })).data,
    retry: false,
  })
}

export function useMailPage(
  connectorId: Ref<string>,
  folder: Ref<string | null>,
  offset: Ref<number>,
  search: Ref<string>
) {
  return useQuery({
    queryKey: computed(
      () =>
        [...mailKey(connectorId.value), "page", folder.value, offset.value, search.value] as const
    ),
    enabled: computed(() => folder.value !== null),
    queryFn: async () =>
      (
        await MailService.mailMessages({
          path: { connector_id: connectorId.value },
          query: {
            folder: folder.value ?? "INBOX",
            offset: offset.value,
            limit: PAGE_SIZE,
            ...(search.value.trim() ? { search: search.value.trim() } : {}),
          },
        })
      ).data,
    // The page stays drawn while the next one is read, rather than blinking.
    placeholderData: keepPreviousData,
    retry: false,
  })
}

export function useMailMessage(connectorId: Ref<string>, ref: Ref<MessageRef | null>) {
  const queryClient = useQueryClient()
  return useQuery({
    queryKey: computed(
      () => [...mailKey(connectorId.value), "message", ref.value?.folder, ref.value?.uid] as const
    ),
    enabled: computed(() => ref.value !== null),
    queryFn: async () => {
      const chosen = ref.value
      if (chosen === null) throw new Error("No message chosen")
      const message = (
        await MailService.mailMessage({
          path: { connector_id: connectorId.value },
          query: chosen,
        })
      ).data
      // Opening it marked it read on the server (D368): the counts and the
      // list are read again rather than patched.
      void queryClient.invalidateQueries({ queryKey: [...mailKey(connectorId.value), "folders"] })
      void queryClient.invalidateQueries({ queryKey: [...mailKey(connectorId.value), "page"] })
      return message
    },
    // A letter does not change once it is there.
    staleTime: Number.POSITIVE_INFINITY,
    retry: false,
  })
}

function useMailChange<T, R>(connectorId: Ref<string>, change: (body: T) => Promise<R>) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: change,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: [...mailKey(connectorId.value), "folders"] })
      void queryClient.invalidateQueries({ queryKey: [...mailKey(connectorId.value), "page"] })
    },
  })
}

export function useMarkMessages(connectorId: Ref<string>) {
  return useMailChange(connectorId, async (body: MarkRequest) => {
    await MailService.markMessages({ path: { connector_id: connectorId.value }, body })
  })
}

export function useDeleteMessages(connectorId: Ref<string>) {
  return useMailChange(
    connectorId,
    async (body: MessageSelection) =>
      (await MailService.deleteMessages({ path: { connector_id: connectorId.value }, body })).data
  )
}

export function useSendMessage(connectorId: Ref<string>) {
  return useMailChange(connectorId, async (request: { draft: Draft; files: File[] }) =>
    (
      await MailService.sendMessage({
        path: { connector_id: connectorId.value },
        body: { message: JSON.stringify(outgoingOf(request.draft)), files: request.files },
      })
    ).data
  )
}

/** Into Drafts, replacing the draft it was opened from (D375). */
export function useSaveDraft(connectorId: Ref<string>) {
  return useMailChange(connectorId, async (request: { draft: Draft; files: File[] }) =>
    (
      await MailService.saveDraft({
        path: { connector_id: connectorId.value },
        body: { message: JSON.stringify(outgoingOf(request.draft)), files: request.files },
      })
    ).data
  )
}

export function useMoveMessages(connectorId: Ref<string>) {
  return useMailChange(
    connectorId,
    async (body: MoveRequest) =>
      (await MailService.moveMessages({ path: { connector_id: connectorId.value }, body })).data
  )
}

/** One folder of the owner's storage, to attach a file from (D374). */
export function useMyFiles(connectorId: Ref<string>, path: Ref<string>, enabled: Ref<boolean>) {
  return useQuery({
    queryKey: computed(() => [...mailKey(connectorId.value), "my-files", path.value] as const),
    enabled,
    queryFn: async () =>
      (
        await MailService.myFiles({
          path: { connector_id: connectorId.value },
          query: { path: path.value },
        })
      ).data,
    retry: false,
  })
}

export function useDownloadAttachment(connectorId: Ref<string>) {
  return useMutation({
    mutationFn: async (request: MessageRef & { part: string; filename: string }) => {
      const response = await MailService.downloadAttachment({
        path: { connector_id: connectorId.value },
        query: { folder: request.folder, uid: request.uid, part: request.part },
        responseType: "blob",
      })
      const disposition = response.headers["content-disposition"] as string | undefined
      saveBrowserDownload(
        response.data as unknown as Blob,
        filenameFromDisposition(disposition, request.filename)
      )
    },
  })
}

export function useKeepAttachment(connectorId: Ref<string>) {
  return useMutation({
    mutationFn: async (request: MessageRef & { part: string }) =>
      (
        await MailService.keepAttachment({
          path: { connector_id: connectorId.value },
          body: request,
        })
      ).data,
  })
}
