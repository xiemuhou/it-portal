# IT 门户 Windows 部署与启停手册

适用范围：Windows 10/11、Windows Server，SQL Server 业务库，门户默认端口 `8089`。

## 1. 上线前准备

服务器需要具备：

- Python 3.10 或更高版本，并已加入 `PATH`。
- 与 `business.local.json` 一致的 Microsoft ODBC Driver 17/18 for SQL Server。
- 到 SQL Server、EHR、LDAP、AI API 等实际启用数据源的网络访问权限。
- 一个权限受控的 Windows 运行账号。该账号需要读取项目目录、写入 `data/`，但不应具有本机管理员权限。
- 反向代理和 HTTPS（正式跨网段或包含敏感信息时建议启用）。

部署前应确认项目目录不是临时目录，也不会被 OneDrive 等同步软件占用。`business.local.json`、数据库密码和本地加密密钥不得通过公开渠道传递。

## 2. 首次部署

以 PowerShell 进入项目目录：

```powershell
Set-Location 'D:\04-AI Project\it-portal'
.\portal.bat deploy
```

首次运行会完成以下工作：

1. 检查 Python 版本。
2. 创建项目专用 `.venv`。
3. 安装 `requirements-business.txt`。
4. 若配置不存在，从模板生成 `business.local.json` 并停止。

填写 `business.local.json` 后再次执行：

```powershell
.\portal.bat deploy -InitializeAdmin
```

该命令会校验配置 JSON、验证关键依赖、执行 `alembic upgrade head`，并初始化权限及管理员。脚本不会启动服务，也不会自动开放 Windows 防火墙。

如果数据库已经初始化，后续部署或升级只运行：

```powershell
.\portal.bat deploy
```

在离线环境已确认依赖完整时，可使用 `-SkipDependencyInstall`，但脚本仍会检查关键模块并执行迁移。

## 3. 防火墙与访问

默认绑定 `0.0.0.0:8089`，局域网地址为 `http://服务器IP:8089/`。如 Windows 防火墙未放行，需要管理员按公司安全规范创建仅面向可信网段的 TCP 8089 入站规则。不要为了方便将端口暴露到公网。

只允许本机或反向代理访问时使用：

```powershell
.\portal.bat start -BindAddress 127.0.0.1
```

## 4. 日常启停

### 后台启动

```powershell
.\portal.bat start
```

脚本会检查端口冲突，隐藏窗口启动应用，等待健康检查通过，再写入 `data/runtime/portal-process.json`。如果应用未在 45 秒内健康，会终止本次启动进程并提示错误日志位置。

### 状态检查

```powershell
.\portal.bat status
```

正常状态同时满足：

- `Listening: True/yes`：端口正在监听。
- `Managed: True`：进程由后台脚本管理，进程号和项目路径一致。
- `Healthy: True`：`/api/health` 返回正常。

也可以在浏览器访问：

```text
http://127.0.0.1:8089/api/health
```

### 安全停止

```powershell
.\portal.bat stop
```

停止脚本会同时核对运行状态文件、项目路径、端口所有者和 Python 进程。状态不一致时会拒绝停止，防止误关其他 Python 服务。不要使用 `taskkill /IM python.exe`，它会结束服务器上的其他 Python 程序。

### 前台调试

```powershell
.\portal.bat foreground
```

前台运行适合排查启动报错，按 `Ctrl+C` 停止。前台实例不写运行状态文件，因此不能使用后台停止脚本关闭。

## 5. 日志和运行文件

| 路径 | 用途 | 是否需要备份 |
| --- | --- | --- |
| `data/runtime/portal-process.json` | 后台进程号、端口和日志位置 | 否 |
| `data/logs/portal-console-*.log` | 后台启动控制台输出，启动时清理 90 天前文件 | 通常否 |
| `data/business/logs/portal.jsonl*` | 应用结构化日志，默认保留 90 天 | 按审计要求 |
| `data/business/reports/file-integrity/` | 文件一致性巡检报告 | 建议 |

运行状态文件和控制台日志不是业务数据。数据库、附件、知识原件、凭据密钥及 `business.local.json` 才是恢复系统所必需的内容。

## 6. 开机自启建议

项目自带后台脚本适合人工维护，但不会自动随 Windows 重启。正式无人值守运行建议二选一：

1. **Windows 任务计划程序**：以专用运行账号在“计算机启动时”执行 `D:\04-AI Project\it-portal\portal.bat foreground`。任务的“起始于”设置为项目目录，并启用失败后重试。任务运行前台模式，由任务计划程序负责进程生命周期。
2. **Windows 服务包装器**：使用公司批准的 WinSW/NSSM 等工具，把 `.venv\Scripts\python.exe -m portal --host 0.0.0.0 --port 8089` 注册为服务，并配置自动恢复。

不要让任务计划程序、Windows 服务和 `portal.bat start` 同时管理同一端口。使用任务计划程序时，通过 `Start-ScheduledTask` / `Stop-ScheduledTask` 启停；使用 Windows 服务时，通过服务控制台或 `Start-Service` / `Stop-Service` 启停。

## 7. 版本升级流程

1. 在维护窗口停止门户。
2. 备份 SQL Server 数据库。
3. 备份整个 `data/business/` 和 `business.local.json`，特别是知识、附件、`wifi-secrets.key`、`ai-secrets.key` 与 `credentials/`。
4. 替换代码，但不要覆盖 `data/`、`.venv/` 和 `business.local.json`。
5. 执行 `.\portal.bat deploy` 安装依赖并升级数据库。
6. 启动门户并执行 `.\portal.bat status`。
7. 登录后检查首页、工单、知识库、附件、静态 IP、电脑资产和组织同步。

数据库迁移完成后，旧程序不一定兼容新结构。回退前必须同时评估代码和数据库版本，不能只覆盖程序文件。

涉及 SQL Server 地址变化、数据库服务器迁移或门户服务器重建时，请按 [数据库与门户迁移恢复手册](数据库与门户迁移恢复手册.md) 操作。不要只恢复 `.bak` 而遗漏 `data/business/` 和加密密钥。

## 8. 常见故障

### 提示端口已占用

```powershell
Get-NetTCPConnection -State Listen -LocalPort 8089 | Select-Object LocalAddress,LocalPort,OwningProcess
Get-Process -Id <OwningProcess>
```

确认进程来源后，从原来的控制台、任务计划程序或 Windows 服务停止；不要让停止脚本接管未知进程。

### 数据库不可用

检查 `business.local.json` 的服务器、端口、数据库名、ODBC 驱动、账号权限和证书设置。配置了外部数据库后，系统不会静默回退到 SQLite。

### 后台启动失败

查看 `data/logs/portal-console-*.stderr.log` 的最新文件，并用前台脚本复现。常见原因包括数据库不可达、迁移未执行、ODBC 驱动缺失或配置 JSON 格式错误。

### 页面可打开但状态不健康

运行 `.\portal.bat status`，再检查结构化日志和数据库连接。健康接口正常时会返回 `status=ok` 及当前数据库类型。
