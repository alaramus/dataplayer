import { useMutation, useQuery, useQueryClient } from "@tanstack/vue-query"

import { ServicesService } from "@/client"
import type { ServiceRequest } from "@/client"
import { connectorsKey } from "@/features/connectors/api"

/**
 * Services this server runs, and what may be asked of it.
 *
 * Server state, so it lives in vue-query like every other: the socket tells us
 * when a job moved, and what a job moved *to* is read back from here rather
 * than assembled from events.
 */
export const serviceTemplatesKey = ["service-templates"] as const
export const servicesKey = ["services"] as const

export function useServiceTemplates() {
  return useQuery({
    queryKey: serviceTemplatesKey,
    queryFn: async () => (await ServicesService.readServiceTemplates()).data,
    // Not infinite, unlike the adapter types: whether one can be started is
    // about a daemon, and a daemon can go away while this page is open.
    staleTime: 30_000,
  })
}

export function useServices() {
  return useQuery({
    queryKey: servicesKey,
    queryFn: async () => (await ServicesService.readServices()).data,
  })
}

export function useRequestService() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (body: ServiceRequest) =>
      (await ServicesService.requestService({ body })).data,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: servicesKey })
    },
  })
}

export function useDeleteService() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (serviceId: string) =>
      (
        await ServicesService.deleteService({
          path: { service_id: serviceId },
        })
      ).data,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: servicesKey })
      await queryClient.invalidateQueries({ queryKey: connectorsKey })
    },
  })
}
