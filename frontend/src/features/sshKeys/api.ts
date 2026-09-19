import { useMutation, useQuery, useQueryClient } from "@tanstack/vue-query"
import { computed, toValue } from "vue"
import type { ComputedRef, MaybeRef, MaybeRefOrGetter } from "vue"

import { ConnectorsService, SshKeysService } from "@/client"
import type {
  ServerKeyRequest,
  SshKeyGenerateWritable,
  SshKeyImportWritable,
  SshKeyPublic,
  SshKeyUnlockWritable,
} from "@/client"
import { keyUsedBy } from "@/features/sshKeys/keys"

/**
 * A person's SSH keys (D146). Server state, so vue-query rather than Pinia
 * (D6): whether a key is unlocked is the server's answer, and a key unlocked
 * in one tab is unlocked in every tab of that person.
 */
export const sshKeysKey = ["ssh-keys"] as const

/** Asked only where a form has somewhere to put one, when `enabled` says so. */
export function useSshKeys(enabled: MaybeRef<boolean> = true) {
  return useQuery({
    queryKey: sshKeysKey,
    queryFn: async () => (await SshKeysService.keysReadSshKeys()).data,
    enabled,
  })
}

/**
 * The key a connection signs in with, when a read of it answered "locked"
 * (D147); null otherwise, and for anybody but the key's owner. The list is
 * asked for only once something was refused.
 */
export function useLockedKey(
  connectorId: MaybeRefOrGetter<string>,
  errorKind: MaybeRefOrGetter<string | null | undefined>
): ComputedRef<SshKeyPublic | null> {
  const locked = computed(() => toValue(errorKind) === "locked")
  const keys = useSshKeys(locked)
  return computed(() =>
    locked.value ? keyUsedBy(keys.data.value ?? [], toValue(connectorId)) : null
  )
}

/** Every change to a key is answered by re-reading the list it is in. */
function useKeyMutation<T>(run: (input: T) => Promise<unknown>) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: run,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: sshKeysKey })
    },
  })
}

export function useGenerateSshKey() {
  return useKeyMutation(
    async (body: SshKeyGenerateWritable) =>
      (await SshKeysService.keysGenerateSshKey({ body })).data
  )
}

export function useImportSshKey() {
  return useKeyMutation(
    async (body: SshKeyImportWritable) =>
      (await SshKeysService.keysImportSshKey({ body })).data
  )
}

export function useDeleteSshKey() {
  return useKeyMutation(
    async (keyId: string) =>
      (await SshKeysService.keysDeleteSshKey({ path: { key_id: keyId } })).data
  )
}

/**
 * Opening a key also re-reads everything that failed because it was shut:
 * a catalog that answered "locked" a moment ago is what the person unlocked
 * it for, and making them press Reload as well would be a second gesture for
 * one intention.
 */
export function useUnlockSshKey() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (asked: { keyId: string; body: SshKeyUnlockWritable }) =>
      (
        await SshKeysService.keysUnlockSshKey({
          path: { key_id: asked.keyId },
          body: asked.body,
        })
      ).data,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: sshKeysKey })
      await queryClient.refetchQueries({ predicate: (query) => query.state.status === "error" })
    },
  })
}

export function useLockSshKey() {
  return useKeyMutation(
    async (keyId: string) =>
      (await SshKeysService.keysLockSshKey({ path: { key_id: keyId } })).data
  )
}

/**
 * The server key a draft trusts, and what the server presents when asked
 * (D145). A mutation rather than a query even when it only describes: the
 * form asks about what it holds now, and a cached answer about a key the
 * person has since replaced would be the one thing this must never show.
 */
export function useServerKey() {
  return useMutation({
    mutationFn: async (body: ServerKeyRequest) =>
      (await ConnectorsService.describeServerKey({ body })).data,
  })
}
