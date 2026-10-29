# IT 服务与运维门户

面向公司员工和 IT 运维团队的内部服务门户。员工可以查看公告与知识、提交工单；IT 人员可以维护网络、资产、IP、耗材和运维记录；管理员负责组织、权限、内容与系统配置。

本 README 是项目入口，帮助你选择正确的部署或迁移路径。详细操作请进入对应专项手册，不需要一次读完所有文档。

## 快速判断：你现在要做什么

| 你的场景 | 操作系统 | 数据库 | 从哪里开始 |
| --- | --- | --- | --- |
| 保留现有生产环境 | Windows | SQL Server | [Windows 部署与启停手册](docs/Windows部署与启停手册.md) |
| 部署一套全新生产系统 | Linux | MySQL 8.0/8.4 | [Linux / MySQL 快速部署手册](docs/Linux快速部署手册.md) |
| 从零创建空数据库 | Windows 或 Linux | SQL Server 或 MySQL | 先配置数据库，再执行 `alembic upgrade head` |
| 把旧系统迁到 Linux | Windows SQL Server → Linux MySQL | 两端数据库 | [Linux 手册第 5 节](docs/Linux快速部署手册.md#5-从sql-server迁移数据) |
| 恢复或迁移 SQL Server | Windows | SQL Server | [数据库迁移与完整恢复手册](docs/数据库与门户迁移恢复手册.md) |
| 学习系统操作 | 浏览器 | 不涉及 | [系统操作手册](docs/IT门户系统操作手册_v1.0.md) |

默认服务端口为 `8089`。正式环境建议通过 Nginx 或公司统一网关提供内网域名和 HTTPS。

## 系统能力

- **门户内容**：公告、公告附件、知识库、IT 服务目录、网络运维态势入口和快捷链接。
- **工单管理**：提交、接单、转派、留言、附件、分类结单、重开、处理时长和最近 30 天默认报表。
- **AI 提单助手**：使用管理员配置的 OpenAI 兼容 API，根据已发布知识库提供建议；AI 不可用时不影响提交工单。
- **五类网络台账**：VLAN、Wi-Fi、网络设备、带宽线路和 VPN 隧道，支持标准模板导入导出及关联选择。
- **静态 IP 与电脑资产**：管理指定静态网段，关联人员、部门、设备、网卡、配件和变更历史。
- **耗材与备忘录**：耗材出入库、返库、撤销和流水；管理员及 IT 共用的加密备忘录。
- **组织与权限**：部门、岗位、人员、账号、角色、数据范围、EHR 只读同步和 LDAP/AD 只读同步。
- **运维保障**：站内通知、操作审计、结构化日志、文件一致性巡检和保留期清理。

完整业务规则见[需求规格说明书](docs/IT门户系统需求规格说明书_v1.0.md)。

## 部署组合

### Windows + SQL Server

适合保留现有环境。统一使用 `portal.bat`：

```powershell
# 首次部署或升级依赖
.\portal.bat deploy

# 首次初始化管理员
.\portal.bat deploy -InitializeAdmin

# 日常启停和检查
.\portal.bat start
.\portal.bat status
.\portal.bat stop
```

完整步骤、Windows 防火墙、开机自启和故障排查见[Windows 部署与启停手册](docs/Windows部署与启停手册.md)。

### Linux + MySQL

适合新生产环境。约定如下：

| 项目 | 约定 |
| --- | --- |
| 项目目录 | `/opt/it-portal` |
| 本机配置 | `/opt/it-portal/business.local.json` |
| 业务文件 | `/opt/it-portal/data/business` |
| 服务管理 | systemd，服务名 `it-portal` |
| 数据库 | MySQL 8.0/8.4，由数据库管理员创建 |
| 数据库账号 | 当前部署方案使用管理员提供的 `root` |

最小部署流程：

```bash
# 创建 Python 环境并安装依赖
cd /opt/it-portal
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-business.txt

# 生成并保护本机配置
cp business.example.json business.local.json
chmod 0600 business.local.json
nano business.local.json

# 注册并启动服务
cp deploy/systemd/it-portal.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now it-portal
```

全新空数据库会在首次启动前自动创建表结构并初始化管理员。详细依赖、MySQL、Nginx、迁移和验收步骤见[Linux / MySQL 快速部署手册](docs/Linux快速部署手册.md)。

## SQL Server 迁移到 MySQL

迁移不是把 `.bak` 直接导入 MySQL：

```text
停止旧门户写入
  → SQL Server 保持在线，或先用 SSMS 还原 .bak
  → 在空 MySQL 中执行 Alembic 建表
  → 运行预检查
  → 正式迁移并逐表校验
  → 复制 data/business
  → 验收后启动 Linux 门户
```

迁移工具具有以下保护：

- SQL Server 源库只读；
- 拒绝覆盖已有业务数据的 MySQL；
- 保留 UUID、账号密码哈希、权限和业务关联；
- 迁移失败时整体回滚；
- 逐表核对行数和 SHA-256 摘要；
- 不迁移历史会话，切换后所有用户重新登录。

当前兼容路径为 SQL Server `0018_remove_portal_backup` → MySQL `0019_mysql_datetime_precision`。`0019` 只修复 MySQL 毫秒时间精度，不要求修改 SQL Server 源库。

## 配置与业务文件

从 `business.example.json` 复制生成 `business.local.json`。常用配置：

| 配置项 | 用途 |
| --- | --- |
| `database` | 门户业务数据库连接 |
| `data_dir` | 知识、附件、密钥、日志和巡检报告目录 |
| `ehr_database` | EHR 只读数据源，不使用时设置 `enabled: false` |
| `ehr_org_code` | EHR 同步组织范围 |
| `ldap` | LDAP/AD 只读同步 |
| `monitor_url` | 网络运维态势系统地址 |
| `secure_cookie` | HTTPS 环境设为 `true` |
| `log_retention_days` | 结构化日志保留天数，默认 90 |
| `audit_retention_days` | 审计记录保留天数，默认 180 |
| `notification_retention_days` | 站内通知保留天数，默认 180 |

数据库不保存知识原文件和附件正文。以下目录必须和数据库一起备份：

| 路径 | 内容 |
| --- | --- |
| `data/business/knowledge/` | 知识库原文件 |
| `data/business/attachments/` | 公告和工单附件 |
| `data/business/knowledge-assets/` | HTML 知识资源 |
| `data/business/knowledge-cache/` | 可重新生成的 PDF/PPT 预览缓存 |
| `data/business/wifi-secrets.key` | 网络设备、线路、Wi-Fi 和备忘录凭据密钥 |
| `data/business/ai-secrets.key` | AI API 密钥的本地加密主密钥 |
| `data/business/credentials/` | 加密后的 AI 凭据文件 |
| `data/business/logs/` | JSON Lines 结构化日志 |
| `data/business/reports/file-integrity/` | 文件一致性巡检报告 |

`business.local.json`、数据库口令、业务文件和密钥只应保存在受控服务器及备份介质，不应混入普通代码交付包。

## 项目结构

```text
it-portal/
├─ portal/                    后端应用与业务模块
├─ portal_static/             浏览器前端资源
├─ migrations/                Alembic 数据库迁移
├─ deploy/                    systemd 与迁移配置示例
├─ scripts/                   授权、数据转换和维护脚本
├─ tests/                     自动化测试
├─ docs/                      需求、操作、部署和审计文档
├─ data/business/             运行期业务文件
├─ document_library.py        知识文件识别与预览
├─ document_worker.py         文档转换隔离进程
├─ business.example.json      配置模板
├─ requirements-business.txt  完整运行依赖
└─ portal.bat                 Windows 统一入口
```

## 验证和健康检查

```bash
# Linux 服务状态和日志
systemctl status it-portal --no-pager
journalctl -u it-portal -n 200 --no-pager
curl http://127.0.0.1:8089/api/health

# 自动化测试
.venv/bin/python -m unittest discover -s tests -v
node --check portal_static/portal.js
node --check portal_static/reader.js
node --check portal_static/ledger.js
node --check portal_static/ipam.js
```

Windows 将 `.venv/bin/python` 改为 `.venv\Scripts\python.exe`，或者直接执行 `portal.bat status`。

## 备份与恢复

门户不提供数据库备份按钮：

- SQL Server 使用 SQL Server Agent、维护计划、SSMS 或企业备份平台；
- MySQL 使用 `mysqldump`、物理备份或企业备份平台；
- 每个可恢复批次必须同时包含数据库、整个 `data/business/` 和部署配置；
- 至少定期在隔离环境进行一次真实恢复演练。

仅有数据库备份不能恢复知识文件、附件和加密密钥。详细边界见[数据库迁移与完整恢复手册](docs/数据库与门户迁移恢复手册.md)。

## 文档导航

| 文档 | 适合谁 | 解决什么问题 |
| --- | --- | --- |
| [文档导航与维护说明](docs/文档导航与维护说明.md) | 所有人 | 判断应该阅读哪份文档 |
| [系统操作手册](docs/IT门户系统操作手册_v1.0.md) | 员工、IT、管理员 | 页面功能怎么使用 |
| [需求规格说明书](docs/IT门户系统需求规格说明书_v1.0.md) | 负责人、开发、验收人员 | 功能边界和验收标准 |
| [Windows 部署与启停手册](docs/Windows部署与启停手册.md) | Windows 管理员 | SQL Server 环境部署、升级和启停 |
| [Linux / MySQL 快速部署手册](docs/Linux快速部署手册.md) | Linux 管理员 | 新建、迁移、systemd、Nginx 和排障 |
| [数据库迁移与完整恢复手册](docs/数据库与门户迁移恢复手册.md) | DBA、系统管理员 | SQL Server 备份、恢复和完整迁移 |
| [五类台账使用说明](docs/五类台账使用说明.md) | IT 运维 | 网络台账字段和关联规则 |
| [架构审计报告](docs/IT门户系统架构审计报告_2026-10-21.md) | 架构师、维护人员 | 风险、容量和后续优化建议 |
| [开发与部署说明](docs/新版开发与部署说明.md) | 开发维护人员 | 历史实现和技术交付记录 |

## 常见问题

### 新数据库需要手工执行建表 SQL 吗？

不需要。数据库由 Alembic 管理。Linux systemd 启动前会自动执行 `alembic upgrade head`；Windows 的 `portal.bat deploy` 也会执行迁移。

### SQL Server `.bak` 能直接导入 MySQL 吗？

不能。先把 `.bak` 恢复到 SQL Server，再使用 `portal.migrate_database` 读取并迁移到空 MySQL。

### 数据库迁移后为什么附件没有出现？

附件正文不在数据库中。必须同时复制整个 `data/business/`，并保留原来的加密密钥。

### Linux 域名可以打开 Nginx，但打不开门户怎么办？

依次检查 `127.0.0.1:8089`、Nginx 配置是否启用、80/443 端口、防火墙以及内部 DNS 是否解析到服务器局域网地址。完整命令见 Linux 手册。

### 可以同时启动 Windows 和 Linux 门户吗？

迁移验收期间可以让旧系统保持只读或停止状态，但不能让两套系统同时写入不同数据库。正式切换后只保留一个写入入口。

## 安全底线

- 不在普通代码交付包、聊天记录或日志中保存真实数据库密码和 API 密钥。
- 不记录 Cookie、令牌、附件正文或解密后的设备凭据。
- 删除数据库、业务文件或密钥前先验证可恢复备份。
- 浏览器隐藏菜单不等于权限控制，所有权限必须由后端再次校验。
- EHR 和 LDAP/AD 连接只用于查询与同步，不对源系统执行写入。
