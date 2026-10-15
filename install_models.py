# -*- coding: utf-8 -*-
"""OCR 模型手动安装工具：解决网络下载失败/证书校验失败的问题。

用法：
    python install_models.py

作用：从 HuggingFace 镜像站下载 cnocr/cnstd 所需模型，保存到本地缓存目录
     （Windows: %APPDATA%\\cnocr 与 %APPDATA%\\cnstd），
     之后运行 python main.py 即可正常初始化 OCR，不再需要联网下载。
"""

import hashlib
import os
import stat
import sys
import tempfile
import time
import zipfile
from pathlib import Path

import requests

MIRROR = os.environ.get('HF_ENDPOINT', 'https://hf-mirror.com')
APPDATA = os.environ.get('APPDATA') or os.path.join(os.path.expanduser('~'), 'AppData', 'Roaming')

# 识别模型（cnocr）：仓库里是 zip 包，需要解压
REC_DIR = os.path.join(APPDATA, 'cnocr', '2.3', 'densenet_lite_136-gru')
REC_ONNX = os.path.join(REC_DIR, 'cnocr-v2.3-densenet_lite_136-gru-epoch=004-ft-model.onnx')
REC_ZIP_URL = (f'{MIRROR}/breezedeus/cnstd-cnocr-models/resolve/main/'
               'models/cnocr/2.3/densenet_lite_136-gru-onnx.zip')
REC_ZIP_SHA256 = '44a92fbaea5f3df2f9dcc63ba17af0e9fc8b208027ff33578e5e7e7fe09b56e2'

# 检测模型（cnstd）：独立仓库，根目录直接是模型文件
DET_DIR = os.path.join(APPDATA, 'cnstd', '1.2', 'ppocr', 'multi_PP-OCRv6_det_small')
DET_BASE = f'{MIRROR}/breezedeus/cnstd-ppocr-multi_PP-OCRv6_det_small/resolve/main'
DET_FILES = [
    ('PP-OCRv6_det_small.onnx', 8 * 1024 * 1024,
     '090f04abcd9d9a7498bc4ebf677e4cb9bdce1fe4197ddb7e529f1ef44e1ff94f'),
    ('config.yaml', 0, None),
    ('README.md', 0, None),
]


def _sha256(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def _is_verified_file(path, min_size=0, expected_sha256=None):
    if not os.path.exists(path) or os.path.getsize(path) < min_size:
        return False
    if expected_sha256 and _sha256(path).lower() != expected_sha256.lower():
        print(f'[错误] 文件校验失败: {path}')
        print('       请手动删除该文件后重新运行，切勿使用来源不明的模型文件。')
        return False
    return True


def download(url, dest, min_size=0, expected_sha256=None, retries=3):
    """通过 HTTPS 下载文件，并在替换目标前进行大小与 SHA-256 校验。"""
    if _is_verified_file(dest, min_size, expected_sha256):
        print(f'[跳过] 已存在且校验通过: {dest}')
        return True
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    for attempt in range(1, retries + 1):
        tmp = None
        try:
            print(f'[下载] {url}（第 {attempt}/{retries} 次）')
            with requests.get(url, stream=True, timeout=(15, 60)) as response:
                response.raise_for_status()
                total = int(response.headers.get('Content-Length', 0))
                done = 0
                with tempfile.NamedTemporaryFile(
                        'wb', delete=False, dir=os.path.dirname(dest),
                        prefix='.download-', suffix='.tmp') as stream:
                    tmp = stream.name
                    for chunk in response.iter_content(1024 * 256):
                        if not chunk:
                            continue
                        stream.write(chunk)
                        done += len(chunk)
                        if total:
                            print(f'\r   进度 {done * 100 // total}%', end='', flush=True)
            print()
            if _is_verified_file(tmp, min_size, expected_sha256):
                os.replace(tmp, dest)
                tmp = None
                print(f'[完成] {os.path.basename(dest)}')
                return True
            print('[警告] 下载文件未通过完整性校验，未写入模型目录。')
        except Exception as e:
            print(f'[错误] {e}')
            time.sleep(2)
        finally:
            if tmp and os.path.exists(tmp):
                os.remove(tmp)
    return False


def _safe_extract(zip_path, destination):
    """拒绝 ZIP Slip、符号链接与异常膨胀文件，再解压已校验的模型压缩包。"""
    target = Path(destination).resolve()
    try:
        with zipfile.ZipFile(zip_path) as archive:
            entries = archive.infolist()
            total_size = sum(entry.file_size for entry in entries)
            if total_size > 256 * 1024 * 1024:
                raise ValueError('压缩包解压后的总大小异常')
            for entry in entries:
                output = (target / entry.filename).resolve()
                if output != target and target not in output.parents:
                    raise ValueError(f'压缩包包含越界路径: {entry.filename}')
                mode = entry.external_attr >> 16
                if stat.S_ISLNK(mode):
                    raise ValueError(f'压缩包包含符号链接: {entry.filename}')
                if entry.compress_size and entry.file_size / entry.compress_size > 150:
                    raise ValueError(f'压缩包条目压缩比异常: {entry.filename}')
            archive.extractall(target)
        return True
    except (OSError, ValueError, zipfile.BadZipFile) as exc:
        print(f'[错误] 安全解压失败: {exc}')
        return False


def install_rec_model():
    """下载并解压识别模型"""
    if os.path.exists(REC_ONNX) and os.path.getsize(REC_ONNX) > 10 * 1024 * 1024:
        print(f'[跳过] 识别模型已存在: {REC_ONNX}')
        return True
    zip_path = os.path.join(os.path.dirname(REC_DIR), 'densenet_lite_136-gru-onnx.zip')
    if not download(REC_ZIP_URL, zip_path, 10 * 1024 * 1024, REC_ZIP_SHA256):
        return False
    try:
        os.makedirs(REC_DIR, exist_ok=True)
        if not _safe_extract(zip_path, os.path.join(APPDATA, 'cnocr', '2.3')):
            return False
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
    for name, min_size, expected_sha256 in DET_FILES:
        ok = download(
            f'{DET_BASE}/{name}', os.path.join(DET_DIR, name), min_size, expected_sha256
        ) and ok
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
