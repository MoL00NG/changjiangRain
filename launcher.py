# -*- coding: utf-8 -*-
"""首次启动时准备项目虚拟环境，并在其中重新启动主程序。

本模块只使用 Python 标准库，因此可以在安装 Selenium 等依赖前运行。
"""

import hashlib
import os
import subprocess
import sys
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parent
VENV_DIR = PROJECT_DIR / '.venv'
REQUIREMENTS = PROJECT_DIR / 'requirements.txt'


def _is_supported_python(executable):
    """要求 Python 3.10+ 及 64 位，满足 OCR/推理依赖要求。"""
    try:
        result = subprocess.run(
            [str(executable), '-c',
             'import struct,sys; print(f"{sys.version_info.major}.{sys.version_info.minor} '
             '{struct.calcsize(\'P\') * 8}")'],
            capture_output=True, text=True, timeout=10, check=True,
        )
        version, bits = result.stdout.strip().split()
        major, minor = map(int, version.split('.'))
        return (major, minor) >= (3, 10) and bits == '64'
    except (OSError, subprocess.SubprocessError, ValueError):
        return False


def _choose_python():
    """优先使用当前解释器；不满足要求时尝试 Windows py 启动器。"""
    if _is_supported_python(sys.executable):
        return sys.executable

    if os.name == 'nt':
        for version in ('3.14', '3.13', '3.12', '3.11', '3.10'):
            try:
                result = subprocess.run(
                    ['py', f'-{version}', '-c', 'import sys; print(sys.executable)'],
                    capture_output=True, text=True, timeout=10, check=True,
                )
                candidate = result.stdout.strip()
                if candidate and _is_supported_python(candidate):
                    return candidate
            except (OSError, subprocess.SubprocessError):
                continue
    return None


def _requirements_digest():
    return hashlib.sha256(REQUIREMENTS.read_bytes()).hexdigest()


def _venv_python():
    if os.name == 'nt':
        return VENV_DIR / 'Scripts' / 'python.exe'
    return VENV_DIR / 'bin' / 'python'


def ensure_project_environment():
    """准备依赖环境；需要时从项目虚拟环境重新启动本脚本。"""
    expected_python = _venv_python().resolve()
    already_in_project_venv = Path(sys.executable).resolve() == expected_python
    stamp = VENV_DIR / '.requirements.sha256'
    digest = _requirements_digest()
    if not _venv_python().exists():
        interpreter = _choose_python()
        if not interpreter:
            print('[错误] 未找到 64 位 Python 3.10 或更高版本。请安装 Python 后重新运行。')
            return False
        print('[信息] 首次运行，正在创建项目虚拟环境...')
        try:
            subprocess.run([interpreter, '-m', 'venv', str(VENV_DIR)], check=True)
        except (OSError, subprocess.CalledProcessError) as exc:
            print(f'[错误] 创建虚拟环境失败：{exc}')
            return False

    python = _venv_python()
    if not stamp.exists() or stamp.read_text(encoding='utf-8').strip() != digest:
        print('[信息] 正在安装或更新项目依赖，请稍候...')
        try:
            subprocess.run([str(python), '-m', 'pip', 'install', '--upgrade', 'pip'], check=True)
            subprocess.run([str(python), '-m', 'pip', 'install', '-r', str(REQUIREMENTS)], check=True)
            stamp.write_text(digest, encoding='utf-8')
        except (OSError, subprocess.CalledProcessError) as exc:
            print(f'[错误] 安装依赖失败：{exc}')
            print('[信息] 检查网络后重新运行即可继续安装。')
            return False

    if already_in_project_venv:
        return True

    print('[信息] 正在切换到项目虚拟环境...')
    try:
        result = subprocess.run([str(python), str(Path(__file__).with_name('main.py')),
                                 *sys.argv[1:]], cwd=str(PROJECT_DIR), check=False)
        raise SystemExit(result.returncode)
    except OSError as exc:
        print(f'[错误] 无法启动虚拟环境中的程序：{exc}')
        return False
