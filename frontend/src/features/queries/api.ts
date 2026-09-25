import { useMutation, useQuery, useQueryClient } from "@tanstack/vue-query"
import { computed, toValue } from "vue"
import type { MaybeRefOrGetter } from "vue"

import { QueriesService } from "@/client"
import type { QueryDocumentCreate, QueryDocumentUpdate } from "@/client"

/**
 * Query documents: the library, and one console.
 *
 * Server state, so vue-query and not a store (D6). A document is the one thing
 * here a person edits continuously, so its cache is written from what the
 * server answered rather than from what was typed — the revision only the
 * server issues is the whole point of the conflict rules (D63).
 */

export interface LibraryFilters {
  connectorId: string | null
  search: string
}

export const libraryKey = (filters: LibraryFilters) =>
  ["queries", "documents", filters.connectorId ?? "any", filters.search] as const

export const documentKey = (documentId: string) =>
  ["queries", "documents", documentId] as const

export function useQueryDocuments(filters: MaybeRefOrGetter<LibraryFilters>) {
  const current = computed(() => toValue(filters))
  return useQuery({
    queryKey: computed(() => libraryKey(current.value)),
    queryFn: async () =>
      (
        await QueriesService.listDocuments({
          query: {
            ...(current.value.connectorId === null
              ? {}
              : { connector_id: current.value.connectorId }),
            search: current.value.search,
          },
        })
      ).data,
  })
}

export function useQueryDocument(documentId: MaybeRefOrGetter<string | null>) {
  const id = computed(() => toValue(documentId))
  return useQuery({
    queryKey: computed(() => documentKey(id.value ?? "none")),
    queryFn: async () =>
      (await QueriesService.readDocument({ path: { document_id: id.value as string } })).data,
    enabled: computed(() => id.value !== null),
    // The editor is the only writer of its own document, and a refetch while
    // somebody types would replace their text with an older answer.
    refetchOnWindowFocus: false,
  })
}

/** Everything that changes the library, so one place says what to re-read. */
function useLibraryInvalidation() {
  const queryClient = useQueryClient()
  return async () => {
    await queryClient.invalidateQueries({ queryKey: ["queries", "documents"] })
  }
}

export function useCreateQueryDocument() {
  const invalidate = useLibraryInvalidation()
  return useMutation({
    mutationFn: async (body: QueryDocumentCreate) =>
      (await QueriesService.createDocument({ body })).data,
    onSuccess: invalidate,
  })
}

export function useSaveQueryDocument() {
  const queryClient = useQueryClient()
  const invalidate = useLibraryInvalidation()
  return useMutation({
    mutationFn: async (change: { documentId: string; body: QueryDocumentUpdate }) =>
      (
        await QueriesService.updateDocument({
          path: { document_id: change.documentId },
          body: change.body,
        })
      ).data,
    onSuccess: async (saved) => {
      // The answer carries the new revision, so the next save has its base
      // without a second round trip.
      queryClient.setQueryData(documentKey(saved.id), saved)
      await invalidate()
    },
  })
}

export function useDeleteQueryDocument() {
  const queryClient = useQueryClient()
  const invalidate = useLibraryInvalidation()
  return useMutation({
    mutationFn: async (documentId: string) =>
      (await QueriesService.deleteDocument({ path: { document_id: documentId } })).data,
    onSuccess: async (_removed, documentId) => {
      queryClient.removeQueries({ queryKey: documentKey(documentId) })
      await invalidate()
    },
  })
}
