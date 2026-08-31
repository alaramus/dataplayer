import { useMutation, useQuery, useQueryClient } from "@tanstack/vue-query"
import { computed } from "vue"
import type { Ref } from "vue"

import { ConnectorsService } from "@/client"
import type {
  ContentRequest,
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
