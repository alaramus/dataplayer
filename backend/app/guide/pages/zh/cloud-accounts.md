# 云账号

云账号是连接代表您访问云的方式：用来获取登录数据库的令牌，或读取保存在密钥存储中的密码。它像 SSH 密钥一样属于您：连接只引用它，与您共享该连接的人可以使用它，却看不到它。账号保存在**偏好设置**的**云账号**中；连接窗口的**选项**页面上也有**新建账号**按钮。

## 类型

- **Amazon Web Services**：**访问密钥**及其**私密密钥**，临时凭据还需**会话令牌**。可以代入一个**角色**——其 ARN、**外部 ID**、会话名称和时长。
- **Google Cloud**：JSON 格式的**服务账号密钥**文件。可以以另一个服务账号的身份操作，前提是对方允许。
- **Microsoft Azure**：**服务主体**——租户、客户端 ID 和客户端密钥。
- **HashiCorp Vault**：其**地址**，需要时还有命名空间和 CA 证书，以及**令牌**或 **AppRole** 的 Role ID 和 Secret ID。

密钥会加密保存，之后不再显示。**测试**会进行该账号允许的开销最小的无害调用，并说明是谁登录的。

## 本服务器自己的身份

账号也可以以运行 DataPlayer 的机器身份登录：AWS 的默认凭据链、Google 的 Application Default Credentials、Azure 的托管标识。任何人都可能借用这一身份，因此只有在安装允许时才会提供，而且只提供给超级用户。

## 连接如何使用账号

每建立一个新连接就签发一个令牌，令牌只保存在内存中，直到快过期为止；签发的内容一律不存储。每个数据源的页面都说明了其哪些登录方式需要账号：

- PostgreSQL 和 MySQL：AWS IAM（RDS）、Google Cloud IAM（Cloud SQL）、Microsoft Entra、密钥存储、Vault 动态凭据。
- Redis：AWS IAM（ElastiCache、MemoryDB）、Microsoft Entra。
- MongoDB：AWS IAM（MONGODB-AWS）、密钥存储。
- Kafka：AWS IAM（MSK）。
- S3：用 AWS 账号代替密钥。

**密钥存储**按密钥所在位置为其命名：在 AWS 上用名称或 ARN；在 Google 上写成 `projects/P/secrets/S`，或在密钥文件所属项目中只写名称；在 Azure 上写成 `VAULT/NAME`；在 Vault 中写成 `MOUNT/PATH`。JSON 格式的密钥按 `password` 和 `username` 键读取，键名可以修改；其他任何密钥本身就是密码。

通过 LDAP、PAM、RADIUS 或 Active Directory 校验密码的服务器不需要账号：在 DataPlayer 看来那就是密码。

## 限制

- 账号的类型不可更改；如需其他云，请新建账号。
- 正被连接使用的账号无法删除；拒绝信息会列出这些连接。
- 在长时间备份过程中过期的令牌不会中断备份：它已打开的连接仍然有效。
- 终端中的 Kafka 工具暂时无法使用 AWS IAM 或 OIDC 登录。
