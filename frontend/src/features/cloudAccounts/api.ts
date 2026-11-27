import { useMutation, useQuery, useQueryClient } from "@tanstack/vue-query"
import { unref } from "vue"
import type { MaybeRef } from "vue"

import { CloudAccountsService } from "@/client"
import type { CloudAccountCreate, CloudAccountUpdate } from "@/client"

/**
 * A person's cloud accounts (D451). Server state, so vue-query (D6): which
 * connections use an account is the server's answer.
 */
export const cloudAccountsKey = ["cloud-accounts"] as const

/** Asked only where something has a place for one, when `enabled` says so. */
export function useCloudAccounts(enabled: MaybeRef<boolean> = true) {
  return useQuery({
    queryKey: cloudAccountsKey,
    queryFn: async () => (await CloudAccountsService.accountsReadCloudAccounts()).data,
    enabled,
  })
}

/** The kinds and the ways each signs in that this person may choose (D452). */
export function useCloudAccountSchema(enabled: MaybeRef<boolean> = true) {
  return useQuery({
    queryKey: [...cloudAccountsKey, "schema"],
    queryFn: async () => (await CloudAccountsService.accountsReadCloudAccountSchema()).data,
    enabled,
    staleTime: Infinity,
  })
}

/**
 * Amazon's regions for a field that names one (D461): the account's, or
 * every published one without it. Kept an hour, as regions change by the year.
 */
export function useAwsRegions(account: MaybeRef<string | undefined>, enabled: MaybeRef<boolean> = true) {
  return useQuery({
    queryKey: [...cloudAccountsKey, "regions", account],
    queryFn: async () =>
      (await CloudAccountsService.accountsReadCloudRegions({ query: { account: unref(account) ?? null } })).data,
    enabled,
    staleTime: 60 * 60 * 1000,
  })
}

/** Every change to an account is answered by re-reading the list it is in. */
function useAccountMutation<T, R>(run: (input: T) => Promise<R>) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: run,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: cloudAccountsKey, exact: true })
    },
  })
}

export function useCreateCloudAccount() {
  return useAccountMutation(
    async (body: CloudAccountCreate) =>
      (await CloudAccountsService.accountsCreateCloudAccount({ body })).data
  )
}

export function useUpdateCloudAccount() {
  return useAccountMutation(
    async (asked: { id: string; body: CloudAccountUpdate }) =>
      (
        await CloudAccountsService.accountsUpdateCloudAccount({
          path: { account_id: asked.id },
          body: asked.body,
        })
      ).data
  )
}

export function useDeleteCloudAccount() {
  return useAccountMutation(
    async (id: string) =>
      (await CloudAccountsService.accountsDeleteCloudAccount({ path: { account_id: id } })).data
  )
}

/** A test changes nothing, so nothing is re-read after it. */
export function useTestCloudAccount() {
  return useMutation({
    mutationFn: async (id: string) =>
      (await CloudAccountsService.accountsTestCloudAccount({ path: { account_id: id } })).data,
  })
}
