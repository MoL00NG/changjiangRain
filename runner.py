# -*- coding: utf-8 -*-
"""列表批量调度：扫描学习单元列表，处理讨论、视频和图文；作业由用户手动完成。"""

import time

from selenium.webdriver.common.by import By

from browser import is_list_page, click_score_tab, click_unfinished_tab
from util import section, info, ok, warn, error
import discussion
import richtext
import video
from config import DEEPSEEK_API_KEY


def _parse_list_item(li):
    """解析列表项，返回 (类型, 名称, 状态)；解析失败返回 ('', '', '')"""
    try:
        tag = li.find_element(By.XPATH, './/span[contains(@class, "type-tag")]').text.strip()
    except Exception:
        tag = ''
    try:
        name = li.find_element(By.XPATH, './/span[contains(@class, "name-text")]').text.strip()
    except Exception:
        name = ''
    status = '未知'
    for s in ('未开始', '未发言', '未学习', '未完成', '学习中', '进行中',
              '已完成', '已学习', '已发言', '待批改'):
        if s in li.text:
            status = s
            break
    return tag, name, status


def _item_key(li, tag, name):
    """生成列表项的稳定标识；同名讨论不能只按名称去重。"""
    try:
        for attr in ('data-id', 'data-node-id', 'data-leaf-id', 'data-leaf_id', 'id'):
            value = li.get_attribute(attr)
            if value:
                return (tag, attr, value)
        # 新版列表的同名项通常仍带有不同的内部节点属性。
        return (tag, li.get_attribute('outerHTML'))
    except Exception:
        return (tag, name)


def _find_new_list_items(driver):
    """识别新版“未完成”页面的行容器。

    新版页面不再使用 li.study-unit，而是在每一行中显示“未发言/未学习/未开始”。
    """
    found = []
    seen = set()
    # 用 JS 的 innerText 而非 XPath text()：新版组件会在标签内嵌套图标，
    # XPath 的直接文本匹配经常漏掉状态节点。
    #
    # 新版计分视频有时不显示“未学习”，而只显示如“80%”的完成度；
    # 因此同时收集未完成百分比标签，避免把这类视频误判为没有任务。
    candidate_nodes = driver.execute_script("""
        const statuses = new Set(['未发言', '未学习', '未开始', '未完成']);
        return Array.from(document.querySelectorAll('*')).filter((el) => {
            const own = (el.innerText || '').trim();
            const isStatus = statuses.has(own) && !Array.from(el.children).some((child) =>
                statuses.has((child.innerText || '').trim()));
            const percent = own.match(/^(\\d{1,3})%$/);
            const isIncompleteVideoPercent = percent && Number(percent[1]) < 100 &&
                !Array.from(el.children).some((child) => /^(\\d{1,3})%$/.test(
                    (child.innerText || '').trim()));
            return isStatus || isIncompleteVideoPercent;
        });
    """)
    for node in candidate_nodes:
        try:
            row = driver.execute_script("""
                let el = arguments[0];
                for (let p = el; p && p !== document.body; p = p.parentElement) {
                    const text = (p.innerText || '').trim();
                    const rect = p.getBoundingClientRect();
                    const hasStatus = text.includes('未发言') || text.includes('未学习') ||
                        text.includes('未开始') || text.includes('未完成');
                    const hasIncompleteVideoProgress = text.includes('视频') &&
                        /(?:^|\\s)(?:[0-9]{1,2}|100)%/.test(text) && !/100%/.test(text);
                    if (rect.height >= 45 && rect.height <= 180 &&
                        (text.includes('讨论') || text.includes('视频') || text.includes('图文')) &&
                        (hasStatus || hasIncompleteVideoProgress)) {
                        return p;
                    }
                }
                return null;
            """, node)
            if not row:
                continue
            text = (row.text or '').strip()
            tag = ('讨论' if '讨论' in text else
                   ('视频' if '视频' in text else ('图文' if '图文' in text else '')))
            if not tag:
                continue
            key = _item_key(row, tag, text)
            if key in seen:
                continue
            seen.add(key)
            found.append((row, tag, text, key))
        except Exception:
            continue
    return found


def _find_next_item(driver, processed):
    """找下一个未完成的讨论/视频/图文项；作业不参与自动处理。"""
    # 新版未完成页优先；没有识别到时再兼容旧版列表。
    new_items = _find_new_list_items(driver)
    if new_items:
        candidates = [item for item in new_items if item[3] not in processed]
        for li, tag, name, key in candidates:
            if tag == '讨论':
                return li, tag, name, key
        if candidates:
            return candidates[0]
        return None, None, None, None

    items = driver.find_elements(By.XPATH, '//li[contains(@class, "study-unit")]')
    # 讨论优先：避免视频批处理后的刷新或会话状态变化使讨论被跳过。
    candidates = []
    for li in items:
        try:
            tag, name, status = _parse_list_item(li)
        except Exception:
            continue
        if tag not in ('讨论', '视频', '图文'):
            continue
        if tag == '讨论' and status != '未发言':
            continue
        if tag in ('视频', '图文') and status in ('已完成', '已学习'):
            continue
        key = _item_key(li, tag, name)
        if not name or key in processed:
            continue
        candidates.append((li, tag, name, key))
    for li, tag, name, key in candidates:
        if tag == '讨论':
            return li, tag, name, key
    if candidates:
        return candidates[0]
    return None, None, None, None


def auto_answer_list(driver, list_url):
    """列表模式：逐个处理未完成的讨论、视频和图文，跳过作业。"""
    info("检测到学习单元列表，开始处理未完成的讨论、视频和图文；作业请手动完成...")
    scan_url = list_url
    if 'tab=unfinished' not in scan_url:
        scan_url += ('&' if '?' in scan_url else '?') + 'tab=unfinished'
    processed = set()  # 已进入过的 (类型, 名称)，防止重复处理
    score_tab_clicked = False  # “成绩单”页签只在首次进入时点击

    while True:
        # 回到列表页，刷新状态
        try:
            driver.switch_to.default_content()
            driver.get(scan_url)
            time.sleep(3)
            # 新版忽略 tab=unfinished 查询参数，需要显式点击“未完成”。
            if click_unfinished_tab(driver):
                score_tab_clicked = True
            elif not score_tab_clicked:
                click_score_tab(driver)
                score_tab_clicked = True
        except Exception as e:
            error(f"刷新列表失败: {e}")
            break

        li, tag, name, item_key = _find_next_item(driver, processed)
        if li is None:
            ok("没有更多未完成（未开始/未发言/未学习/未完成）的讨论、视频或图文单元了")
            break

        section(f"处理{tag}: {name}")
        processed.add(item_key)

        # 视频：不进入页面，直接用 API 心跳一键刷课
        if tag == '视频':
            video.brush_all_videos(driver, list_url)
            # 新版列表通常有多个视频进度行；一次视频流程覆盖整门课程，
            # 因此将所有新版视频行标记为已处理，避免重复启动整门课程流程。
            try:
                for _, new_tag, _, new_key in _find_new_list_items(driver):
                    if new_tag == '视频':
                        processed.add(new_key)
            except Exception:
                pass
            # 同时兼容旧版 study-unit 列表。
            try:
                for li in driver.find_elements(By.XPATH, '//li[contains(@class, "study-unit")]'):
                    t, n, s = _parse_list_item(li)
                    if t == '视频' and n:
                        processed.add((t, n))
            except Exception:
                pass
            # 心跳接口不会跳转页面；显式回到顶层上下文，下一轮从列表重新扫描讨论。
            try:
                driver.switch_to.default_content()
                driver.get(scan_url)
                time.sleep(3)
                click_score_tab(driver)
            except Exception as e:
                warn(f"返回列表失败: {e}")
            continue

        # 图文：通过课程接口处理全部图文节点，不进入页面，不影响视频逻辑。
        if tag == '图文':
            richtext.complete_all_richtexts(driver)
            try:
                for new_li, new_tag, new_name, new_key in _find_new_list_items(driver):
                    if new_tag == '图文':
                        processed.add(new_key)
            except Exception:
                pass
            continue

        # 点击进入（优先点名称列 unit-name-td，否则点整个 li）
        try:
            try:
                click_target = li.find_element(By.XPATH, './/div[contains(@class, "unit-name-td")]')
            except Exception:
                click_target = li
            driver.execute_script("arguments[0].click();", click_target)
            time.sleep(3)
        except Exception as e:
            error(f"点击{tag}失败: {e}")
            continue

        # 如果在新标签页打开，切换过去
        try:
            if len(driver.window_handles) > 1:
                driver.switch_to.window(driver.window_handles[-1])
                time.sleep(2)
                info("已切换到新标签页")
        except Exception:
            pass

        if is_list_page(driver):
            warn("点击后仍在列表页（可能需手动进入），跳过该项")
            continue

        # 按类型分发处理
        if tag == '讨论':
            if DEEPSEEK_API_KEY:
                discussion.auto_answer_discussion(driver)
            else:
                warn('未配置 DeepSeek API Key，跳过讨论项；视频和图文仍可继续处理。')

        # 关闭讨论标签页，回到列表标签页
        try:
            while len(driver.window_handles) > 1:
                driver.switch_to.window(driver.window_handles[-1])
                driver.close()
                time.sleep(0.5)
            driver.switch_to.window(driver.window_handles[0])
        except Exception:
            pass

        # 关闭当前界面，回到列表继续下一个
        info("返回列表，继续检索下一个...")
        time.sleep(1)
