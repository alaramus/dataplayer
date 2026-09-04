import { useMutation, useQuery, useQueryClient } from "@tanstack/vue-query"
import { computed } from "vue"
import type { Ref } from "vue"

import { BackupsService, JobsService, ServicesService } from "@/client"
import type { RestoreRequest, ServiceRequestWritable } from "@/client"
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
    mutationFn: async (body: ServiceRequestWritable) =>
      (await ServicesService.requestService({ body })).data,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: servicesKey })
    },
  })
}

/**
 * Take a service away, and its connection when that was asked for too.
 *
 * Two answers rather than one, because they are two things: the container and
 * its data are this command's, and the connection it made may be shared or
 * named in somebody's query history (D84).
 */
export function useDeleteService() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (asked: { serviceId: string; deleteConnector: boolean }) =>
      (
        await ServicesService.deleteService({
          path: { service_id: asked.serviceId },
          query: { delete_connector: asked.deleteConnector },
        })
      ).data,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: servicesKey })
      await queryClient.invalidateQueries({ queryKey: connectorsKey })
    },
  })
}

export function useServiceLogs(serviceId: Ref<string | null>) {
  return useQuery({
    queryKey: computed(() => ["service-logs", serviceId.value] as const),
    queryFn: async () =>
      (
        await ServicesService.readServiceLogs({
          path: { service_id: serviceId.value ?? "" },
        })
      ).data,
    enabled: computed(() => serviceId.value !== null),
    // What a container printed a second ago is what it printed: this is read
    // when something went wrong, not watched.
    staleTime: 0,
  })
}

export function useRetryService() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (serviceId: string) =>
      (
        await ServicesService.retryService({
          path: { service_id: serviceId },
        })
      ).data,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: servicesKey })
    },
  })
}

export function useCancelJob() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (jobId: string) =>
      (await JobsService.cancelJob({ path: { job_id: jobId } })).data,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: servicesKey })
    },
  })
}

/**
 * Where one service listens, and under what names.
 *
 * An ordinary read, which it is because the password is not in it: nothing is
 * stamped, nothing is rationed, and asking again is asking again. Kept a
 * short while because an address changes only when the service is started
 * afresh.
 */
export function useServiceCredentials(
  serviceId: Ref<string | null>,
  enabled: Ref<boolean>
) {
  return useQuery({
    queryKey: computed(() => ["service-credentials", serviceId.value] as const),
    queryFn: async () =>
      (
        await ServicesService.readServiceCredentials({
          path: { service_id: serviceId.value ?? "" },
        })
      ).data,
    enabled: computed(() => serviceId.value !== null && enabled.value),
    staleTime: 30_000,
  })
}

/**
 * The same, with the password, asked for exactly once.
 *
 * `staleTime: Infinity` and no retry, because this is not a read: the server
 * stamps the row as handed over and refuses the second ask. A refetch would
 * turn the one answer into a refusal on the screen of the person who was
 * being told it — which is why the cached answer has to outlive the window
 * being closed and opened again in the same session.
 */
export function useRevealedCredentials(
  serviceId: Ref<string | null>,
  enabled: Ref<boolean>
) {
  const queryClient = useQueryClient()
  return useQuery({
    queryKey: computed(() => ["service-secret", serviceId.value] as const),
    queryFn: async () => {
      const answer = (
        await ServicesService.revealServiceCredentials({
          path: { service_id: serviceId.value ?? "" },
        })
      ).data
      // The row now says it has been handed over, which is what a later
      // request for it will be refused by.
      await queryClient.invalidateQueries({ queryKey: servicesKey })
      return answer
    },
    enabled: computed(() => serviceId.value !== null && enabled.value),
    staleTime: Infinity,
    gcTime: Infinity,
    retry: false,
  })
}

export const backupsKey = ["backups"] as const
export const backupOfferKey = ["backup-offer"] as const

export function useBackupOffer() {
  return useQuery({
    queryKey: backupOfferKey,
    queryFn: async () => (await BackupsService.readBackupOffer()).data,
    // About the machine rather than about a source, and a daemon can go away
    // while this page is open.
    staleTime: 30_000,
  })
}

export function useBackups() {
  return useQuery({
    queryKey: backupsKey,
    queryFn: async () => (await BackupsService.readBackups()).data,
  })
}

export function useBackUp() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (connectorId: string) =>
      (await BackupsService.backUp({ body: { connector_id: connectorId } })).data,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: backupsKey })
    },
  })
}

export function useDeleteBackup() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (filename: string) =>
      (await BackupsService.deleteBackup({ path: { filename } })).data,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: backupsKey })
    },
  })
}

export function useRestore() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (body: RestoreRequest) =>
      (await BackupsService.restore({ body })).data,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: backupsKey })
    },
  })
}
