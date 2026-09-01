#!/usr/bin/env python3
"""
PyInstaller Sidecar 冻结打包脚本
将 backend/app.py 编译为独立二进制可执行文件，存放在 src-tauri/binaries 目录。
"""

import sys
import subprocess
import shutil
from pathlib import Path

def main():
    project_root = Path(__file__).parent.parent.resolve()
    pyinstaller_cache = project_root / ".cache" / "pyinstaller"
    pyinstaller_cache.mkdir(parents=True, exist_ok=True)
    import os
    os.environ["PYINSTALLER_CONFIG_DIR"] = str(pyinstaller_cache)

    temp_dir = project_root.parent / ".cache" / "temp"
    temp_dir.mkdir(parents=True, exist_ok=True)
    os.environ["TEMP"] = str(temp_dir)
    os.environ["TMP"] = str(temp_dir)

    tauri_binaries_dir = project_root / "src-tauri" / "binaries"
    tauri_binaries_dir.mkdir(parents=True, exist_ok=True)

    target_triple = "x86_64-pc-windows-msvc"
    binary_name = f"boss_backend-{target_triple}.exe"

    print(f"[BUILD] 打包 Python Sidecar: {binary_name} ...")
    
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm",
        "--onefile",
        "--name", f"boss_backend-{target_triple}",
        "--distpath", str(tauri_binaries_dir.resolve()),
        "--workpath", str((project_root / "build_temp").resolve()),
        "--specpath", str((project_root / "build_temp").resolve()),
        "--collect-all=backend",
        "--hidden-import=fastapi",
        "--hidden-import=uvicorn",
        "--hidden-import=uvicorn.logging",
        "--hidden-import=uvicorn.loops",
        "--hidden-import=uvicorn.loops.auto",
        "--hidden-import=uvicorn.protocols",
        "--hidden-import=uvicorn.protocols.http",
        "--hidden-import=uvicorn.protocols.http.auto",
        "--hidden-import=uvicorn.protocols.websockets",
        "--hidden-import=uvicorn.protocols.websockets.auto",
        "--hidden-import=uvicorn.lifespan",
        "--hidden-import=uvicorn.lifespan.on",
        "--hidden-import=sqlite3",
        "--hidden-import=playwright",
        str(project_root / "backend" / "app.py")
    ]

    print(f"[RUN] {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=project_root)
    output_file = tauri_binaries_dir / binary_name
    if result.returncode == 0 and output_file.exists():
        print(f"\n[SUCCESS] Sidecar 编译成功: {output_file} ({output_file.stat().st_size / 1024 / 1024:.2f} MB)")
    else:
        print(f"\n[ERROR] Sidecar 打包失败或输出文件不存在，退出码: {result.returncode}")
        sys.exit(1)

if __name__ == "__main__":
    main()
