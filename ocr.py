# -*- coding: utf-8 -*-
"""OCR 识别与文本清理：截图识别、题干/选项整理、噪音过滤"""

import os
import re
import time

import numpy as np
from PIL import Image, ImageEnhance

from util import ok, warn, error, progress

# ==================== OCR 初始化 ====================
progress("正在初始化 OCR (cnocr)...")
try:
    import cnocr  # noqa: F401  先单独验证 cnocr 是否安装
except ImportError as e:
    error(f"缺少 OCR 依赖 cnocr（具体原因: {e}）")
    error("请先安装：pip install cnocr onnxruntime")
    exit(1)

# 国内网络访问 HuggingFace 常出现证书校验失败/下载中断，默认改用镜像站下载模型
os.environ.setdefault('HF_ENDPOINT', 'https://hf-mirror.com')
os.environ.setdefault('HF_HUB_DISABLE_SYMLINKS_WARNING', '1')


def _local_model_paths():
    """本地模型缓存路径（Windows: %APPDATA%\\cnocr 与 %APPDATA%\\cnstd）"""
    base = os.environ.get('APPDATA') or os.path.join(os.path.expanduser('~'), 'AppData', 'Roaming')
    rec = os.path.join(base, 'cnocr', '2.3', 'densenet_lite_136-gru',
                       'cnocr-v2.3-densenet_lite_136-gru-epoch=004-ft-model.onnx')
    det = os.path.join(base, 'cnstd', '1.2', 'ppocr', 'multi_PP-OCRv6_det_small',
                       'PP-OCRv6_det_small.onnx')
    return rec, det


_ocr_engine = None
for attempt in range(1, 4):
    try:
        from cnocr import CnOcr
        # 本地已有模型文件时直接使用，避免联网下载
        rec_fp, det_fp = _local_model_paths()
        kwargs = {}
        if os.path.exists(rec_fp):
            kwargs['rec_model_fp'] = rec_fp
        if os.path.exists(det_fp):
            kwargs['det_model_fp'] = det_fp
        _ocr_engine = CnOcr(**kwargs)
        break
    except ImportError as e:
        error(f"cnocr 初始化失败（缺少依赖或模型加载失败，第 {attempt}/3 次）: {e}")
        error("请尝试安装依赖：pip install onnxruntime")
    except Exception as e:
        error(f"OCR 初始化失败（第 {attempt}/3 次）: {type(e).__name__}: {e}")
    if attempt < 3:
        progress("稍后重试（常见原因是模型下载不完整或网络波动）...")
        time.sleep(3)

if _ocr_engine is None:
    error("OCR 初始化失败，请检查网络后重试；也可运行 python install_models.py 手动安装模型")
    exit(1)

try:
    model_name = getattr(_ocr_engine, 'rec_model_name', 'default')
except Exception:
    model_name = 'default'
ok(f"cnocr 初始化成功 (识别模型: {model_name})")


def _has_cjk(text):
    """判断文本是否包含中文字符"""
    return any('\u4e00' <= ch <= '\u9fff' for ch in text)


def _parse_option_line(line):
    """尝试把一行解析为选项，返回 (字母, 内容)；失败返回 None（支持 A-H，兼容投票题 5 个以上选项）"""
    # 字母 + 分隔符 + 内容：A、xxx / A. xxx / A：xxx / A) xxx
    m = re.match(r'^([A-H])\s*[、.．:：)）]\s*(.+)$', line)
    if m:
        return m.group(1), m.group(2).strip()
    # 字母 + 空格 + 内容：A xxx
    m = re.match(r'^([A-H])\s+(.+)$', line)
    if m and not m.group(2).startswith(('单选', '多选', '判断', '填空')):
        return m.group(1), m.group(2).strip()
    # 字母与内容紧贴：Axxx（以中文开头）
    m = re.match(r'^([A-H])(.+)$', line)
    if m and _has_cjk(m.group(2)):
        return m.group(1), m.group(2).strip()
    return None


def _variant_score(lines):
    """评估一组 OCR 行：选项字母越多越完整，含中文越多越好"""
    letters = sum(1 for l in lines if re.fullmatch(r'[A-H]', l['text']))
    pairs = sum(1 for l in lines if _parse_option_line(l['text']) is not None)
    cjk = sum(1 for l in lines if _has_cjk(l['text']))
    return letters * 100 + pairs * 10 + cjk + len(lines)


def _ocr_once(img):
    """对单张图片执行 OCR，返回按阅读顺序排序的行列表"""
    result = _ocr_engine.ocr(np.array(img))
    lines = []
    for item in (result or []):
        if isinstance(item, dict):
            text = str(item.get('text', '')).strip()
            score = float(item.get('score') or 0)
            pos = item.get('position')
            if pos is None:
                pos = [[0, 0], [0, 0], [0, 0], [0, 0]]
            ys = [p[1] for p in pos]
            xs = [p[0] for p in pos]
            lines.append({
                'text': text,
                'score': score,
                'y': sum(ys) / len(ys),      # 行中心 y
                'x': sum(xs) / len(xs),      # 行中心 x
                'h': max(ys) - min(ys),      # 行高
            })
        elif isinstance(item, (list, tuple)) and len(item) >= 2:
            # 兼容旧版 cnocr 返回格式
            text = str(item[1]).strip() if isinstance(item[1], str) else str(item[1]).strip()
            lines.append({'text': text, 'score': 0.0, 'y': 0.0, 'x': 0.0, 'h': 0.0})
        else:
            lines.append({'text': str(item).strip(), 'score': 0.0, 'y': 0.0, 'x': 0.0, 'h': 0.0})

    if not lines:
        return []

    # 按阅读顺序排序：先按行分组（容差取行高中位数的一半），组内再按 x 从左到右
    heights = [l['h'] for l in lines if l['h'] > 0]
    tol = max(10.0, 0.5 * (sorted(heights)[len(heights) // 2] if heights else 30.0))
    lines.sort(key=lambda d: (round(d['y'] / tol), d['x']))
    return lines


def ocr_image(image_path):
    """OCR 识别截图，返回按阅读顺序排列的文本行列表；多组预处理方案兜底"""
    try:
        img = Image.open(image_path).convert('RGB')
        width, height = img.size

        # 过宽：缩小到 2000 以内；过小：放大 2 倍，提升小字识别率
        if width > 2000:
            ratio = 2000.0 / width
            img = img.resize((2000, int(height * ratio)), Image.LANCZOS)
        elif width < 800 or height < 400:
            img = img.resize((width * 2, height * 2), Image.LANCZOS)

        variants = [('原图', img)]
        variants.append(('增强对比', ImageEnhance.Contrast(img).enhance(1.6)))
        gray = ImageEnhance.Contrast(img.convert('L').convert('RGB')).enhance(2.0)
        variants.append(('灰度增强', gray))

        best_lines, best_score = [], -1
        for name, variant in variants:
            lines = _ocr_once(variant)
            if not lines:
                continue
            score = _variant_score(lines)
            progress(f"{name} 变体: {len(lines)} 行 (得分 {score})")
            if score > best_score:
                best_score, best_lines = score, lines

        if not best_lines:
            return None
        return best_lines

    except Exception as e:
        error(f"OCR 识别失败: {e}")
        return None


# ==================== 文本清理 ====================
NOISE_WORDS = [
    '课程班级', '资源库', 'AI空间', 'AN空间', '窝源府', '山', 'NEW', 'REW',
    '上一题', '提交', '下一题', '返回旧版', '返时旧版', '返回', '展开', 'R7',
    '上一', '下一',
]


def _is_noise_line(line):
    """判断一行是否为页面噪音（顶部栏、按钮、进度等）"""
    if not line:
        return True
    if line in NOISE_WORDS:
        return True
    if re.fullmatch(r'\d+/\d+题?', line):        # 1/2题 之类的进度
        return True
    if re.fullmatch(r'\d{1,2}', line):           # 孤立的短数字（序号残留）
        return True
    if re.fullmatch(r'[一〇O×√✓题上下←→《》〈〉]', line):    # 孤立的单字/符号 UI 残留
        return True
    if re.search(r'截止时间|考核|考试时间', line):  # 页面头部信息
        return True
    if re.match(r'^[<〈【\[]?\s*返回', line):      # 返回按钮
        return True
    return False


def _strip_type_marker(line, question_type):
    """去掉行里的题型标记和分值，如 '2.多选题（2分)' 或 '题型：判断题' -> ''"""
    line = re.sub(r'^题干\s*[：:]\s*', '', line)
    line = re.sub(r'题型\s*[：:]\s*' + question_type, '', line)
    line = re.sub(r'\d*\s*[.、．]?\s*' + question_type, '', line)
    line = re.sub(r'[（(]\s*\d+\s*分\s*[)）]?', '', line)
    return line.strip()


def clean_question(ocr_text):
    """清理 OCR 结果，保留题干与选项，返回 (整理后的文本, 题型)"""
    # 兼容两种输入：字符串，或 ocr_image 返回的行列表
    if isinstance(ocr_text, str):
        lines = [l.strip() for l in ocr_text.split('\n') if l.strip()]
    else:
        lines = [l['text'].strip() for l in ocr_text if l.get('text', '').strip()]

    # 1. 过滤页面噪音
    lines = [l for l in lines if not _is_noise_line(l)]

    # 2. 找题型
    question_type = '单选'
    type_idx = None
    for i, line in enumerate(lines):
        m = re.search(r'(单选题|多选题|判断题|填空题|投票题)', line)
        if m:
            question_type = m.group(1)
            type_idx = i
            break

    def is_standalone_letter(line, lines, i):
        """单独的字母行，且下一行是内容（而不是另一个选项字母）"""
        if not re.fullmatch(r'[A-H]', line):
            return False
        if i + 1 >= len(lines):
            return False
        nxt = lines[i + 1]
        return not re.fullmatch(r'[A-H]', nxt) and not _parse_option_line(nxt)

    # 3. 找第一个选项的位置
    first_opt = None
    for i, line in enumerate(lines):
        if _parse_option_line(line) or is_standalone_letter(line, lines, i):
            first_opt = i
            break

    # 4. 题干：从题型行开始，到第一个选项之前（去掉题型/分值标记）
    stem_lines = []
    start = type_idx if type_idx is not None else 0
    if first_opt is not None:
        slice_lines = lines[start:first_opt]
    else:
        slice_lines = lines[start:]
    for line in slice_lines:
        line = _strip_type_marker(line, question_type)
        if not line:
            continue
        # 判断题中单独成行的“对/错/正确/错误”是选项图标残留，不是题干
        if question_type == '判断题' and line in ('对', '错', '正确', '错误'):
            continue
        stem_lines.append(line)

    # 5. 解析选项（合并被 OCR 拆成两行的“字母 + 内容”）
    options = []  # [(letter, content)]
    if first_opt is not None:
        i = first_opt
        while i < len(lines):
            line = lines[i]
            parsed = _parse_option_line(line)
            if parsed:
                options.append(list(parsed))
                i += 1
                continue
            if re.fullmatch(r'[A-H]', line):
                letter, content = line, ''
                if i + 1 < len(lines) and not re.fullmatch(r'[A-H]', lines[i + 1]) \
                        and not _parse_option_line(lines[i + 1]):
                    content = lines[i + 1]
                    i += 1
                options.append([letter, content])
            i += 1

    # 判断题的“对/错”单独成行时
    if question_type == '判断题' and not options:
        letter_idx = 0
        for line in lines:
            if line in ('对', '错', '正确', '错误'):
                options.append([chr(ord('A') + letter_idx), line])
                letter_idx += 1

    # 6. 组合输出
    result = [f"题型：{question_type}"]
    stem = '\n'.join(stem_lines).strip()
    if stem:
        result.append(f"题干：{stem}")
    if options:
        options.sort(key=lambda o: o[0])
        result.append('选项：')
        for letter, content in options:
            result.append(f"{letter}. {content}" if content else letter)
    else:
        # 实在解析不出选项，把题干之后的原文附上，避免丢信息
        tail = '\n'.join(lines[first_opt:]).strip() if first_opt is not None else ''
        if tail:
            result.append(f"原文：{tail}")

    return '\n'.join(result), question_type


def extract_text(ocr_lines):
    """把 OCR 行列表过滤噪音后拼接成纯文本（用于讨论题等无选项场景）"""
    texts = []
    for l in (ocr_lines or []):
        if isinstance(l, dict):
            t = (l.get('text') or '').strip()
        else:
            t = str(l).strip()
        if t and not _is_noise_line(t):
            texts.append(t)
    return '\n'.join(texts)
