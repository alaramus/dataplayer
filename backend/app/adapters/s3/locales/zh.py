"""What S3 writes, in Chinese (D226).

The file side is the explorer's and words itself; these are the words of the
store, its form and its refusals.
"""

MESSAGES: dict[str, str] = {
    "S3": "S3",
    "Amazon S3 or a store that speaks its API. Browse buckets and folders and work with objects as with your own files: tables, SQL over files, the editor, archives, search and copying between connections. Buckets are made and deleted here too. Signs in with an access key.": "Amazon S3 或兼容其 API 的存储。浏览存储桶和文件夹，像操作自己的文件一样处理对象：表格、文件上的 SQL、编辑器、归档、搜索以及在连接之间复制。也可以在这里创建和删除存储桶。使用访问密钥登录。",
    "The store's address, such as https://s3.example.com; empty for Amazon S3": "存储的地址，例如 https://s3.example.com；Amazon S3 留空",
    "Region": "区域",
    "Empty is us-east-1": "留空即 us-east-1",
    "Access key": "访问密钥",
    "Bucket": "存储桶",
    "Empty shows every bucket this key may list": "留空显示此密钥可列出的所有存储桶",
    "Where browsing starts inside the bucket": "在存储桶内从哪里开始浏览",
    "Addressing": "寻址方式",
    "Auto is virtual-hosted on Amazon S3 and path-style elsewhere": "自动：在 Amazon S3 上为 virtual-hosted，其他地方为 path-style",
    "Verify the certificate": "验证证书",
    "Off only for a store with a certificate of its own making": "仅对使用自制证书的存储关闭",
    "The endpoint must be an http or https address": "接入点必须是 http 或 https 地址",
    "A bucket is one name, without slashes": "存储桶是一个名称，不含斜杠",
    "The folder must stay inside the bucket": "文件夹必须位于存储桶内",
    "A folder needs the bucket it is in": "文件夹需要它所在的存储桶",
    "The store does not know this access key": "存储不认识此访问密钥",
    "The secret key does not match the access key": "私钥与访问密钥不匹配",
    "The store does not let this key do that": "存储不允许此密钥执行该操作",
    "There is no such bucket in this store": "此存储中没有该存储桶",
    "The bucket is in another region than this connection names": "存储桶所在区域与此连接指定的区域不同",
    "This object is archived and has to be restored first": "此对象已归档，需要先恢复",
    "That is no longer in the store": "存储中已不再有此项",
    "The store's certificate was not accepted": "存储的证书未被接受",
    "The store did not answer in time": "存储未及时响应",
    "Could not reach the store": "无法连接到存储",
    "The store could not do that": "存储无法完成此操作",
    "Only buckets are kept at the root of the store": "存储的根目录下只能放存储桶",
    "{name} holds more than {count} objects; this store changes them one by one, so it is refused": "{name} 中的对象超过 {count} 个；此存储逐个更改对象，因此拒绝执行",
    "The store did not delete every object": "存储未能删除所有对象",
    "A bucket is not renamed or copied as a whole": "存储桶不能整体重命名或复制",
    "A bucket's name is 3 to 63 lowercase letters, digits, dots and hyphens, beginning and ending with a letter or a digit": "存储桶名称由 3 到 63 个小写字母、数字、点和连字符组成，并以字母或数字开头和结尾",
    "{name} keeps old versions of its objects; empty it with a lifecycle rule, then delete it": "{name} 保留了对象的旧版本；请先用生命周期规则清空它，然后再删除",
}
