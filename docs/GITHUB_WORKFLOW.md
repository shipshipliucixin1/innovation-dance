# GitHub 持续更新指南

项目：ProjectFlow；远程仓库：[shipshipliucixin1/innovation-dance](https://github.com/shipshipliucixin1/innovation-dance)；主分支：`main`。

## 最简单的更新方式

1. 在当前目录修改代码或文档，保存文件。
2. 双击根目录 `update-github.bat`。
3. 检查窗口显示的修改文件，输入一句更新说明，例如 `Improve project review prompts`。回车使用默认说明。
4. 看到 `GitHub main is up to date` 后关闭窗口。

脚本顺序是：验证项目解释器 → fetch → 检查远程历史是否已包含在本地 → 工作文件与历史安全扫描 → stage → 暂存区再次扫描 → commit → 普通 push。不会使用 `--force`，不会自动改写提交或覆盖远程历史。没有新文件时也会尝试推送之前因网络失败尚未上传的本地提交。

安全检查不等于全面识别私人信息。新增文档、截图与数据样例仍需自行确认可公开。不要使用 `git add -f` 绕过忽略规则，不要把真实数据库、聊天导出或密钥作为测试样例提交。

## 手动更新

在项目目录打开 PowerShell：

```powershell
git status
git fetch origin
.\.conda-env\python.exe scripts\check_secrets.py
git add --all
.\.conda-env\python.exe scripts\check_secrets.py --staged-only
git diff --cached --stat
git commit -m "Describe your update"
git push origin main
```

**每条命令都需成功后再继续**，尤其是安全检查。`main` 应包含 `origin/main` 的所有既有提交；使用自动脚本会先验证这个条件。推送成功仅代表代码已上传，GitHub Actions 的测试结果还要在仓库 Actions 页面查看。

## 远程比本地更新时

脚本会停止，不自动合并正在编辑的文件。先保存当前修改并通过安全检查，然后提交本地工作：

```powershell
git add --all
.\.conda-env\python.exe scripts\check_secrets.py --staged-only
git commit -m "Save local work"
git pull --no-rebase origin main
```

如有冲突，处理后再提交，重新运行安全检查和测试，再执行更新脚本。这种方式通过合并保留两边历史。不要执行强制推送、`reset --hard` 或盲目覆盖文件。

## 登录与网络

HTTPS 推送使用 Git Credential Manager 或 GitHub CLI 的已授权凭据，登录在 GitHub 官方浏览器界面完成。不要将 token 放入 remote URL、脚本、README、命令行参数或聊天。遇到登录请求时由自己输入并完成授权。

此机器的首次上传遇到无效的本机代理；可通过命令级覆盖测试直连：`git -c http.proxy= fetch origin`。如本仓库配置了空的 `http.proxy`，只影响本仓库，不改变其他仓库或全局代理。其他机器如果需要代理，应使用自己的配置。更新脚本也支持在当前 PowerShell 会话设置 `$env:PROJECTFLOW_GIT_DIRECT='1'` 来选择命令级直连。

## 哪些内容不会上传

`.gitignore` 排除 `.env`（只保留空的 `.env.example`）、项目 Conda 环境、运行数据库、`data/`、`.qa/`、测试临时数据、`dist/`、私钥与证书、常见凭据文件、本地导出/备份、缓存和无关构建目录。

`scripts/check_secrets.py` 扫描工作文件、完整暂存区及所有 refs/reflog 可达的历史对象。它覆盖常见模型/GitHub/AWS/Google/Slack 凭据特征、私钥头和字面量密钥赋值，也扫描 commit 信息及注解 tag。发现潜在问题时只输出文件、行和规则，不输出匹配值，并以失败状态停止。二进制文件仅做已知字节特征检查，截图仍需人工审核。它不是专业秘密扫描器的完整替代品，也不能保证检出任意格式密钥或私人信息。

## 如果发现密钥风险

立即停止推送。不要只删除当前文件后继续，因为旧提交可能仍含密钥。先撤销/轮换相关凭据，再检查影响范围。仓库历史的清理与强制推送需要单独设计、明确授权，本更新脚本不会自动执行。

## 测试与 CI

```powershell
.\.conda-env\python.exe -m unittest discover -s tests -v
```

测试使用本地样例和临时数据库，不调用付费模型。已有 `.github/workflows/tests.yml` 会在 push/pull request 时运行 Windows 和 Linux 测试；不会部署网站、启动云服务或上传本地业务数据。
