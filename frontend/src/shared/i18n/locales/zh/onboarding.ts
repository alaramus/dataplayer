/** 欢迎导览（features/onboarding），以及用户指南窗口（features/guide）和朗读（features/speech）的少量文字。 */
import type { Messages } from "../en"

export const onboarding: Messages["onboarding"] = {
  title: "欢迎使用 DataPlayer",
  intro: "选择语言和应用程序的外观，然后观看一段简短的导览，了解它都能做什么：每个主要部分配有一段无声短片。",
  steps: {
    new_connection: "创建新连接",
    tabs: "使用标签页",
    table: "使用表",
    pipelines: "使用流水线",
    dashboards: "使用仪表盘",
    ai_agent: "使用 AI 智能体",
  },
  position: "第 {n} 步，共 {total} 步",
  start: "开始导览",
  finish: "完成",
  next: "下一步",
  skip_tour: "跳过导览",
  skip: "跳过",
  mark_failed: "无法将导览标记为已查看",
  close_title: "关闭欢迎导览？",
  close_message: "导览不会再次自动打开。你可以随时在偏好设置中的“欢迎导览”下重新播放。",
  close_confirm: "关闭导览",
  keep_watching: "继续观看",
  guide: {
    title: "用户指南",
    not_a_page: "该链接未指向用户指南中的页面",
    read_failed: "无法读取用户指南中的此页面",
  },
  speech: {
    listen: "朗读",
    stop: "停止朗读",
    browser_default: "浏览器默认",
  },
}
