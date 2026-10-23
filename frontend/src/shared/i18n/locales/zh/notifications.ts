/** 通知与屏幕上正在运行的工作（shared/notifications、shared/operations）。 */
import type { Messages } from "../en"

export const notifications: Messages["notifications"] = {
  toasts: {
    more: "“活动”中还有 {n} 条",
    dismiss: "忽略",
  },
  operations: {
    starting: "正在启动",
    waiting_to_resume: "等待恢复",
    upload_sent: "上传已发送；正在等待服务器",
  },
}
