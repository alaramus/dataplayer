export function requiredCredentialErrors(username: string, password: string) {
  return {
    username: username.trim() === "" ? "Email is required" : "",
    password: password === "" ? "Password is required" : "",
  }
}
