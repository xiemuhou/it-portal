# IT 门户 Linux / MySQL 快速部署手册

本手册面向负责 Linux、MySQL 和网络访问配置的管理员。第一次部署时，先选择路径：

| 场景 | 建表方式 | 启动顺序 |
|---|---|---|
| 全新系统，不导入旧数据 | systemd 首次启动自动建表 | 配置完成后直接启动服务 |
| 从 SQL Server 迁移 | 手工执行 Alembic，只创建空表 | 建表 → 迁移 → 复制业务文件 → 启动服务 |

本版本按以下方式部署：

- 项目目录：`/opt/it-portal`
- 业务文件：`/opt/it-portal/data/business`
- MySQL数据库和root账号：由数据库管理员提前准备
- Linux进程：由systemd直接以root运行
- 首次启动：自动创建或升级数据库表结构

## 1. 准备项目

把项目代码复制或解压到：

```text
/opt/it-portal
```

安装依赖。Debian/Ubuntu示例：

```bash
sudo apt update
sudo apt install python3 python3-venv python3-pip unixodbc curl rsync \
  libreoffice-impress fonts-noto-cjk mysql-client

cd /opt/it-portal
sudo python3 -m venv .venv
sudo .venv/bin/python -m pip install --upgrade pip
sudo .venv/bin/python -m pip install -r requirements-business.txt
sudo mkdir -p data/business
```

如果需要从Linux直接读取SQL Server，或者继续使用SQL Server EHR同步，还要安装Microsoft ODBC Driver 18 for SQL Server。

## 2. 准备MySQL数据库

由MySQL管理员自行创建数据库并设置root密码。数据库要求MySQL 8.0或8.4，建议执行：

```sql
CREATE DATABASE IF NOT EXISTS itportal
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_0900_ai_ci;
```

本项目不负责创建、修改MySQL root账号，也不在项目中保存建库密码脚本。

## 3. 配置数据库连接

```bash
cd /opt/it-portal
sudo cp business.example.json business.local.json
sudo chmod 0600 business.local.json
sudo nano business.local.json
```

使用root密码连接的示例：

```json
{
  "database": {
    "engine": "mysql",
    "host": "127.0.0.1",
    "port": 3306,
    "name": "itportal",
    "username": "root",
    "password": "MySQL root密码",
    "unix_socket": ""
  },
  "data_dir": "/opt/it-portal/data/business",
  "timezone": "Asia/Shanghai"
}
```

如果MySQL root使用Linux本地socket认证，可以把密码留空，并填写实际socket路径，例如：

```json
"unix_socket": "/var/run/mysqld/mysqld.sock"
```

`business.local.json`保存 MySQL root 密码，只能保留在受控服务器上，不要混入普通代码交付包、聊天记录或日志；文件权限必须保持`0600`。

## 4. 全新系统是否需要手动建表

不需要手动执行建表SQL。systemd服务每次启动前会自动运行：

```bash
python -m alembic upgrade head
python -m portal.manage init-admin
```

因此：

- 全新空数据库：首次启动自动创建所有表并初始化管理员；
- 已有数据库：启动时只执行尚未运行的新迁移；
- 正常重启：不会重复创建表，也不会清空现有数据。

首次启动后，管理员交付信息可能保存在：

```text
/opt/it-portal/data/business/initial-account.txt
```

完成登录和改密后应删除该明文交付文件。

## 5. 从SQL Server迁移数据

### 5.1 SSMS的BAK文件不能直接导入MySQL

MySQL不能识别SQL Server的`.bak`文件。

- 如果原SQL Server数据库仍然存在：迁移工具直接读取原数据库，不需要使用`.bak`。
- 如果只剩`.bak`：先在任意SQL Server实例中通过SSMS执行“还原数据库”，然后让迁移工具读取还原后的数据库。

SSMS还原后的数据库名可以是`itPortal_Restore`，随后在迁移源配置中填写这个名称。

### 5.2 迁移前创建空表结构

数据迁移要求MySQL已经有表，但不能有业务数据。此时不要先启动systemd服务，手动执行一次：

```bash
cd /opt/it-portal
sudo IT_PORTAL_CONFIG_FILE=/opt/it-portal/business.local.json \
  .venv/bin/python -m alembic upgrade head
```

不要执行`portal.manage init-admin`，否则MySQL不再是空目标库，迁移工具会拒绝导入。

### 5.3 安装 SQL Server ODBC 驱动

仅当迁移命令在 Linux 上直接读取 SQL Server 时需要。先安装 Microsoft ODBC Driver 18：

```bash
. /etc/os-release

if [ "$ID" = "ubuntu" ]; then
  REPO_URL="https://packages.microsoft.com/config/ubuntu/${VERSION_ID}/packages-microsoft-prod.deb"
elif [ "$ID" = "debian" ]; then
  REPO_URL="https://packages.microsoft.com/config/debian/${VERSION_ID%%.*}/packages-microsoft-prod.deb"
else
  echo "请按 Microsoft 文档安装当前发行版的 msodbcsql18：$ID $VERSION_ID"
  exit 1
fi

curl -fsSL "$REPO_URL" -o /tmp/packages-microsoft-prod.deb
dpkg -i /tmp/packages-microsoft-prod.deb
apt-get update
ACCEPT_EULA=Y apt-get install -y msodbcsql18 unixodbc libgssapi-krb5-2
odbcinst -q -d
```

最后应看到 `[ODBC Driver 18 for SQL Server]`。其他发行版请参考 [Microsoft Linux ODBC 安装说明](https://learn.microsoft.com/sql/connect/odbc/linux-mac/installing-the-microsoft-odbc-driver-for-sql-server)。

### 5.4 配置SQL Server源连接

```bash
sudo mkdir -p /root/itportal-migration
sudo cp deploy/examples/migration-source.mssql.example.json \
  /root/itportal-migration/source.json
sudo chmod 0600 /root/itportal-migration/source.json
sudo nano /root/itportal-migration/source.json
```

填写SQL Server地址、1433端口、数据库名、账号、密码和ODBC驱动。源账号只需要读取门户数据库。使用经管理员批准的内网自签名证书例外时，配置为：

```json
"driver": "ODBC Driver 18 for SQL Server",
"trust_server_certificate": true
```

连接仍然加密，但不再校验自签名证书链。正式受信任证书环境应保持 `false`。

### 5.5 预检查和正式导入

先确认旧Windows门户已经停止，避免迁移时继续产生数据。

预检查：

```bash
cd /opt/it-portal
sudo .venv/bin/python -m portal.migrate_database \
  --source-config /root/itportal-migration/source.json \
  --target-config /opt/it-portal/business.local.json \
  --manifest /root/itportal-migration/preflight.json \
  --dry-run
```

正式导入：

```bash
sudo .venv/bin/python -m portal.migrate_database \
  --source-config /root/itportal-migration/source.json \
  --target-config /opt/it-portal/business.local.json \
  --manifest /root/itportal-migration/final.json
```

迁移工具会：

- 只读取SQL Server，不修改源数据库；
- 拒绝覆盖非空MySQL数据库；
- 保留UUID、账号密码哈希、权限和业务关联；
- 在MySQL事务中导入，失败时整体回滚；
- 逐表核对行数和SHA-256摘要；
- 不迁移历史登录会话，用户切换后需要重新登录。

当前 MySQL 目标结构包含 `0019_mysql_datetime_precision` 精度修复。它把早期功能表中的
`DATETIME` 调整为 `DATETIME(3)`，避免 SQL Server 时间值的毫秒在写入 MySQL 时丢失。
迁移工具明确允许停止写入的 SQL Server `0018_remove_portal_backup` 迁移到 MySQL
`0019_mysql_datetime_precision`；该差异只涉及目标数据库存储精度，不需要修改源数据库。

如果不想在Linux安装SQL Server ODBC驱动，也可以在原Windows服务器运行同一迁移命令，让目标配置连接Linux MySQL。

### 5.6 常见迁移错误

#### 找不到 ODBC Driver 18

如果提示 `Can't open lib 'ODBC Driver 18 for SQL Server'`，返回第 5.3 节安装驱动并执行 `odbcinst -q -d` 验证。

#### 自签名证书验证失败

如果提示 `certificate verify failed:self-signed certificate`，确认管理员已经批准信任该内网服务器证书，再按第 5.4 节设置 `trust_server_certificate: true`。

#### 首次建表出现 MySQL 1824

如果旧项目包在执行 `alembic upgrade head` 时出现：

```text
Failed to open the referenced table 'computer_assets'
```

这是旧迁移链缺少电脑与静态 IP 基础表造成的，不是 MySQL root 权限问题。更新项目中的
`migrations/versions/0002_ipam_base.py` 和 `0003_computer_lifecycle.py` 后，先查看当前位置：

```bash
cd /opt/it-portal
IT_PORTAL_CONFIG_FILE=/opt/it-portal/business.local.json \
  .venv/bin/python -m alembic current
```

如果显示 `0002_ledger`，可直接重新执行：

```bash
IT_PORTAL_CONFIG_FILE=/opt/it-portal/business.local.json \
  .venv/bin/python -m alembic upgrade head
```

第一次失败的 `CREATE TABLE computer_accessories` 不会在 MySQL 中留下可用的半张表，通常不需要重建数据库。如果当前位置不是 `0002_ledger`，先停止操作并检查 `alembic_version`，不要手工修改版本号或删除已有表。

#### `announcement_files` 校验失败

如果提示 `Target verification failed for announcement_files`，说明目标 MySQL 仍是旧的秒级 `DATETIME`。正式迁移已经整体回滚，不会留下半套数据。更新代码后执行：

```bash
IT_PORTAL_CONFIG_FILE=/opt/it-portal/business.local.json \
  .venv/bin/python -m alembic upgrade head

IT_PORTAL_CONFIG_FILE=/opt/it-portal/business.local.json \
  .venv/bin/python -m alembic current
```

目标应显示 `0019_mysql_datetime_precision (head)`，然后重新执行预检查和正式迁移。

## 6. 复制业务文件

把原Windows项目的：

```text
data/business/
```

整体复制到Linux项目中的：

```text
/opt/it-portal/data/business/
```

假设旧目录已经上传到`/tmp/itportal-business`：

```bash
sudo rsync -aH /tmp/itportal-business/ /opt/it-portal/data/business/
sudo chmod -R go-rwx /opt/it-portal/data/business
```

必须保留：

```text
knowledge/
knowledge-assets/
attachments/
wifi-secrets.key
ai-secrets.key
credentials/
```

这些文件包含知识库、公告/工单附件以及历史密文所需密钥。旧`business.db`和旧日志即使一起复制，也不会被MySQL连接使用；确认上线后再归档清理。

## 7. 安装并启动systemd服务

```bash
cd /opt/it-portal
sudo cp deploy/systemd/it-portal.service /etc/systemd/system/it-portal.service
sudo systemctl daemon-reload
sudo systemctl enable --now it-portal
```

查看状态和日志：

```bash
sudo systemctl status it-portal
sudo journalctl -u it-portal -n 200 --no-pager
sudo journalctl -u it-portal -f
curl http://127.0.0.1:8089/api/health
```

常用命令：

```bash
sudo systemctl start it-portal
sudo systemctl stop it-portal
sudo systemctl restart it-portal
```

## 8. 配置 Nginx 和局域网域名

门户正常运行后，先确认本机访问：

```bash
curl -i http://127.0.0.1:8089/api/health
```

安装 Nginx，并创建 `/etc/nginx/sites-available/it-portal`：

```nginx
server {
    listen 80;
    listen [::]:80;
    server_name portal.example.local;

    location / {
        proxy_pass http://127.0.0.1:8089;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_connect_timeout 10s;
        proxy_read_timeout 60s;
    }
}
```

启用并检查：

```bash
ln -s /etc/nginx/sites-available/it-portal /etc/nginx/sites-enabled/it-portal
nginx -t
systemctl reload nginx
ss -lntp | grep -E ':80|:8089'
curl -i -H 'Host: portal.example.local' http://127.0.0.1/api/health
```

公司内部 DNS 必须把域名解析到 Linux 服务器的局域网 IP；防火墙也必须允许可信网段访问 80/443。使用服务器 IP 直接测试时，可暂时把实际 IP 加到 `server_name`，不要在承载多个网站的 Nginx 上随意设置 `default_server`。

正式启用 HTTPS 后，在 `business.local.json` 中设置：

```json
"secure_cookie": true
```

## 9. 更新项目代码

新代码先解压到独立目录，再覆盖程序文件。不要覆盖现有配置、虚拟环境和业务数据：

```bash
systemctl stop it-portal

rsync -av \
  --exclude='.venv/' \
  --exclude='data/' \
  --exclude='business.local.json' \
  /opt/it-portal-update/ \
  /opt/it-portal/

cd /opt/it-portal
.venv/bin/python -m pip install -r requirements-business.txt
IT_PORTAL_CONFIG_FILE=/opt/it-portal/business.local.json \
  .venv/bin/python -m alembic upgrade head
systemctl start it-portal
```

升级前必须备份数据库、`data/business/` 和 `business.local.json`。

## 10. 验收

至少检查：

- 原管理员和普通员工能够登录；
- 工单、公告、知识库和附件完整；
- 网络台账、IP、电脑、耗材、人员和部门完整；
- 历史设备/Wi-Fi/线路/备忘录密码可以解密；
- AI配置仍可使用；
- `/api/health`显示数据库为MySQL。

确认正常后再把正式访问地址切换到Linux服务器。验收失败时停止Linux服务并重新启动原Windows门户。新Linux系统开放写入后不能直接切回旧SQL Server，否则新产生的数据会丢失。

## 11. 目录汇总

| 路径 | 用途 |
|---|---|
| `/opt/it-portal` | 项目代码、配置和Python虚拟环境 |
| `/opt/it-portal/business.local.json` | MySQL root连接配置 |
| `/opt/it-portal/data/business` | 知识库、附件、密钥和运行文件 |
| `/etc/systemd/system/it-portal.service` | systemd服务配置 |
