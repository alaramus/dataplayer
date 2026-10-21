import type { Messages } from "../en"

export const preferences: Messages["preferences"] = {
  title: "偏好设置",
  saved: "偏好设置已保存",
  not_saved: "无法保存偏好设置",
  sections: {
    general: "常规",
    general_summary: "语言、主题、朗读语音和新手引导",
    connections: "连接",
    connections_summary: "工作区打开时检查连接的频率",
    ssh_keys: "SSH 密钥",
    ssh_keys_summary: "此账户用于 SSH 连接的密钥",
  },
  language_summary:
    "整个界面的语言。该设置保存在账户中，因此会随账户在任何浏览器中生效；在未选择之前，使用浏览器自身的语言。",
  appearance: "外观",
  appearance_summary:
    "为整个应用设置浅色或深色主题，或随操作系统在浅色和深色之间切换。该设置保存在账户中，因此会随账户在任何浏览器中生效。",
  voice: "朗读语音",
  voice_summary:
    "在所有朗读消息的地方用于朗读的语音。语音来自此浏览器本身。该设置保存在此浏览器中。",
  tour: "新手引导",
  tour_summary:
    "首次访问时的短片，应用的每个主要部分各一段。随时可在此重新打开。",
  replay_tour: "重播引导",
  checks: "检查连接是否可访问",
  checks_summary:
    "工作区打开时，会按此计划探测每个连接，其旁的圆点显示上次的响应。探测会打开自己的连接，因此对于缓慢或远程的服务器，值得降低询问频率。",
  checks_label: "检查连接的频率",
  interval: {
    off: "从不 — 仅在我点击检查时",
    "15s": "每 15 秒",
    "30s": "每 30 秒",
    "1m": "每分钟",
    "5m": "每 5 分钟",
    "15m": "每 15 分钟",
  },
}
