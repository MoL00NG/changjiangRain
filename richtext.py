# -*- coding: utf-8 -*-
"""图文学习单元处理：发现图文节点，检查状态，再按课程接口完成阅读记录。"""

import time

import requests

from config import RICHTEXT_STAY_SECONDS, RICHTEXT_SKIP_DELAY
from util import error, info, ok, progress, warn
from video import (
    API_BASE,
    _extract_session,
    _extract_university_id,
    _headers,
    _pick_classroom,
)


def _iter_nodes(value):
    """递归遍历章节结构中的字典节点。"""
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _iter_nodes(child)
    elif isinstance(value, list):
        for child in value:
            yield from _iter_nodes(child)


def _list_richtexts(headers, classroom_id, university_id):
    """读取当前课程的图文节点（leaf_type == 3），不改变任何学习记录。"""
    try:
        response = requests.get(
            f'{API_BASE}/mooc-api/v1/lms/learn/course/chapter',
            params={
                'cid': classroom_id,
                'term': 'latest',
                'uv_id': university_id,
                'classroom_id': classroom_id,
            },
            headers=headers,
            timeout=30,
        )
        response.raise_for_status()
        payload = response.json()
        if not payload.get('success'):
            warn(f"获取图文章节失败: {payload.get('msg') or payload.get('message') or '未知错误'}")
            return None

        items = []
        seen = set()
        for node in _iter_nodes(payload.get('data', {}).get('course_chapter', [])):
            # 接口在不同课程中可能返回整数或字符串类型。
            if str(node.get('leaf_type')) != '3':
                continue
            leaf_id = node.get('id')
            if not leaf_id or str(leaf_id) in seen:
                continue
            seen.add(str(leaf_id))
            items.append((str(leaf_id), node.get('name') or '未命名图文'))
        return items
    except Exception as exc:
        error(f"获取图文列表失败: {exc}")
        return None


def _is_finished(headers, leaf_id):
    """返回 True / False；请求失败时返回 None，避免误判后重复完成。"""
    try:
        response = requests.get(
            f'{API_BASE}/mooc-api/v1/lms/learn/user_article_finish_status/{leaf_id}/',
            headers=headers,
            timeout=20,
        )
        response.raise_for_status()
        payload = response.json()
        if not payload.get('success'):
            return None
        return bool(payload.get('data', {}).get('finish'))
    except Exception as exc:
        warn(f"图文 {leaf_id}: 无法读取完成状态 ({exc})")
        return None


def _complete_one(headers, leaf_id, title):
    """完成一个已确认未完成的图文单元，并按接口响应验证结果。"""
    finished = _is_finished(headers, leaf_id)
    if finished is True:
        info(f"{title}: 已完成，跳过")
        return True
    if finished is None:
        warn(f"{title}: 状态不明确，为避免误操作已跳过")
        return False

    if RICHTEXT_STAY_SECONDS > 0:
        progress(f"{title}: 阅读停留 {RICHTEXT_STAY_SECONDS} 秒")
        time.sleep(RICHTEXT_STAY_SECONDS)

    try:
        response = requests.get(
            f'{API_BASE}/mooc-api/v1/lms/learn/user_article_finish/{leaf_id}/',
            headers=headers,
            timeout=20,
        )
        response.raise_for_status()
        payload = response.json()
        if payload.get('success'):
            ok(f"{title}: 图文已完成")
            return True
        warn(f"{title}: 完成接口未确认成功")
        return False
    except Exception as exc:
        warn(f"{title}: 图文完成失败 ({exc})")
        return False


def complete_all_richtexts(driver):
    """处理当前课程所有图文单元；仅在列表检测到“图文”时由调度器调用。"""
    info("开始处理图文学习单元...")
    csrf, session = _extract_session(driver)
    if not csrf or not session:
        return False

    university_id = _extract_university_id(driver)
    headers = _headers(csrf, session, university_id, xtbz='ykt')
    classroom_id = _pick_classroom(headers, driver)
    if not classroom_id:
        return False
    headers = _headers(csrf, session, university_id, cid=classroom_id, xtbz='ykt')

    items = _list_richtexts(headers, classroom_id, university_id)
    if items is None:
        return False
    if not items:
        info("该课程没有图文学习单元")
        return True

    info(f"共找到 {len(items)} 个图文学习单元")
    succeeded = 0
    for index, (leaf_id, title) in enumerate(items, start=1):
        progress(f"图文 {index}/{len(items)}: {title}")
        if _complete_one(headers, leaf_id, title):
            succeeded += 1
        if index < len(items) and RICHTEXT_SKIP_DELAY > 0:
            time.sleep(RICHTEXT_SKIP_DELAY)

    ok(f"图文处理完成：{succeeded}/{len(items)}")
    return succeeded == len(items)
