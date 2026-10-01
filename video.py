# -*- coding: utf-8 -*-
"""视频一键刷课：通过心跳接口模拟观看进度（参考 viedookok.py 的 API 方案）。

无需进入视频页面，直接从浏览器会话取 Cookie 调接口，几分钟刷完全部未看视频。
"""

import json
import re
import time
from urllib.parse import parse_qs, urlparse

import requests

from config import UNIVERSITY_ID, VIDEO_LEARNING_RATE, VIDEO_HEARTBEAT_BATCH
from util import info, ok, warn, error, progress

API_BASE = "https://changjiang.yuketang.cn"
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36 Edg/119.0.0.0')


def _extract_session(driver):
    """从浏览器会话中提取 csrftoken 与 sessionid"""
    csrf = session = None
    for c in driver.get_cookies():
        if c['name'] == 'csrftoken':
            csrf = c['value']
        elif c['name'] == 'sessionid':
            session = c['value']
    if not csrf or not session:
        warn("浏览器会话中未找到 csrftoken/sessionid（请确认 Cookie 已加载）")
    return csrf, session


def _extract_university_id(driver):
    """优先使用当前课程 URL 的学校编号，旧常量仅作兜底。

    不同学校部署的长江雨课堂编号不同；把它固定为 3714 会让其他学校的
    视频接口带错请求头。当前页面 URL 是最可靠且无需额外请求的来源。
    """
    try:
        params = parse_qs(urlparse(driver.current_url or '').query)
        value = (params.get('university_id') or [''])[0]
        if value:
            return str(value)
    except Exception:
        pass
    try:
        for cookie in driver.get_cookies():
            if cookie.get('name') in ('university_id', 'uv_id') and cookie.get('value'):
                return str(cookie['value'])
    except Exception:
        pass
    return str(UNIVERSITY_ID)


def _headers(csrf, session, university_id, cid=None, xtbz='cloud'):
    headers = {
        'User-Agent': UA,
        'Content-Type': 'application/json',
        'Cookie': f'csrftoken={csrf}; sessionid={session}; '
                  f'university_id={university_id}; platform_id=3',
        'x-csrftoken': csrf,
        'sec-fetch-dest': 'empty',
        'sec-fetch-mode': 'cors',
        'sec-fetch-site': 'same-origin',
        'university-id': university_id,
        'xtbz': xtbz,
    }
    if cid:
        headers['classroom-id'] = str(cid)
        headers['Referer'] = f'{API_BASE}/v2/web/studentLog/{cid}'
    return headers


def _get_user_id(headers):
    try:
        r = requests.get(f'{API_BASE}/v2/api/web/userinfo', headers=headers, timeout=30)
        m = re.search(r'"user_id":(\d+)', r.text)
        return m.group(1) if m else None
    except Exception as e:
        error(f"获取用户信息失败: {e}")
        return None


def _extract_classroom_id(url):
    """从页面 URL 提取 classroom_id（形如 .../studentLog/12345）"""
    m = re.search(r'studentLog/(\d+)', url or '')
    if m:
        return m.group(1)
    m = re.search(r'classroom[^/\d]*[/=](\d+)', url or '')
    return m.group(1) if m else None


def _pick_classroom(headers, driver):
    """优先从当前 URL 提取教室 id；失败则列出课程让用户选择"""
    cid = _extract_classroom_id(driver.current_url)
    if cid:
        info(f"教室 id: {cid}")
        return cid
    try:
        r = requests.get(f'{API_BASE}/v2/api/web/courses/list',
                         params={'identity': '2'}, headers=headers, timeout=30).json()
        if r.get('errmsg') != 'Success':
            error("课程列表获取失败（Cookie 可能已失效）")
            return None
        items = r['data']['list']
        for i, item in enumerate(items):
            info(f"[{i + 1}] {item['course']['name']}")
        n = input('请输入课程编号: ').strip()
        return str(items[int(n) - 1]['classroom_id'])
    except Exception as e:
        error(f"获取课程列表失败: {e}")
        return None


def _list_videos(headers, cid):
    """获取课程下所有视频叶子节点，返回 [(leaf_id, 标题)]"""
    try:
        r = requests.get(f'{API_BASE}/v2/api/web/classrooms/{cid}?role=5',
                         headers=headers, timeout=30).json()
        skuid = r['data']['free_sku_id']
        url = f'{API_BASE}/c27/online_courseware/schedule/score_detail/single/{skuid}/0/'
        ret = requests.get(url, headers=headers, timeout=30).json()
        videos = []
        for leaf in ret['data']['leaf_level_infos']:
            if leaf.get('leaf_type') == 0:  # 0 = 视频
                videos.append((str(leaf['id']), leaf.get('leaf_level_title') or '未命名视频'))
        return videos
    except Exception as e:
        error(f"获取视频列表失败: {e}")
        return None


def _brush_one(headers, cid, leaf_id, title, university_id):
    """刷单个视频直到进度 100%，返回是否成功"""
    try:
        leaf = requests.get(f'{API_BASE}/mooc-api/v1/lms/learn/leaf_info/{cid}/{leaf_id}/',
                            headers=headers, timeout=30).json()['data']
        skuid = leaf['sku_id']
        user_id = leaf['user_id']
        course_id = leaf['course_id']
    except Exception as e:
        warn(f"{title}: 获取视频信息失败 ({e})")
        return False

    # 新版 leaf_info 有时将节点 id 与实际视频 id 分开，优先使用后者。
    video_id = str(leaf.get('video_id') or leaf.get('content_id') or leaf_id)
    progress_url = (f'{API_BASE}/video-log/get_video_watch_progress/'
                    f'?cid={course_id}&user_id={user_id}&classroom_id={cid}'
                    f'&video_type=video&vtype=rate&video_id={video_id}'
                    f'&snapshot=1&term=latest&uv_id={university_id}')

    # 已完成则跳过
    try:
        m = re.search(r'"completed":(\d)', requests.get(progress_url, headers=headers, timeout=30).text)
        if m and m.group(1) == '1':
            info(f"{title}: 已完成，跳过")
            return True
    except Exception:
        pass

    info(f"{title}: 开始刷课...")
    video_frame = 0
    val = 0
    timestap = int(round(time.time() * 1000))
    while str(val) not in ('1.0', '1'):
        heart_data = []
        for _ in range(VIDEO_HEARTBEAT_BATCH):
            heart_data.append({
                'i': 5, 'et': 'loadeddata', 'p': 'web',
                'n': 'ali-cdn.xuetangx.com', 'lob': 'ykt',
                'cp': video_frame, 'fp': 0, 'tp': 0, 'sp': 1,
                'ts': str(timestap), 'u': int(user_id), 'uip': '',
                'c': course_id, 'v': int(video_id), 'skuid': skuid,
                'classroomid': cid, 'cc': video_id, 'd': 4981.0,
                'pg': '4512543_skdv', 'sq': 2, 't': 'video',
                'cards_id': 0, 'slide': 0, 'v_url': '',
            })
            video_frame += VIDEO_LEARNING_RATE
            max_time = int((time.time() + 3600) * 1000)
            timestap = min(max_time, timestap + 1000 * 15)
        try:
            r = requests.post(f'{API_BASE}/video-log/heartbeat/',
                              headers=headers, json={'heart_data': heart_data}, timeout=30)
            try:
                err = json.loads(r.text)['message']
                if 'anomaly' in err:
                    video_frame = 0  # 检测到异常，重置进度重新刷
            except Exception:
                pass
        except Exception as e:
            warn(f"{title}: 心跳发送失败 ({e})")
            return False
        try:
            m = re.search(r'"rate":([\d.]+)',
                          requests.get(progress_url, headers=headers, timeout=30).text)
            if not m:
                return False
            val = m.group(1)
            progress(f"{title}: 进度 {float(val) * 100:.1f}%")
        except Exception:
            pass
        time.sleep(0.7)
    ok(f"{title}: 学习完成")
    return True


def brush_all_videos(driver, list_url=None):
    """一键刷完当前课程所有未完成的视频；返回是否成功"""
    info("视频一键刷课（API 心跳方案）...")
    csrf, session = _extract_session(driver)
    if not csrf or not session:
        return False
    university_id = _extract_university_id(driver)
    info(f"学校 id: {university_id}")
    headers = _headers(csrf, session, university_id, xtbz='ykt')

    user_id = _get_user_id(headers)
    if not user_id:
        return False
    info(f"用户 id: {user_id}")

    cid = _pick_classroom(headers, driver)
    if not cid:
        return False
    headers = _headers(csrf, session, university_id, cid=cid, xtbz='ykt')

    videos = _list_videos(headers, cid)
    if videos is None:
        return False
    if not videos:
        info("该课程没有视频章节")
        return True

    info(f"共找到 {len(videos)} 个视频")
    done = 0
    for leaf_id, title in videos:
        if _brush_one(headers, cid, leaf_id, title, university_id):
            done += 1
    ok(f"视频处理完成：{done}/{len(videos)}")
    return True
