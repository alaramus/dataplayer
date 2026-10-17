/** Which DataPlayer server this tab talks to (features/servers). */
export const servers = {
  check: {
    https_only: "This page uses HTTPS. Use an HTTPS server address.",
    unreachable:
      "Could not reach a compatible DataPlayer server. Check the address, server version, certificate and allowed frontend origin (CORS).",
    incompatible: "This server is not compatible with this version of DataPlayer.",
  },
  name_invalid: "Enter a server name of 1 to 100 characters.",
  name: "Server name",
  url: "Server URL",
  url_example: "https://data.example.com",
  boundary: {
    title: "Connect to DataPlayer",
  },
  link: {
    new_server: "New server",
    connect_failed: "Could not connect to this server.",
    title: "Choose the server for this link",
    notice:
      "This link uses another server. Check the address before connecting; you may need to sign in there.",
    connect: "Check and connect",
  },
  switcher: {
    save_failed: "Could not save the server in this browser.",
    compatible: "Compatible DataPlayer server.",
    saved: "Server saved. Choose Connect to use it in this tab.",
    choose: "Choose server",
    servers: "Servers",
    intro: "Choose the server for this browser tab. Accounts are separate on each server.",
    current: "Current: {name} · {url}",
    current_mark: " · Current",
    check: "Check",
    connect: "Connect",
    edit: "Edit server",
    remove: "Remove server",
    add: "Add server",
    check_connection: "Check connection",
    save_and_connect: "Save and connect",
    save: "Save server",
  },
}
