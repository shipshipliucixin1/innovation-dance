# 首次公开推送检查记录

日期：2026-10-30。目标：[shipshipliucixin1/innovation-dance](https://github.com/shipshipliucixin1/innovation-dance)，分支 `main`。

## 基线与历史

检查时当前目录没有 `.git`，也不属于父级 Git 仓库，因此不存在需要保留或扫描的旧本地提交。只在本项目初始化 `main`。GitHub 仓库元数据与 `git ls-remote` 都显示仓库为空，没有远程分支或提交需要合并。后续使用普通推送，禁止强制推送或改写历史。

## 排除范围

`.gitignore` 已排除：项目 Conda/venv 环境、`.env` 及其本地变体、运行数据库、`data/`、`.qa/`、测试临时数据、构建/打包产物、常见私钥/凭据文件、聊天/项目导出与备份、IDE 缓存。仅提交空的 `.env.example`。两张界面截图来自明确标记的虚构演示内容，不包含用户私人项目或密钥。

`.gitattributes` 固定跨平台换行：Python/JS/文档使用 LF，Windows BAT/PowerShell 使用 CRLF，PNG 作为二进制。

## 凭据检查

使用新增的离线 `scripts/check_secrets.py`，检查候选工作文件、完整暂存区和所有 refs/reflog 可达历史对象，包括提交信息及注解 tag。覆盖常见模型/GitHub/AWS/Google/Slack 凭据特征、私钥头、带凭据 URL 和字面量密钥赋值；输出只含位置/规则，不打印匹配值。已知的精确虚构测试常量只在测试路径中允许。

新增三项测试：禁止上传路径、凭据特征与空示例配置、在一次性 Git 仓库中提交再删除虚构密钥后仍能从历史检出。三个新增测试与原 32 项业务测试均通过，共 **35 项**。测试不会调用付费模型，不使用用户私人数据。

该扫描是启发式检查，不能保证识别任意格式密钥、私人信息或图片中的文字。提交前仍检查文件清单；没有因忽略规则而声称旧历史中的文件会被自动删除。本项目首次初始化没有旧历史，已有项目则必须处理历史风险后再推送。

## 持续更新机制

- 完善中英文 README，提供实际仓库链接、clone、安装、模型配置及使用说明。
- 提供 `update-github.bat`：先 fetch 并确认远程提交已被包含，再扫描、stage、再次扫描、commit、普通 push；出现风险或远程分歧就停止。
- CI 使用完整 checkout 历史、只读仓库权限，运行发布前检查和离线测试；不部署云服务、不上传本机数据库。
- 登录由用户在 GitHub 官方浏览器界面完成，令牌由 Git Credential Manager 管理，不写入仓库、远程地址或脚本。

此记录随首次源码提交发布。实际提交 ID、推送结果和工作区状态以 Git 命令及 GitHub 返回结果为准。

## 首次推送后核对

首次提交 `f438fe61b7ececa3e26af2d9dfc8b847b1a55188` 已通过普通推送建立 `origin/main`，远程与本地 SHA 一致，工作区干净。首次远程 [GitHub Actions](https://github.com/shipshipliucixin1/innovation-dance/actions/runs/40911646963) 已在 Windows/Linux 完成并通过。随后保留此提交，通过后续正常提交补充“commit 后、push 前”的历史复查，保证刚输入的提交说明也被检查；没有 amend、rebase、reset 或强制推送。
