# -*- coding: utf-8 -*-
"""AI 求解：选择题共识作答、讨论发言生成"""

import re
import time
from collections import Counter

import requests

from config import (
    DEEPSEEK_API_KEY, DEEPSEEK_MODEL, DEEPSEEK_BASE_URL,
    MAX_RETRIES, MIN_CONSENSUS, DISCUSSION_MIN_LEN, DISCUSSION_MAX_LEN,
)
from util import ok, warn, error, progress

_HEADERS = {
    'Content-Type': 'application/json',
    'Authorization': f'Bearer {DEEPSEEK_API_KEY}'
}


def _chat(prompt, temperature=0.3, max_tokens=8192, use_reasoning_fallback=True):
    """调用 DeepSeek API，返回消息文本（兼容 content / reasoning_content）。

    使用接口默认的基础深度思考；推理会占用 max_tokens，必须给足，
    否则 finish_reason=length 且 content 为空。
    use_reasoning_fallback=False 时 content 为空直接返回 None，
    避免把英文推理过程（reasoning_content）误当回答（如讨论发言）。
    """
    data = {
        'model': DEEPSEEK_MODEL,
        'messages': [{'role': 'user', 'content': prompt}],
        'temperature': temperature,
        'max_tokens': max_tokens,
    }
    try:
        response = requests.post(
            f'{DEEPSEEK_BASE_URL}/chat/completions',
            headers=_HEADERS,
            json=data,
            timeout=300
        )
        if response.status_code != 200:
            error(f'API 错误 {response.status_code}: {response.text[:200]}')
            return None
        result = response.json()
        try:
            msg = result['choices'][0]['message']
        except (KeyError, IndexError):
            error(f'API 返回异常: {str(result)[:200]}')
            return None
        content = (msg.get('content') or '').strip()
        reasoning = (msg.get('reasoning_content') or '').strip()
        if content:
            text = content
        elif use_reasoning_fallback:
            text = reasoning
        else:
            return None  # 不把英文推理过程当回答
        # 去掉 markdown 代码块围栏，如 ```A,C```
        return re.sub(r'^```[a-zA-Z]*|```$', '', text).strip()
    except Exception as e:
        error(f'API 错误: {e}')
        return None


def _is_mostly_chinese(text):
    """判断文本是否以中文为主（防止英文推理/英文回答被当作发言）"""
    if not text:
        return False
    total = max(len(text), 1)
    ascii_letters = sum(1 for ch in text if 'a' <= ch <= 'z' or 'A' <= ch <= 'Z')
    cjk = sum(1 for ch in text if '\u4e00' <= ch <= '\u9fff')
    return cjk >= total * 0.3 and ascii_letters <= total * 0.25


def solve_once(question_text, is_multi=False):
    """单次调用 AI 求选择题答案"""
    if is_multi:
        prompt = f"""这是一道**多选题**，可能有多个正确答案。

题目内容：
{question_text}

重要：这是多选题，必须输出所有正确选项的字母，用逗号分隔！
例如：A,C 或 A,B,D

只输出答案："""
    else:
        prompt = f"""请仔细阅读以下题目，只输出答案，不要输出任何解释。

题目内容：
{question_text}

输出规则：
- 单选题：输出单个字母，如 A
- 多选题：输出多个字母用逗号分隔，如 A,C
- 判断题：输出 对 或 错

只输出答案："""

    answer = _chat(prompt)
    if answer is None:
        return None

    # 提取答案
    if is_multi:
        # 多选/投票题：匹配 A,C 或 A,B,C 格式（兼容逗号/顿号/空格/“和”分隔）
        match = re.search(r'[A-H](?:[,\s，、和]*[A-H])*', answer)
        if match:
            # 清理格式，去掉空格，统一用逗号
            raw = match.group(0)
            parts = re.findall(r'[A-H]', raw)
            if parts:
                return ','.join(sorted(set(parts)))
        warn(f'未解析出多选答案: {answer[:100]!r}')
        return None
    else:
        # 单选或判断
        match = re.search(r'^[A-H]$|^[对错]$', answer)
        if match:
            return match.group(0)
        match2 = re.search(r'[A-H]|[对错]', answer)
        if match2:
            return match2.group(0)
        warn(f'未解析出单选/判断答案: {answer[:100]!r}')
        return None


def solve_with_consensus(question_text, is_multi=False, max_retries=MAX_RETRIES, min_consensus=MIN_CONSENSUS):
    """多次调用 AI，取共识"""
    answers = []

    for i in range(max_retries):
        progress(f'第 {i+1}/{max_retries} 次思考...')
        answer = solve_once(question_text, is_multi)

        if answer:
            answers.append(answer)
            ok(f'本次结果: {answer}')
        else:
            warn('无效，重试')

        if len(answers) >= min_consensus:
            counter = Counter(answers)
            for ans, count in counter.items():
                if count >= min_consensus:
                    ok(f'达成共识: {ans} ({count} 次)')
                    return ans

        time.sleep(0.3)

    if answers:
        counter = Counter(answers)
        most_common = counter.most_common(1)[0]
        warn(f'采用出现最多的: {most_common[0]}')
        return most_common[0]

    return None


def generate_discussion_answer(question, min_len=DISCUSSION_MIN_LEN, max_len=DISCUSSION_MAX_LEN):
    """让 AI 针对讨论主题生成一段 min_len~max_len 字的客观中文发言。

    不把英文推理过程当回答；非中文/超字数自动重写，最多 3 次。
    """
    note = ''
    for _ in range(3):
        prompt = f"""请针对下面的讨论主题，写一段讨论发言，字数控制在 {min_len}~{max_len} 字（含标点）之间，根据主题需要自行选择合适篇幅。
{note}
要求：
- 必须使用中文回答，不得出现英文内容
- 以客观、理性的口吻作答，陈述事实与观点，不带个人主观情感和感受
- 不要出现“我觉得”“我认为”“我学会了”“让我”等第一人称主观表述
- 只输出发言内容本身，不要任何前缀、引号或解释

讨论主题：
{question}"""
        text = _chat(prompt, temperature=0.7, max_tokens=8192, use_reasoning_fallback=False)
        if text:
            text = text.strip(' "\'“”‘’')
        if not text or len(text) < 10:
            note = '注意：上一版生成失败或为空，请重新写一版中文发言。'
            continue
        if not _is_mostly_chinese(text):
            note = '注意：上一版发言混入了大量英文，请只用中文重新写一版。'
            continue
        # 少量容差：模型数字数时通常不含标点/引号
        if min_len - 10 <= len(text) <= max_len + 15:
            return text
        note = f'注意：上一版发言共 {len(text)} 字，不符合 {min_len}~{max_len} 字要求，请重新写一版，严格控制字数。'
    return None
