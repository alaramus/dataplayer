import { useMutation, useQuery, useQueryClient } from "@tanstack/vue-query"
import { computed } from "vue"
import type { Ref } from "vue"

import { ConnectorsService } from "@/client"
import type {
  ContentRequest,
  DeleteRowsRequest,
  DocumentChangeRequest,
  DocumentInsertRequest,
  DocumentsRequest,
  EditorContentRequest,
  UpdateContentRequest,
} from "@/client"

export const contentKey = (connectorId: string, request: ContentRequest) =>
  ["content", connectorId, request] as const

export function useContent(connectorId: Ref<string>, request: Readonly<Ref<ContentRequest>>) {
  return useQuery({
    queryKey: computed(() => contentKey(connectorId.value, request.value)),
    queryFn: async ({ signal }) =>
      (
        await ConnectorsService.readContent({
          path: { connector_id: connectorId.value },
          body: request.value,
          signal,
        })
      ).data,
  })
}

/** An imperative content read that still shares vue-query's server-state cache. */
export function useContentLoader() {
  const queryClient = useQueryClient()
  return async function loadContent(connectorId: string, request: ContentRequest) {
    return queryClient.fetchQuery({
      queryKey: contentKey(connectorId, request),
      queryFn: async () =>
        (
          await ConnectorsService.readContent({
            path: { connector_id: connectorId },
            body: request,
          })
        ).data,
      // Preview tickets live for one minute. Leave enough margin that an
      // image resolved from Markdown is not handed an almost-expired URL.
      staleTime: 45_000,
    })
  }
}

export const editorContentKey = (connectorId: string, request: EditorContentRequest) =>
  ["editor-content", connectorId, request] as const

export function useEditorContent(
  connectorId: Ref<string>,
  request: Readonly<Ref<EditorContentRequest>>
) {
  return useQuery({
    queryKey: computed(() => editorContentKey(connectorId.value, request.value)),
    queryFn: async ({ signal }) =>
      (
        await ConnectorsService.readEditorContent({
          path: { connector_id: connectorId.value },
          body: request.value,
          signal,
        })
      ).data,
  })
}

export function useUpdateContent(connectorId: Ref<string>) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (body: UpdateContentRequest) =>
      (
        await ConnectorsService.updateContent({
          path: { connector_id: connectorId.value },
          body,
        })
      ).data,
    // A saved file changes what its table projection would read, and what any
    // other tab on the same file still shows.
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["editor-content", connectorId.value] }),
        queryClient.invalidateQueries({ queryKey: ["content", connectorId.value] }),
        queryClient.invalidateQueries({ queryKey: ["rows", connectorId.value] }),
      ])
    },
  })
}

export const documentsKey = (connectorId: string, request: DocumentsRequest) =>
  ["documents", connectorId, request] as const

/** A page of whole documents, under the grid's own filters and order (D295). */
export function useDocuments(connectorId: Ref<string>, request: Readonly<Ref<DocumentsRequest>>) {
  return useQuery({
    queryKey: computed(() => documentsKey(connectorId.value, request.value)),
    queryFn: async ({ signal }) =>
      (
        await ConnectorsService.readDocuments({
          path: { connector_id: connectorId.value },
          body: request.value,
          signal,
        })
      ).data,
  })
}

export function useChangeDocument(connectorId: Ref<string>) {
  return useDocumentsMutation(connectorId, async (id, body: DocumentChangeRequest) =>
    (await ConnectorsService.changeDocument({ path: { connector_id: id }, body })).data
  )
}

/** What changes the documents changes the grid over the same collection too. */
function useDocumentsMutation<Body, Answer>(
  connectorId: Ref<string>,
  run: (connectorId: string, body: Body) => Promise<Answer>
) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: Body) => run(connectorId.value, body),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["documents", connectorId.value] }),
        queryClient.invalidateQueries({ queryKey: ["rows", connectorId.value] }),
      ])
    },
  })
}

/** A new document written as text, a clone included (D459). */
export function useInsertDocument(connectorId: Ref<string>) {
  return useDocumentsMutation(connectorId, async (id, body: DocumentInsertRequest) =>
    (await ConnectorsService.insertDocument({ path: { connector_id: id }, body })).data
  )
}

/** Documents deleted by their handles, as the grid deletes rows (D287). */
export function useDeleteDocuments(connectorId: Ref<string>) {
  return useDocumentsMutation(connectorId, async (id, body: DeleteRowsRequest) =>
    (await ConnectorsService.deleteRows({ path: { connector_id: id }, body })).data
  )
}
