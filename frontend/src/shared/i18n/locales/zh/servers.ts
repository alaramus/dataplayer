/** 此标签页连接到哪台 DataPlayer 服务器（features/servers）。 */
import type { Messages } from "../en"

export const servers: Messages["servers"] = {
  check: {
    https_only: "此页面使用 HTTPS。请使用 HTTPS 服务器地址。",
    unreachable:
      "无法连接到兼容的 DataPlayer 服务器。请检查地址、服务器版本、证书和允许的前端来源（CORS）。",
    incompatible: "此服务器与此版本的 DataPlayer 不兼容。",
  },
  name_invalid: "请输入 1 到 100 个字符的服务器名称。",
  name: "服务器名称",
  url: "服务器 URL",
  url_example: "https://data.example.com",
  boundary: {
    title: "连接到 DataPlayer",
  },
  link: {
    new_server: "新服务器",
    connect_failed: "无法连接到此服务器。",
    title: "为此链接选择服务器",
    notice:
      "此链接使用另一台服务器。连接前请检查地址；可能需要在那里登录。",
    connect: "检查并连接",
  },
  switcher: {
    save_failed: "无法在此浏览器中保存服务器。",
    compatible: "兼容的 DataPlayer 服务器。",
    saved: "服务器已保存。选择“连接”即可在此标签页中使用它。",
    choose: "选择服务器",
    servers: "服务器",
    intro: "为此浏览器标签页选择服务器。每台服务器上的账户相互独立。",
    current: "当前：{name} · {url}",
    current_mark: " · 当前",
    check: "检查",
    connect: "连接",
    edit: "编辑服务器",
    remove: "移除服务器",
    add: "添加服务器",
    check_connection: "检查连接",
    save_and_connect: "保存并连接",
    save: "保存服务器",
  },
}
