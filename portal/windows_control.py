"""Single Windows operator entry point used by portal.bat."""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from urllib.error import URLError
from urllib.request import urlopen


ROOT = Path(__file__).resolve().parent.parent
DATA_ROOT = ROOT / "data"
RUNTIME_ROOT = DATA_ROOT / "runtime"
LOG_ROOT = DATA_ROOT / "logs"
STATE_FILE = RUNTIME_ROOT / "portal-process.json"
CONFIG_FILE = ROOT / "business.local.json"
CONFIG_TEMPLATE = ROOT / "business.example.json"


def _listener_pid(port: int) -> int | None:
    result = subprocess.run(
        ["netstat", "-ano", "-p", "TCP"],
        capture_output=True,
        text=True,
        errors="replace",
        check=False,
    )
    for raw_line in result.stdout.splitlines():
        parts = raw_line.split()
        if len(parts) < 5 or parts[-2].upper() != "LISTENING":
            continue
        local_address = parts[1]
        try:
            local_port = int(local_address.rsplit(":", 1)[1])
            process_id = int(parts[-1])
        except (ValueError, IndexError):
            continue
        if local_port == port:
            return process_id
    return None


def _healthy(port: int) -> bool:
    try:
        with urlopen(f"http://127.0.0.1:{port}/api/health", timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8"))
        return payload.get("status") == "ok"
    except (OSError, URLError, ValueError, json.JSONDecodeError):
        return False


def _read_state() -> dict | None:
    if not STATE_FILE.is_file():
        return None
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"运行状态文件格式无效：{STATE_FILE}") from exc


def _write_state(state: dict) -> None:
    RUNTIME_ROOT.mkdir(parents=True, exist_ok=True)
    temporary = STATE_FILE.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, STATE_FILE)


def _configuration() -> dict:
    if not CONFIG_FILE.is_file():
        raise RuntimeError("缺少 business.local.json，请先运行：portal.bat deploy")
    try:
        return json.loads(CONFIG_FILE.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise RuntimeError("business.local.json 不是有效的 JSON 配置文件。") from exc


def _process_name(process_id: int) -> str:
    result = subprocess.run(
        ["tasklist", "/FI", f"PID eq {process_id}", "/FO", "CSV", "/NH"],
        capture_output=True,
        text=True,
        errors="replace",
        check=False,
    )
    line = result.stdout.strip()
    if not line.startswith('"'):
        return ""
    return line.split('","', 1)[0].strip('"')


def _cleanup_console_logs(retention_days: int) -> None:
    if not LOG_ROOT.is_dir():
        return
    cutoff = datetime.now().timestamp() - timedelta(days=max(1, retention_days)).total_seconds()
    for path in LOG_ROOT.glob("portal-console-*.log"):
        try:
            if path.is_file() and path.stat().st_mtime < cutoff:
                path.unlink()
        except OSError:
            pass


def command_deploy(args: argparse.Namespace) -> int:
    if sys.version_info < (3, 10):
        raise RuntimeError(f"需要 Python 3.10 或更高版本，当前版本：{sys.version.split()[0]}")

    for module_name in ("fastapi", "uvicorn", "sqlalchemy", "alembic", "multipart", "cryptography", "ldap3", "openpyxl"):
        __import__(module_name)

    if not CONFIG_FILE.exists():
        CONFIG_FILE.write_bytes(CONFIG_TEMPLATE.read_bytes())
        print("已根据模板生成 business.local.json。")
        print("请填写数据库和集成配置，然后重新执行部署。")
        return 2

    config = _configuration()
    database = config.get("database") or {}
    if str(database.get("engine", "")).lower() == "mssql":
        import pyodbc

        configured_driver = str(database.get("driver") or "")
        if configured_driver not in pyodbc.drivers():
            raise RuntimeError(f"未安装配置中指定的 SQL Server ODBC 驱动：{configured_driver}")
        print(f"已检测到 SQL Server ODBC 驱动：{configured_driver}")

    print("正在执行数据库结构迁移……")
    result = subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=ROOT, check=False)
    if result.returncode:
        raise RuntimeError("数据库迁移失败，服务未启动。")

    if args.initialize_admin:
        result = subprocess.run([sys.executable, "-m", "portal.manage", "init-admin"], cwd=ROOT, check=False)
        if result.returncode:
            raise RuntimeError("管理员初始化失败。")

    RUNTIME_ROOT.mkdir(parents=True, exist_ok=True)
    LOG_ROOT.mkdir(parents=True, exist_ok=True)
    print("Windows 部署检查已完成。")
    print("启动：portal.bat start")
    print("状态：portal.bat status")
    print("停止：portal.bat stop")
    return 0


def command_start(args: argparse.Namespace) -> int:
    _configuration()
    listener = _listener_pid(args.port)
    if listener is not None:
        if _healthy(args.port):
            print(f"IT 门户已在端口 {args.port} 运行，进程号：{listener}。")
            return 0
        raise RuntimeError(f"端口 {args.port} 已被进程 {listener} 占用。")

    config = _configuration()
    _cleanup_console_logs(int(config.get("log_retention_days", 90)))
    RUNTIME_ROOT.mkdir(parents=True, exist_ok=True)
    LOG_ROOT.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    stdout_log = LOG_ROOT / f"portal-console-{timestamp}.stdout.log"
    stderr_log = LOG_ROOT / f"portal-console-{timestamp}.stderr.log"
    creation_flags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW

    print(f"正在后台启动 IT 门户，监听地址：{args.bind_address}:{args.port}……")
    with stdout_log.open("ab") as stdout_handle, stderr_log.open("ab") as stderr_handle:
        process = subprocess.Popen(
            [sys.executable, "-m", "portal", "--host", args.bind_address, "--port", str(args.port)],
            cwd=ROOT,
            stdin=subprocess.DEVNULL,
            stdout=stdout_handle,
            stderr=stderr_handle,
            creationflags=creation_flags,
            close_fds=True,
        )

    deadline = time.monotonic() + args.startup_timeout
    listener = None
    while time.monotonic() < deadline:
        time.sleep(0.5)
        listener = _listener_pid(args.port)
        if listener is not None and _healthy(args.port):
            break
        if process.poll() is not None:
            break

    if listener is None or not _healthy(args.port):
        if process.poll() is None:
            process.terminate()
        detail = ""
        try:
            detail = "\n".join(stderr_log.read_text(encoding="utf-8", errors="replace").splitlines()[-20:])
        except OSError:
            pass
        raise RuntimeError(f"IT 门户未能正常启动，请检查日志：{stderr_log}\n{detail}")

    state = {
        "process_id": listener,
        "launcher_process_id": process.pid,
        "port": args.port,
        "bind_address": args.bind_address,
        "project_root": str(ROOT),
        "started_at": datetime.now().astimezone().isoformat(),
        "stdout_log": str(stdout_log),
        "stderr_log": str(stderr_log),
    }
    _write_state(state)
    print(f"IT 门户启动成功，进程号：{listener}")
    print(f"本机访问地址：http://127.0.0.1:{args.port}/")
    return 0


def command_status(args: argparse.Namespace) -> int:
    state = _read_state()
    port = args.port or int((state or {}).get("port", 8089))
    listener = _listener_pid(port)
    if listener is None:
        print(f"IT 门户已停止，端口 {port} 当前没有监听进程。")
        if state:
            print(f"发现过期的运行状态文件：{STATE_FILE}")
        return 1


    managed = bool(
        state
        and int(state.get("process_id", -1)) == listener
        and Path(str(state.get("project_root", ""))).resolve() == ROOT.resolve()
    )
    healthy = _healthy(port)
    print("监听状态：正常")
    print(f"进程号：  {listener}")
    print(f"端口：    {port}")
    print(f"受管状态：{'是' if managed else '否'}")
    print(f"健康状态：{'正常' if healthy else '异常'}")
    if state:
        print(f"启动时间：{state.get('started_at', '')}")
        print(f"标准输出：{state.get('stdout_log', '')}")
        print(f"错误日志：{state.get('stderr_log', '')}")
    if not managed:
        print("当前服务不是后台受管模式；如果通过菜单选择了前台启动，请回到启动窗口按 Ctrl+C 停止。")
    return 0 if healthy else 2


def command_stop(_args: argparse.Namespace) -> int:
    state = _read_state()
    if not state:
        listener = _listener_pid(8089)
        if listener is not None:
            raise RuntimeError(f"端口 8089 正由进程 {listener} 使用，但它不是后台受管实例。如果使用了前台启动，请回到启动窗口按 Ctrl+C 停止。")
        print("IT 门户已经处于停止状态。")
        return 0

    if Path(str(state.get("project_root", ""))).resolve() != ROOT.resolve():
        raise RuntimeError("运行状态属于其他项目目录，未停止任何进程。")
    port = int(state["port"])
    process_id = int(state["process_id"])
    listener = _listener_pid(port)
    if listener is None:
        STATE_FILE.unlink(missing_ok=True)
        print("IT 门户未在监听，已清理过期的运行状态文件。")
        return 0
    if listener != process_id:
        raise RuntimeError(f"端口 {port} 当前属于进程 {listener}，与受管进程 {process_id} 不一致，未执行停止操作。")
    if not _process_name(process_id).lower().startswith("python"):
        raise RuntimeError(f"受管进程 {process_id} 已不是 Python 进程，未执行停止操作。")

    print(f"正在停止 IT 门户，进程号：{process_id}……")
    result = subprocess.run(["taskkill", "/PID", str(process_id), "/T", "/F"], capture_output=True, check=False)
    if result.returncode:
        raise RuntimeError(f"无法停止 IT 门户进程 {process_id}。")
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline and _listener_pid(port) is not None:
        time.sleep(0.25)
    if _listener_pid(port) is not None:
        raise RuntimeError("IT 门户在 15 秒内未停止，已保留运行状态供排查。")
    STATE_FILE.unlink(missing_ok=True)
    print("IT 门户已成功停止。")
    return 0


def command_foreground(args: argparse.Namespace) -> int:
    _configuration()
    listener = _listener_pid(args.port)
    if listener is not None:
        raise RuntimeError(f"端口 {args.port} 已被进程 {listener} 占用。")
    print(f"正在前台启动 IT 门户：http://{args.bind_address}:{args.port}")
    print("按 Ctrl+C 可以停止前台服务。")
    return subprocess.call(
        [sys.executable, "-m", "portal", "--host", args.bind_address, "--port", str(args.port)],
        cwd=ROOT,
    )


def command_usage(_args: argparse.Namespace) -> int:
    print("用法：")
    print("  portal.bat deploy [-InitializeAdmin] [-SkipDependencyInstall]  部署或升级")
    print("  portal.bat start [-Port 8089] [-BindAddress 0.0.0.0]           后台启动")
    print("  portal.bat status [-Port 8089]                                查看状态")
    print("  portal.bat stop                                               停止服务")
    print("  portal.bat foreground [-Port 8089] [-BindAddress 0.0.0.0]      前台调试")
    return 0


def command_menu(_args: argparse.Namespace) -> int:
    print()
    print("IT 门户 - Windows 运维工具")
    print("=" * 40)
    print("1. 后台启动")
    print("2. 查看运行状态")
    print("3. 停止服务")
    print("4. 前台启动（调试）")
    print("5. 部署或升级")
    print("0. 退出")
    print()
    choice = input("请选择操作：").strip()
    commands = {"1": "start", "2": "status", "3": "stop", "4": "foreground", "5": "deploy"}
    if choice == "0":
        return 0
    command = commands.get(choice)
    if command is None:
        print("输入无效，请重新运行后选择 0 到 5。")
        input("按回车键退出……")
        return 2
    result = subprocess.run(
        [os.environ.get("COMSPEC", "cmd.exe"), "/d", "/c", str(ROOT / "portal.bat"), command],
        cwd=ROOT,
        check=False,
    )
    input("按回车键退出……")
    return result.returncode


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="IT 门户 Windows 运维工具")
    subparsers = parser.add_subparsers(dest="command", required=True)

    deploy = subparsers.add_parser("deploy")
    deploy.add_argument("-InitializeAdmin", "--initialize-admin", action="store_true")
    deploy.add_argument("-SkipDependencyInstall", "--skip-dependency-install", action="store_true")
    deploy.set_defaults(handler=command_deploy)

    for name, handler in (("start", command_start), ("foreground", command_foreground)):
        command = subparsers.add_parser(name)
        command.add_argument("-Port", "--port", type=int, default=8089)
        command.add_argument("-BindAddress", "--bind-address", default="0.0.0.0")
        if name == "start":
            command.add_argument("-StartupTimeout", "--startup-timeout", type=int, default=45)
        command.set_defaults(handler=handler)

    status = subparsers.add_parser("status")
    status.add_argument("-Port", "--port", type=int, default=0)
    status.set_defaults(handler=command_status)

    stop = subparsers.add_parser("stop")
    stop.set_defaults(handler=command_stop)

    menu = subparsers.add_parser("menu")
    menu.set_defaults(handler=command_menu)

    usage = subparsers.add_parser("usage")
    usage.set_defaults(handler=command_usage)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        return int(args.handler(args))
    except KeyboardInterrupt:
        return 130
    except Exception as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
