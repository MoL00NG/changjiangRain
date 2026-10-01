# -*- coding: utf-8 -*-
"""终端输出工具：统一格式与配色（无表情符号，支持管道重定向时自动关闭颜色）"""

import os
import sys


def _enable_ansi_on_windows():
    """Windows 下启用 ANSI 转义序列（Windows 10+ 有效，失败则忽略）"""
    if sys.platform == 'win32':
        try:
            import ctypes
            kernel32 = ctypes.windll.kernel32
            kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)
        except Exception:
            pass


_enable_ansi_on_windows()

# 仅当输出到真实终端且未设置 NO_COLOR 时启用颜色
USE_COLOR = sys.stdout.isatty() and not os.environ.get('NO_COLOR')


def _paint(text, code):
    if not USE_COLOR:
        return text
    return f'\033[{code}m{text}\033[0m'


def section(title):
    """区块标题"""
    print('=' * 56)
    print(_paint(title, '1;36'))
    print('=' * 56)


def info(msg):
    """普通信息（青色）"""
    print(_paint('[信息] ', '36') + str(msg))


def ok(msg):
    """成功信息（绿色）"""
    print(_paint('[完成] ', '32') + str(msg))


def warn(msg):
    """警告信息（黄色）"""
    print(_paint('[警告] ', '33') + str(msg))


def error(msg):
    """错误信息（红色）"""
    print(_paint('[错误] ', '31') + str(msg))


def progress(msg):
    """进度信息（青色）"""
    print(_paint('[进度] ', '36') + str(msg))
