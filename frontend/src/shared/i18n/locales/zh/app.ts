/** 不属于任何界面的词：登录、语言、主题。 */
import type { Messages } from "../en"

export const common: Messages["common"] = {
  back_to_workspace: "返回工作区",
}

export const language: Messages["language"] = {
  label: "语言",
  browser: "浏览器的语言",
  browser_hint: "此浏览器所请求的语言，或英语",
}

export const auth: Messages["auth"] = {
  sign_in: "登录",
  email: "电子邮件",
  password: "密码",
  email_required: "电子邮件为必填项",
  password_required: "密码为必填项",
  checking_server: "正在检查服务器……",
  retry_connection: "重试连接",
  sign_in_failed: "无法登录。请检查电子邮件和密码。",
  welcome_tagline: "一个地方，管理你使用的所有数据源",
}

export const theme: Messages["theme"] = {
  label: "主题",
  light: "浅色",
  paper_light: "浅色纸张",
  paper_light_hint: "温暖的浅色纸张，配以青铜色点缀",
  dark: "深色",
  paper: "深色纸张",
  paper_hint: "温暖的深色纸张，配以青铜色点缀",
  midnight: "午夜",
  midnight_hint: "最暗：近乎黑色的深蓝，配以冰蓝色点缀",
  dark_blue: "深蓝",
  dark_blue_hint: "饱和的深蓝，配以青色点缀",
  dark_purple: "深紫",
  dark_purple_hint: "紫色霓虹，配以粉色和青色点缀",
  system: "跟随系统",
  system_hint: "浅色或深色，随操作系统的变化",
  switch_to: "切换到 {theme}",
}
