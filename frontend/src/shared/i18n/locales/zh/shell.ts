/** 应用外壳：App、路由、store、会话、服务器、socket、下载、剪贴板。 */
import type { Messages } from "../en"

export const shell: Messages["shell"] = {
  leave_work: {
    title: "离开正在进行的浏览器工作？",
    message:
      "切换时，此浏览器标签页中正在进行的上传和其他工作将会停止。已由服务器拥有的任务将在那里继续。",
    confirm: "切换服务器",
  },
  default_server: "默认服务器",
  server_url: {
    full_http: "请输入完整的 HTTP 或 HTTPS 服务器 URL。",
    full_url: "请输入完整 URL，例如 https://data.example.com。",
    http_only: "请使用 HTTP 或 HTTPS 服务器 URL。",
    no_extras: "服务器 URL 不得包含凭据、查询或片段。",
    invalid_destination: "目标无效",
  },
  servers: {
    invalid_profile: "请输入有效的服务器名称和 HTTP(S) URL。",
    default_is_configured: "默认服务器由此次安装配置。",
    already_saved: "该服务器已保存。",
    too_many: "添加另一个服务器前，请先移除一个已保存的服务器（最多 {n} 个）。",
  },
}
