import { t } from "@/shared/i18n"

export function requiredCredentialErrors(username: string, password: string) {
  return {
    username: username.trim() === "" ? t("auth.email_required") : "",
    password: password === "" ? t("auth.password_required") : "",
  }
}

/** The shortest password the server accepts. */
export const MIN_PASSWORD = 8

/** What is wrong with a password being chosen and its repetition, by field. */
export function newPasswordErrors(password: string, repeat: string) {
  return {
    password: password.length < MIN_PASSWORD
      ? t("auth.set_password.too_short", { n: MIN_PASSWORD }, MIN_PASSWORD)
      : "",
    repeat: repeat !== password ? t("auth.set_password.mismatch") : "",
  }
}
