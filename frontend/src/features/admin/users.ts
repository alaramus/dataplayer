import type { UserInvite, UserPublic, UserUpdate } from "@/client"
import { t } from "@/shared/i18n"

/**
 * The form behind the user dialog, and what it turns into.
 *
 * Plain functions rather than logic inside the component, so the rules that
 * matter are tested without mounting anything. There is no password here: a
 * new account chooses its own through the link it is given, and an existing
 * one is reset by issuing another.
 */
export interface UserForm {
  email: string
  fullName: string
  isActive: boolean
  isSuperuser: boolean
  /** Megabytes the person's storage may hold; null leaves the server's figure (D324). */
  storageQuotaMb: number | null
}

export function emptyForm(): UserForm {
  return {
    email: "",
    fullName: "",
    isActive: true,
    isSuperuser: false,
    storageQuotaMb: null,
  }
}

export function formOf(user: UserPublic): UserForm {
  return {
    email: user.email,
    fullName: user.full_name ?? "",
    isActive: user.is_active ?? true,
    isSuperuser: user.is_superuser ?? false,
    storageQuotaMb: user.storage_quota_mb ?? null,
  }
}

/**
 * What is wrong with the form, by field. An empty object means nothing is.
 *
 * The same rule the server applies, checked here so that a typo does not cost
 * a round trip; the server still applies it, and its answer still wins.
 */
export function validate(form: UserForm): Record<string, string> {
  const errors: Record<string, string> = {}
  if (!/^\S+@\S+\.\S+$/.test(form.email)) {
    errors.email = t("admin.users.email_invalid")
  }
  if (form.storageQuotaMb !== null && (!Number.isInteger(form.storageQuotaMb) || form.storageQuotaMb < 0)) {
    errors.storageQuotaMb = t("admin.users.storage_limit_invalid")
  }
  return errors
}

export function toCreate(form: UserForm): UserInvite {
  return {
    email: form.email,
    full_name: form.fullName === "" ? null : form.fullName,
    is_active: form.isActive,
    is_superuser: form.isSuperuser,
    storage_quota_mb: form.storageQuotaMb,
  }
}

export function toUpdate(form: UserForm): UserUpdate {
  return {
    email: form.email,
    full_name: form.fullName === "" ? null : form.fullName,
    is_active: form.isActive,
    is_superuser: form.isSuperuser,
    storage_quota_mb: form.storageQuotaMb,
  }
}

/** What the table says of a person's limit: theirs, or the server's. */
export function storageLimitText(user: UserPublic): string {
  const megabytes = user.storage_quota_mb ?? null
  if (megabytes === null) return t("admin.users.storage_limit_server")
  if (megabytes === 0) return t("admin.users.storage_limit_none")
  return t("admin.users.storage_limit_mb", { n: megabytes })
}

/**
 * Why this account cannot be removed, or nothing.
 *
 * The server refuses a superuser deleting themselves; saying so before the
 * press is the same rule shown rather than explained after the fact.
 */
export function undeletableReason(user: UserPublic, currentUserId: string | null): string {
  return user.id === currentUserId ? t("admin.users.cannot_delete_self") : ""
}
