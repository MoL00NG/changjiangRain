# -*- coding: utf-8 -*-
"""OCR 模型手动安装工具：解决网络下载失败/证书校验失败的问题。

用法：
    python install_models.py

作用：从 HuggingFace 镜像站下载 cnocr/cnstd 所需模型，保存到本地缓存目录
     （Windows: %APPDATA%\\cnocr 与 %APPDATA%\\cnstd），
     之后运行 python main.py 即可正常初始化 OCR，不再需要联网下载。
"""

import os
import sys
import time
import zipfile

import requests

try:
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
except Exception:
    pass

MIRROR = os.environ.get('HF_ENDPOINT', 'https://hf-mirror.com')
APPDATA = os.environ.get('APPDATA') or os.path.join(os.path.expanduser('~'), 'AppData', 'Roaming')

# 识别模型（cnocr）：仓库里是 zip 包，需要解压
REC_DIR = os.path.join(APPDATA, 'cnocr', '2.3', 'densenet_lite_136-gru')
REC_ONNX = os.path.join(REC_DIR, 'cnocr-v2.3-densenet_lite_136-gru-epoch=004-ft-model.onnx')
REC_ZIP_URL = (f'{MIRROR}/breezedeus/cnstd-cnocr-models/resolve/main/'
               'models/cnocr/2.3/densenet_lite_136-gru-onnx.zip')

# 检测模型（cnstd）：独立仓库，根目录直接是模型文件
DET_DIR = os.path.join(APPDATA, 'cnstd', '1.2', 'ppocr', 'multi_PP-OCRv6_det_small')
DET_BASE = f'{MIRROR}/breezedeus/cnstd-ppocr-multi_PP-OCRv6_det_small/resolve/main'
DET_FILES = [
    ('PP-OCRv6_det_small.onnx', 8 * 1024 * 1024),
    ('config.yaml', 0),
    ('README.md', 0),
]


def download(url, dest, min_size=0, retries=3):
    """下载单个文件到目标路径；已存在且大小达标则跳过"""
    if os.path.exists(dest) and os.path.getsize(dest) >= min_size:
        print(f'[跳过] 已存在: {dest}')
        return True
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    for attempt in range(1, retries + 1):
        try:
            print(f'[下载] {url}（第 {attempt}/{retries} 次）')
            r = requests.get(url, stream=True, timeout=60, verify=False)
            r.raise_for_status()
            total = int(r.headers.get('Content-Length', 0))
            done = 0
            tmp = dest + '.tmp'
            with open(tmp, 'wb') as f:
                for chunk in r.iter_content(1024 * 256):
                    f.write(chunk)
                    done += len(chunk)
                    if total:
                        print(f'\r   进度 {done * 100 // total}%', end='', flush=True)
            print()
            os.replace(tmp, dest)
            if os.path.getsize(dest) >= min_size:
                print(f'[完成] {os.path.basename(dest)}')
                return True
            print('[警告] 文件大小异常，删除后重试')
            os.remove(dest)
        except Exception as e:
            print(f'[错误] {e}')
            time.sleep(2)
    return False


def install_rec_model():
    """下载并解压识别模型"""
    if os.path.exists(REC_ONNX) and os.path.getsize(REC_ONNX) > 10 * 1024 * 1024:
        print(f'[跳过] 识别模型已存在: {REC_ONNX}')
        return True
    zip_path = os.path.join(os.path.dirname(REC_DIR), 'densenet_lite_136-gru-onnx.zip')
    if not download(REC_ZIP_URL, zip_path, 10 * 1024 * 1024):
        return False
    try:
        os.makedirs(REC_DIR, exist_ok=True)
        with zipfile.ZipFile(zip_path) as z:
            z.extractall(os.path.join(APPDATA, 'cnocr', '2.3'))
        os.remove(zip_path)
        if os.path.exists(REC_ONNX):
            print(f'[完成] 识别模型已解压: {REC_ONNX}')
            return True
        print('[警告] 解压后未找到模型文件')
        return False
    except Exception as e:
        print(f'[错误] 解压失败: {e}')
        return False


def install_det_model():
    """下载检测模型文件"""
    ok = True
    for name, min_size in DET_FILES:
        ok = download(f'{DET_BASE}/{name}', os.path.join(DET_DIR, name), min_size) and ok
    return ok


def main():
    print('=' * 56)
    print('OCR 模型手动安装工具')
    print('=' * 56)
    print(f'镜像源: {MIRROR}')

    rec_ok = install_rec_model()
    det_ok = install_det_model()

    print()
    if rec_ok and det_ok:
        print('[完成] 所有模型已就绪，现在可以运行: python main.py')
        sys.exit(0)
    print('[警告] 部分模型下载失败，请检查网络后重试')
    print('也可用浏览器手动打开上述链接下载，把文件放到提示的目录后重新运行本脚本。')
    sys.exit(1)


if __name__ == '__main__':
    main()
