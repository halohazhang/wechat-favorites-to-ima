# wechat-favorites-to-ima

把**微信收藏夹里的公众号文章**批量迁移到**腾讯 ima 知识库**的 Claude 技能(Skill)。

先在本地建立 Markdown 存档,再分批、经确认地导入 ima。全程可断点续跑,每一步高风险操作都需要用户确认——不碰微信数据库、不碰逆向 API、不经手任何凭据。

> 适用平台:macOS(依赖 Mac 微信客户端的 UI 自动化导出)

## 工作原理

```
Mac 微信收藏夹
   │  ① UI 自动化导出文章链接(CSV)
   ▼
queue.jsonl(迁移状态的唯一事实来源)
   │  ② 按批下载文章正文 → 本地 Markdown 存档
   ▼
wandao-batches/<批次>/files/
   │  ③ 经用户确认后,通过万能导(Wandao)批量导入
   ▼
ima 知识库
   │  ④ 逐条核对标题与正文可搜索性
   ▼
verified(完成)
```

整条链路由 `queue.jsonl` 记录每篇文章的状态(`queued → download_planned → archived → ready_for_wandao → importing → imported → verified`),中断后可从任意位置恢复,失败与需人工处理的条目会被显式标记,绝不静默丢失。

## 设计原则

- **先存档,后导入**:所有文章先落成本地 Markdown,ima 里的内容永远有本地备份。
- **小批量 + 人工确认**:试点 5 篇,后续每批不超过 20 篇;每次上传前必须向用户复述目标知识库名称和文件数。
- **不碰敏感数据**:不读微信数据库、浏览器 Cookie、密码、API Key、万能导已保存的凭据,不调用 ima 未公开的私有接口。
- **不虚报进度**:上传任务开始 ≠ 导入成功;只有在 ima 里逐条核实过的条目才会标记为 `verified`。
- **遇到风控就停**:登录、二维码、验证码、账号警告、目标不明确、连续三次失败,一律停下来交还给用户。

## 依赖的外部工具

本技能不捆绑任何第三方代码,以下工具需按各自仓库说明自行安装(建议钉死到具体 commit,升级前先审查改动):

| 工具 | 用途 | 许可证 |
|---|---|---|
| [wechat-favorites-exporter](https://github.com/pengyulong/wechat-favorites-exporter) | 通过 macOS 辅助功能自动化,把微信收藏夹的公众号文章链接导出为 CSV | MIT |
| [wechat2md](https://github.com/shiyan521/wechat2md) | 把公众号文章 URL 批量下载为带图 Markdown | MIT |
| [万能导 Wandao](https://github.com/tllovesxs/wandao) | 把 Markdown 目录批量导入 ima 知识库 | AGPL-3.0(仅外部调用,本技能不捆绑、不修改) |

其他前置条件:macOS、Python 3.10+、已登录的 Mac 微信客户端、辅助功能(Accessibility)权限。

⚠️ 使用 wechat2md 前请检查其是否关闭了 TLS 证书校验(`verify=False`),`check_environment.py` 会自动检测并告警;在修补或替换之前,不要用关闭校验的下载器抓取私人内容。

## 安装

```bash
npx skills add halohazhang/wechat-favorites-to-ima
```

或手动把本仓库放入你的 skills 目录。安装后对 Claude 说"把我的微信收藏迁移到 ima"即可触发。

## 使用流程

技能会引导 Claude 按以下阶段执行(详见 [SKILL.md](SKILL.md) 与 [references/workflow.md](references/workflow.md)):

1. **环境体检**(只读不改):`python3 scripts/check_environment.py`,报告三个外部工具的位置、版本与安全隐患。
2. **导出试点**:用户登录 Mac 微信并打开「收藏 → 链接」,授权 UI 控制后导出最多 20 条链接。
3. **初始化队列**:`manage_queue.py init` 建立 `queue.jsonl`,自动去重、拒收非法 URL,并输出按域名的统计(出现非 `mp.weixin.qq.com` 的域名会单独列出提醒)。
4. **下载 5 篇存档试点**:用户批准联网后运行下载器,`reconcile` 把 Markdown 对回队列;正文提取失败的只算"仅链接占位",绝不上传。
5. **创建并上传试点批次**:`make-batch` 生成批次目录,用户确认目标知识库和数量后经万能导上传;只有万能导确认成功的条目才标 `imported`。
6. **核验并继续**:在 ima 里逐条核对试点文章的标题和正文,确认后按每批 ≤20 篇继续,直到全部条目落入终态(`verified` / `skipped` / `failed` / `needs_user`),并生成 `report.md`。

后续增量同步:再次导出后用 `manage_queue.py merge` 合并,已有条目自动去重,只处理新增。

## 仓库结构

```
├── SKILL.md                          技能入口与安全规则
├── references/
│   ├── workflow.md                   检查点、职责分工、正常/恢复流程
│   ├── tool-contracts.md             三个外部工具的信任边界与调用约定
│   ├── exporter-compatibility.md     导出器对当前微信 UI 的兼容性检查
│   └── queue-schema.md               队列文件格式、状态机与修复规则
├── scripts/
│   ├── check_environment.py          只读环境检查(不安装、不修改)
│   └── manage_queue.py               队列管理:init/merge/prepare-download/
│                                     reconcile/make-batch/mark-*/report
└── agents/openai.yaml                跨平台 agent 界面描述
```

两个脚本均为纯标准库实现,无网络请求,队列写入采用临时文件 + 原子替换,中断不损坏状态。`mark-item`/`mark-batch` 内置状态转移白名单,防止误把未核实的条目标成完成;人工修复需显式 `--force` 并建议用 `--note` 记录原因。

## 边界与限制

- 导出器只识别可见的公众号文章链接,**不覆盖**收藏夹里的普通网页、笔记、图片等其他类型;导出数量 ≠ 收藏总数。
- 文章 URL 和生成的存档会暴露个人阅读兴趣,**不要公开运行目录**(run 目录应放在技能目录之外的用户工作区)。
- 本技能不做也不应做:解密微信本地数据库、绕过登录/验证码、调用 ima 私有接口。

## 许可证

[MIT](LICENSE)。所依赖的外部工具遵循其各自的许可证。
