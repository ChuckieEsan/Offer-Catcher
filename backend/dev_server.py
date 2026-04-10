#!/usr/bin/env python
"""开发服务器启动脚本

统一启动 FastAPI 服务和所有 Worker 进程。
支持文件变化时自动重启所有进程。

用法:
    PYTHONPATH=. uv run python dev_server.py

依赖:
    uv add watchdog --group dev
"""

import os
import sys
import signal
import subprocess
import time
from pathlib import Path
from typing import Dict

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler, FileSystemEvent

# 进程配置
PROCESSES = {
    "web": {
        "cmd": ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"],
        "reload": False,  # uvicorn 自己处理 reload
    },
    "answer_worker": {
        "cmd": ["uv", "run", "python", "workers/answer_worker.py"],
        "reload": True,
    },
    "extract_worker": {
        "cmd": ["uv", "run", "python", "workers/extract_worker.py"],
        "reload": True,
    },
    "clustering_worker": {
        "cmd": ["uv", "run", "python", "workers/clustering_worker.py"],
        "reload": True,
    },
}

# 监听的目录
WATCH_DIRS = ["app", "workers"]
# 忽略的文件模式
IGNORE_PATTERNS = [
    "__pycache__",
    ".pyc",
    ".pyo",
    ".git",
    ".venv",
    "node_modules",
    ".log",
]

# 日志目录
LOG_DIR = Path(__file__).parent / "logs"


class ProcessManager:
    """进程管理器"""

    def __init__(self):
        self.processes: Dict[str, subprocess.Popen] = {}
        self.log_files: Dict[str, Path] = {}
        self.running = True
        self.base_dir = Path(__file__).parent

        # 创建日志目录
        self._setup_log_dir()

    def _setup_log_dir(self):
        """创建日志目录"""
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        print(f"[Logs] 日志目录: {LOG_DIR}")

    def _get_log_file(self, name: str) -> Path:
        """获取进程日志文件路径"""
        return LOG_DIR / f"{name}.log"

    def start_all(self):
        """启动所有进程"""
        os.environ["PYTHONPATH"] = str(self.base_dir)

        for name, config in PROCESSES.items():
            self.start_process(name, config)

    def start_process(self, name: str, config: dict):
        """启动单个进程"""
        cmd = config["cmd"]
        log_file = self._get_log_file(name)
        self.log_files[name] = log_file

        # 清空日志文件
        log_file.write_text("")
        print(f"[{name}] Starting: {' '.join(cmd)}")
        print(f"[{name}] Log file: {log_file}")

        try:
            proc = subprocess.Popen(
                cmd,
                cwd=self.base_dir,
                env=os.environ.copy(),
                stdout=open(log_file, "a"),
                stderr=subprocess.STDOUT,  # 合并 stderr 到 stdout
            )
            self.processes[name] = proc
        except Exception as e:
            print(f"[{name}] Failed to start: {e}")

    def stop_all(self):
        """停止所有进程"""
        self.running = False

        for name, proc in self.processes.items():
            if proc.poll() is None:  # 进程仍在运行
                print(f"[{name}] Stopping...")
                proc.terminate()

                # 等待进程结束
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    print(f"[{name}] Force killing...")
                    proc.kill()

                # 关闭日志文件句柄
                if proc.stdout:
                    proc.stdout.close()

        self.processes.clear()
        self.log_files.clear()

    def restart_workers(self):
        """重启所有 workers（不重启 web）"""
        print("\n[Reload] Restarting workers due to file change...")

        for name, config in PROCESSES.items():
            if not config["reload"]:
                continue

            # 停止现有进程
            if name in self.processes:
                proc = self.processes[name]
                if proc.poll() is None:
                    proc.terminate()
                    # 关闭日志文件句柄
                    if proc.stdout:
                        proc.stdout.close()
                    try:
                        proc.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        proc.kill()

            # 重新启动
            time.sleep(0.5)  # 给一点时间让端口释放
            self.start_process(name, config)

        print("[Reload] Workers restarted\n")


class ReloadHandler(FileSystemEventHandler):
    """文件变化处理器"""

    def __init__(self, manager: ProcessManager):
        self.manager = manager
        self.last_reload_time = 0
        self.reload_cooldown = 2.0  # 重载冷却时间（秒）

    def on_modified(self, event: FileSystemEvent):
        """文件修改事件"""
        if not event.is_directory:
            path = Path(event.src_path)

            # 检查是否是 Python 文件
            if not path.suffix == ".py":
                return

            # 检查是否在忽略模式中
            for pattern in IGNORE_PATTERNS:
                if pattern in str(path):
                    return

            # 冷却时间检查，避免频繁重启
            current_time = time.time()
            if current_time - self.last_reload_time < self.reload_cooldown:
                return

            self.last_reload_time = current_time
            print(f"[Watchdog] File changed: {path}")

            if self.manager.running:
                self.manager.restart_workers()


def main():
    """主函数"""
    print("=" * 60)
    print("Offer-Catcher Dev Server")
    print("=" * 60)
    print("Starting all services...")
    print()
    print(f"日志目录: {LOG_DIR}")
    print("查看日志: tail -f logs/<process_name>.log")
    print()

    manager = ProcessManager()

    # 设置信号处理器
    def signal_handler(sig, frame):
        print("\nReceived shutdown signal...")
        manager.stop_all()
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # 启动所有进程
    manager.start_all()

    # 设置文件监听
    observer = Observer()
    handler = ReloadHandler(manager)

    base_dir = Path(__file__).parent
    for watch_dir in WATCH_DIRS:
        watch_path = base_dir / watch_dir
        if watch_path.exists():
            observer.schedule(handler, str(watch_path), recursive=True)
            print(f"[Watchdog] Watching: {watch_path}")

    observer.start()
    print("[Watchdog] File watcher started")
    print()
    print("All services started. Press Ctrl+C to stop.")
    print("=" * 60)
    print()

    try:
        # 主循环：监控进程状态
        while manager.running:
            for name, proc in manager.processes.items():
                if proc.poll() is not None:
                    print(f"[{name}] Process exited with code: {proc.returncode}")
                    # 如果进程意外退出，可以选择重启
                    if manager.running:
                        config = PROCESSES.get(name)
                        if config:
                            print(f"[{name}] Restarting...")
                            manager.start_process(name, config)

            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        observer.stop()
        observer.join()
        manager.stop_all()
        print("Dev server stopped")


if __name__ == "__main__":
    main()