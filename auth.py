# -*- coding: utf-8 -*-
"""本地雨课堂登录、Cookie 保存及课程选择。"""

import json
import os
import re
import tempfile
import time
from urllib.parse import parse_qs, urlencode, urlparse

import requests

from config import COOKIE_PATH, UNIVERSITY_ID
from util import error, info, ok, warn

API_BASE = 'https://changjiang.yuketang.cn'
HOME_URL = f'{API_BASE}/'


def _cookie_map(driver):
    try:
        return {item.get('name'): item.get('value') for item in driver.get_cookies()}
    except Exception:
        return {}


def _university_id(driver):
    query_value = (parse_qs(urlparse(driver.current_url or '').query)
                   .get('university_id') or [None])[0]
    cookies = _cookie_map(driver)
    return str(query_value or cookies.get('university_id') or cookies.get('uv_id') or UNIVERSITY_ID)


def _api_headers(csrf, session, university_id):
    return {
        'User-Agent': ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                       'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36'),
        'Accept': 'application/json, text/plain, */*',
        'Content-Type': 'application/json',
        'Cookie': f'csrftoken={csrf}; sessionid={session}; university_id={university_id}; platform_id=3',
        'x-csrftoken': csrf,
        'X-CSRFToken': csrf,
        'university-id': university_id,
        'platform-id': '3',
        'xtbz': 'ykt',
        'x-client': 'web',
        'Referer': HOME_URL,
    }


def _session_is_valid(driver):
    cookies = _cookie_map(driver)
    csrf, session = cookies.get('csrftoken'), cookies.get('sessionid')
    if not csrf or not session:
        return False
    try:
        response = requests.get(
            f'{API_BASE}/v2/api/web/userinfo',
            headers=_api_headers(csrf, session, _university_id(driver)),
            timeout=15,
        )
        if response.status_code != 200:
            return False
        body = response.text
        return bool(re.search(r'"user_id"\s*:\s*\d+', body))
    except requests.RequestException:
        return False


def _save_auth_cookies(driver):
    """只保存认证所需 Cookie，原子替换文件并避免输出凭证。"""
    cookies = _cookie_map(driver)
    payload = []
    for name in ('csrftoken', 'sessionid'):
        item = next((cookie for cookie in driver.get_cookies()
                     if cookie.get('name') == name), None)
        if not item or not cookies.get(name):
            raise ValueError(f'登录后缺少 {name}')
        entry = {
            'Name': name,
            'Value': cookies[name],
            'Domain': (item.get('domain') or 'changjiang.yuketang.cn').lstrip('.'),
            'Path': item.get('path') or '/',
            'Secure': bool(item.get('secure')),
            'HttpOnly': bool(item.get('httpOnly')),
        }
        expiry = item.get('expiry')
        if expiry:
            entry['Expires'] = time.strftime('%Y-%m-%dT%H:%M:%S', time.localtime(expiry))
        payload.append(entry)

    os.makedirs(os.path.dirname(COOKIE_PATH), exist_ok=True)
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(
                'w', encoding='utf-8', newline='\n',
                dir=os.path.dirname(COOKIE_PATH), delete=False) as temp_file:
            temp_path = temp_file.name
            json.dump(payload, temp_file, ensure_ascii=False, indent=2)
            temp_file.write('\n')
        os.replace(temp_path, COOKIE_PATH)
    finally:
        if temp_path and os.path.exists(temp_path):
            os.unlink(temp_path)


def wait_for_login(driver, timeout_seconds=240):
    """等待用户在本地 Edge 扫码登录；认证通过后保存必要 Cookie。"""
    if _session_is_valid(driver):
        info('已复用本机有效的雨课堂登录状态')
        return True

    info('请在刚打开的 Edge 窗口中扫码登录长江雨课堂。')
    info(f'登录等待时间为 {timeout_seconds // 60} 分钟；Cookie 只保存在本机。')
    deadline = time.monotonic() + timeout_seconds
    next_notice = time.monotonic() + 30
    last_cookie_pair = None
    last_validation = 0.0
    while time.monotonic() < deadline:
        current_cookies = _cookie_map(driver)
        cookie_pair = (current_cookies.get('csrftoken'), current_cookies.get('sessionid'))
        now = time.monotonic()
        should_validate = (all(cookie_pair) and
                           (cookie_pair != last_cookie_pair or now - last_validation >= 15))
        if should_validate and _session_is_valid(driver):
            try:
                _save_auth_cookies(driver)
            except (OSError, ValueError) as exc:
                error(f'保存本地登录状态失败：{exc}')
                return False
            ok('扫码登录成功，已安全保存本机登录状态')
            return True
        if should_validate:
            last_cookie_pair = cookie_pair
            last_validation = now
        if time.monotonic() >= next_notice:
            info('仍在等待登录；完成扫码并确认 Edge 已进入雨课堂页面即可。')
            next_notice = time.monotonic() + 30
        time.sleep(2)
    warn('等待登录超时，请重新运行程序后再扫码。')
    return False


def list_courses(driver):
    """从雨课堂课程列表接口读取用户可访问课程。"""
    cookies = _cookie_map(driver)
    headers = _api_headers(cookies.get('csrftoken'), cookies.get('sessionid'), _university_id(driver))
    try:
        response = requests.get(
            f'{API_BASE}/v2/api/web/courses/list',
            params={'identity': '2'}, headers=headers, timeout=25,
        )
        response.raise_for_status()
        payload = response.json()
        if payload.get('errmsg') != 'Success':
            error(f"读取课程列表失败：{payload.get('errmsg') or payload.get('message') or '接口未确认成功'}")
            return None
        data = payload.get('data') or {}
        items = data.get('list') or data.get('courses') or []
        courses, seen = [], set()
        for item in items:
            course = item.get('course') or item
            classroom_id = item.get('classroom_id') or course.get('classroom_id')
            name = course.get('name') or item.get('name') or f'课程 {classroom_id or "未知"}'
            if classroom_id and str(classroom_id) not in seen:
                seen.add(str(classroom_id))
                courses.append({'classroom_id': str(classroom_id), 'name': str(name)})
        return courses
    except (requests.RequestException, ValueError, TypeError) as exc:
        error(f'读取课程列表失败：{exc}')
        return None


def _course_url(classroom_id, university_id):
    query = urlencode({
        'university_id': university_id,
        'platform_id': '3',
        'classroom_id': classroom_id,
        'content_url': '',
    })
    return f'{API_BASE}/v2/web/studentLog/{classroom_id}?{query}'


def choose_courses(courses, university_id):
    """按编号、名称关键词或课程链接选择一批课程，保持输入顺序。"""
    if not courses:
        return []
    info(f'已找到 {len(courses)} 门课程：')
    for index, course in enumerate(courses, start=1):
        print(f"  {index:>2}. {course['name']}")

    while True:
        choice = input(
            '\n输入课程编号、名称关键词或课程主页链接；多门课程用逗号分隔，输入 q 结束: '
        ).strip()
        if choice.lower() in ('q', 'quit', '退出'):
            return []

        tokens = [token.strip() for token in re.split(r'[,，;；]+', choice) if token.strip()]
        if not tokens:
            warn('请输入至少一个课程编号或名称；输入 q 可结束。')
            continue

        selected_courses = []
        selected_ids = set()
        invalid = False
        for token in tokens:
            match = re.search(r'/studentLog/(\d+)', token)
            if match:
                classroom_id = match.group(1)
                selected = next((course for course in courses
                                 if course['classroom_id'] == classroom_id), None)
            elif token.isdigit() and 1 <= int(token) <= len(courses):
                selected = courses[int(token) - 1]
            else:
                matches = [course for course in courses
                           if token.casefold() in course['name'].casefold()]
                if len(matches) == 1:
                    selected = matches[0]
                elif len(matches) > 1:
                    warn(f'“{token}”匹配到多门课程，请改用课程编号：')
                    for course in matches:
                        index = courses.index(course) + 1
                        print(f"  {index:>2}. {course['name']}")
                    invalid = True
                    continue
                else:
                    selected = None

            if selected is None:
                warn(f'没有匹配到“{token}”，请检查课程编号、名称或链接。')
                invalid = True
                continue
            classroom_id = selected['classroom_id']
            if classroom_id not in selected_ids:
                selected_ids.add(classroom_id)
                selected_courses.append(
                    (selected, _course_url(classroom_id, university_id))
                )

        if not invalid and selected_courses:
            info(f'本批次按顺序选择了 {len(selected_courses)} 门课程。')
            return selected_courses
