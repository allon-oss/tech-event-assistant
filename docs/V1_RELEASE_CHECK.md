# V1.0 公开前收尾记录

检查日期：2026-10-05。本轮仅收尾，不新增业务功能或页面；未创建远程仓库、push 或部署。

## V0.3 保存

- 提交：`2b17279f9c30ee7f728f81436f9d4e6ba639bf2b`。
- 信息：`feat: complete v0.3 event review workflow`。
- 提交前原有 47 项测试通过；逐项检查暂存的 10 个文件，未包含本地生成数据或配置。
- `.gitignore` 已覆盖 `.env*`、working CSV、复盘草稿、虚拟环境、缓存、日志、临时文件与本地工具配置。Streamlit 仅允许共用 `config.toml` 进入 Git，`secrets.toml` 被忽略。

## 安全检查范围与结果

扫描当前项目自有文件和本地运行产物，排除 Git 内部文件、第三方虚拟环境与生成缓存；另外检查 Git 所有引用及 reflog 可达的 2 个提交、28 个唯一历史 blob、25 个历史路径，并检查 1 个不可达 blob。未修改历史。

检查凭证模式（API Key、Token、密码、Cookie、私钥）、数据库连接、手机号、邮箱、微信号、本机用户名和 Windows 绝对路径；复查可能不应公开的文件名及提交作者信息。可公开文件和受检 Git 内容未发现上述风险，Git 作者使用 GitHub 隐私邮箱；未发现历史提交过 working CSV、复盘草稿、日志、`.env`、密钥或虚拟环境。

本地虚拟环境、日志、模拟复盘草稿、Linux 依赖解析报告均被忽略，不属于公开仓库范围。依赖报告中的上游维护者邮箱和路径示例来自公开软件包元数据，未进入 Git。发布应使用经检查的 Git 文件，避免上传整个本地目录。

数据字典明确记录人物、负责人、公司、项目为人工组合的虚构演示资料。原始 CSV 共 100 条、100 个不同演示姓名；所有 98 个非空机构带 `虚构·` 标识，所有非空备注带 `Synthetic Demo Data；` 标识。未发现真实联系方式，没有真实客户资料的来源或记录。名称可能与真实世界偶然同名，虚构来源以数据字典说明为准。

原始 CSV SHA256 保持：

```text
6bae9989b305c488eecd303cbc7776b3a11d60e7b7ff6f1ab127f4eeb9cea7e3
```

## 模式与部署

`src/app_mode.py` 优先读取环境变量 APP_MODE；没有环境变量时读取 Streamlit 应用配置，缺失配置默认 local，非法值显示错误并停止。公网必须显式设置 demo。

Local Mode 保留原来的 working CSV 和 Markdown 文件持久化、版本检查和原子替换。Demo Mode 使用 `SessionFollowupStore` / `SessionReviewStore`，只将数据副本和草稿保存到访问者自己的 `st.session_state`，不使用共享可变缓存，也不读写本地 working CSV / 复盘文件。复用相同的业务校验、统计、模板和导出。恢复只改变该会话跟进数据；CSV 下载为本会话已保存跟进，Markdown 下载为当前编辑全文。刷新或会话结束后重置，页面和 README 已说明。

路径通过模块位置与 pathlib 定位，不依赖 Windows 用户目录；支持其他启动目录。`requirements.txt` 无本机路径、新 API 服务或额外依赖。原有 3 个固定依赖保留；`pip check` 通过，Python 3.12 / 现代 x86-64 Linux 的 38 个依赖可解析为 wheels。Pandas Linux wheel 要求 glibc 2.24 或更新。未在 Linux 实机运行，未部署公网。

README 已说明科技 / 创业活动的观察 → 跟进 → 复盘、作品集 Demo、合成数据、没有真实客户数据、没有 LLM / 数据库 / 登录，以及 Windows / Linux 启动与后续托管配置。保留本地 loopback 默认监听，其他托管环境须按 README 覆盖监听地址和端口。

## 验证与待确认

原有 47 项加新增 7 项，共 54 项通过。新增测试先复现公共文件写入及读取 Local 数据的问题，再验证会话隔离、修改 / KPI / 复盘 / 下载、恢复确认、无公共文件生成、已有 Local 文件不变、原始 CSV 字节不变、缺失数据处理、非法模式、Cloud 配置和其他目录启动。Local 页面测试明确指定 local，使完整测试也能从设置 APP_MODE=demo 的终端通过。

测试使用临时目录。AppTest 的 `missing ScriptRunContext` 提示来自测试环境，不是页面异常。下载验证检查实际交给 Streamlit 下载组件的字节；本轮没有重复 V0.3 的人工浏览器验收或实际公网下载。

V1.0 经用户确认，以 `chore: prepare v1.0 for public demo` 保存本地 Git。提交前再次检查暂存范围，排除本地生成数据、草稿、日志、缓存和环境文件；本轮不创建远程仓库、不 push、不部署。实际部署后须进行托管环境验收。本轮没有发现代码或安全阻塞问题。

独立只读审查通过，审查者另行运行 54 项完整测试全部通过；未发现代码正确性或访问者会话隔离阻塞问题，未修改源码、索引或 HEAD。
