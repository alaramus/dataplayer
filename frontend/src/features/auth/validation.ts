import { t } from "@/shared/i18n"

export function requiredCredentialErrors(username: string, password: string) {
  return {
    username: username.trim() === "" ? t("auth.email_required") : "",
    password: password === "" ? t("auth.password_required") : "",
  }
}
