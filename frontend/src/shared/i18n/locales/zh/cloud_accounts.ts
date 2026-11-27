import type { Messages } from "../en"

/** 连接用于登录的云账号 (features/cloudAccounts). */
export const cloud_accounts: Messages["cloud_accounts"] = {
  section: {
    title: "云账号",
    hint: "您的连接从这些账号获取密码和令牌：Amazon Web Services, Google Cloud, Microsoft Azure 和 HashiCorp Vault。每建立一个新连接就签发一个令牌，且从不保存。在此输入的密钥会加密保存，之后不再显示。",
    form_hint: "您的连接从这些账号获取密码和令牌；一个账号可供任何连接使用。其密钥会加密保存，之后不再显示。",
    new_account: "新建账号",
    empty: "还没有云账号",
    unused: "没有连接使用它",
    used_by: "使用者：{names}",
    ambient: "本服务器的身份",
    test: "测试账号",
    test_failed: "无法测试该账号",
    edit: "修改账号",
    delete_title: "删除此账号？",
    delete_message: "{name} 及其密钥将从本服务器删除。凭据本身仍保留在云中。",
    delete: "删除",
    delete_failed: "无法删除该账号",
    delete_used: "请先将其连接改用其他账号",
    delete_account: "删除此账号",
  },
  dialog: {
    title_new: "新建云账号",
    title_edit: "修改云账号",
    subtitle: "密钥会加密保存，之后不再显示",
    name: "名称",
    kind: "云",
    make: "创建",
    save: "保存",
    made: "账号已创建",
    saved: "账号已保存",
    save_failed: "无法保存该账号",
  },
}
