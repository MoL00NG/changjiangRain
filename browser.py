# -*- coding: utf-8 -*-
"""浏览器与页面操作：Cookie 加载、驱动创建、截图、翻页、提交、页面状态判断"""

import json
import time
from datetime import datetime

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.edge.options import Options

from config import COOKIE_PATH, SCREENSHOT_PATH
from util import ok, warn, error, progress


# ==================== Cookie 加载 ====================
def load_cookies_from_file(cookie_path=COOKIE_PATH):
    try:
        with open(cookie_path, 'r', encoding='utf-8') as f:
            cookies = json.load(f)

        selenium_cookies = []
        for c in cookies:
            cookie = {
                'name': c.get('Name', ''),
                'value': c.get('Value', ''),
                'domain': c.get('Domain', ''),
                'path': c.get('Path', '/'),
                'secure': c.get('Secure', False),
                'httpOnly': c.get('HttpOnly', False)
            }
            if 'Expires' in c and c['Expires']:
                try:
                    exp_str = c['Expires'].replace('+08:00', '')
                    exp_time = datetime.fromisoformat(exp_str)
                    cookie['expiry'] = int(exp_time.timestamp())
                except Exception:
                    pass
            selenium_cookies.append(cookie)

        ok(f"已读取 {len(selenium_cookies)} 个本机 Cookie 缓存（尚未验证登录是否有效）")
        return selenium_cookies
    except Exception as e:
        error(f"加载 Cookie 失败: {e}")
        return None


# ==================== 浏览器驱动 ====================
def get_driver_with_cookies(url):
    options = Options()
    options.add_argument('--ignore-certificate-errors')
    options.add_argument('--log-level=3')
    options.add_argument('--disable-blink-features=AutomationControlled')
    options.add_experimental_option('excludeSwitches', ['enable-automation'])
    options.add_experimental_option('useAutomationExtension', False)
    options.add_argument('--start-maximized')

    driver = webdriver.Edge(options=options)

    driver.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {
        'source': '''
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            })
        '''
    })

    driver.get(url)
    time.sleep(3)

    cookies = load_cookies_from_file()
    if cookies:
        for cookie in cookies:
            try:
                if not cookie.get('name') or not cookie.get('value'):
                    continue
                if cookie.get('domain', '').startswith('.'):
                    cookie['domain'] = cookie['domain'][1:]
                driver.add_cookie(cookie)
            except Exception as e:
                warn(f"添加 Cookie 失败: {e}")

        driver.refresh()
        time.sleep(3)
        ok("已将本机 Cookie 缓存导入浏览器，正在验证登录状态")

    return driver


# ==================== 题目容器与截图 ====================
def get_question_container(driver):
    selectors = [
        '//div[contains(@class, "container-problem")]',
        '//div[contains(@class, "subject-item")]',
        '//div[contains(@class, "el-scrollbar__view")]',
        '//div[contains(@class, "question") or contains(@class, "problem") or contains(@class, "exercise")]',
        '//body[contains(., "单选题") or contains(., "多选题") or contains(., "判断题")]'
    ]

    for selector in selectors:
        elems = driver.find_elements(By.XPATH, selector)
        for elem in elems:
            if elem.is_displayed():
                return elem
    return None


def screenshot_element(driver, elem, save_path=SCREENSHOT_PATH):
    try:
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", elem)
        time.sleep(0.3)
        elem.screenshot(save_path)
        return save_path
    except Exception as e:
        error(f"截图失败: {e}")
        return None


# ==================== 页面状态判断 ====================
def is_multi_choice(driver):
    """从 HTML 判断是否多选题"""
    try:
        container = driver.find_element(By.XPATH, '//div[contains(@class, "container-problem")]')
        html = container.get_attribute('innerHTML')
        if 'el-checkbox' in html:
            return True
        if 'list-unstyled-checkbox' in html:
            return True
        if '多选' in html:
            return True
        return False
    except Exception:
        return False


def check_if_done(driver):
    """判断作业是否已完成/已提交（最后一题作答后，页面按钮会变为禁用的“已提交”）"""
    try:
        src = driver.page_source
        if '已完成' in src or '全部提交' in src or '已提交' in src:
            return True
    except Exception:
        pass
    return False


def is_list_page(driver):
    """判断当前页面是否为课程学习列表页，兼容新旧版雨课堂。

    新版页面的路径仍是 ``/v2/web/studentLog/<classroom_id>``，但不再
    使用旧版的 ``li.study-unit``。不能只靠旧 DOM 判断，否则主流程会把
    新版课程页误认为未知页，根本不会进入批量扫描。
    """
    try:
        current_url = driver.current_url or ''

        # 已经在作业/答题页里了
        if ('iframe-exercise' in current_url or '/exercise/' in current_url or
                driver.find_elements(By.XPATH, '//div[contains(@class, "container-problem")]')):
            return False

        # 新版课程首页 / 未完成列表页。
        if '/v2/web/studentLog/' in current_url:
            return True

        # 讨论页和视频页不是列表页，即使页面保留了侧边栏。
        if '/forum/' in current_url or '/video/' in current_url:
            return False

        # 旧版页面仍沿用 study-unit。
        items = driver.find_elements(By.XPATH, '//li[contains(@class, "study-unit")]')
        return any(it.is_displayed() for it in items)
    except Exception:
        return False


def click_score_tab(driver):
    """点击“成绩单”页签——作业和讨论列表在该页签下；找不到则忽略"""
    try:
        tabs = driver.find_elements(By.XPATH, '//span[contains(@class, "rain-tabs__nav-item-text")]')
        for tab in tabs:
            if tab.is_displayed() and '成绩单' in (tab.text or ''):
                driver.execute_script("arguments[0].click();", tab)
                time.sleep(2)
                ok("已点击“成绩单”页签")
                return True
    except Exception:
        pass
    return False


def click_unfinished_tab(driver):
    """进入新版课程页的“未完成”页签。

    新版页面会忽略 URL 中的 ``tab=unfinished`` 并回到“学习日志”，因此
    必须通过页面实际的页签切换。找不到时返回 False，让旧版流程继续工作。
    """
    try:
        candidates = driver.find_elements(By.XPATH,
            '//*[contains(normalize-space(.), "未完成") and '
            'not(.//*[contains(normalize-space(.), "未完成")])]')
        visible = []
        for el in candidates:
            if not el.is_displayed():
                continue
            text = (el.text or '').strip()
            if text.startswith('未完成'):
                visible.append(el)
        if not visible:
            return False

        # 最内层文本节点通常不是点击目标，向上寻找尺寸合理的可点击页签。
        target = driver.execute_script("""
            let el = arguments[0];
            for (let p = el; p && p !== document.body; p = p.parentElement) {
                const r = p.getBoundingClientRect();
                const style = getComputedStyle(p);
                if (r.width >= 35 && r.width <= 220 && r.height >= 20 && r.height <= 80 &&
                    (style.cursor === 'pointer' || p.getAttribute('role') === 'tab' ||
                     /tab/i.test(p.className || ''))) {
                    return p;
                }
            }
            return el;
        """, visible[0])
        driver.execute_script("arguments[0].click();", target or visible[0])
        time.sleep(2)
        ok("已切换到新版“未完成”页签")
        return True
    except Exception:
        return False


# ==================== 翻页与提交 ====================
def is_disabled(elem):
    """判断元素是否被禁用（disabled 属性 / class / aria / pointer-events / 父级）"""
    try:
        if elem.get_attribute('disabled') is not None:
            return True
        cls = elem.get_attribute('class') or ''
        if 'disabled' in cls or 'is-disabled' in cls:
            return True
        if (elem.get_attribute('aria-disabled') or '').lower() == 'true':
            return True
        if elem.value_of_css_property('pointer-events') == 'none':
            return True
        parent = elem.find_element(By.XPATH, '..')
        pcls = parent.get_attribute('class') or ''
        if 'disabled' in pcls or 'is-disabled' in pcls or parent.get_attribute('disabled') is not None:
            return True
    except Exception:
        pass
    return False


def go_next(driver):
    """点击“下一题”；按钮不存在或被禁用时返回 False（说明已到最后一题）"""
    try:
        btns = driver.find_elements(By.XPATH,
            '//button[contains(text(), "下一题")] | //span[contains(text(), "下一题")] | //a[contains(text(), "下一题")]')
        if not btns:
            return False
        for btn in btns:
            if is_disabled(btn):
                continue
            driver.execute_script("arguments[0].click();", btn)
            time.sleep(1.5)
            progress("已点击下一题")
            return True
        warn("下一题不可点击，已到最后一题")
        return False
    except Exception:
        return False


def submit_current(driver):
    """点击“提交”按钮提交当前题答案（提交后会自动进入下一题）。

    返回 True=已点击提交 / False=提交按钮不存在或被禁用
    """
    try:
        # 用 contains(., ...) 匹配，兼容 <button><span>提交</span></button> 结构
        btns = driver.find_elements(By.XPATH,
            '//button[contains(., "提交")] | //span[contains(text(), "提交")] | //button[contains(text(), "交卷")]')
        for btn in btns:
            if btn.is_displayed() and not is_disabled(btn):
                driver.execute_script("arguments[0].click();", btn)
                time.sleep(2)
                ok("已提交本题")
                return True
        warn("提交按钮不可用")
        return False
    except Exception:
        return False


def handle_submit_confirm(driver):
    """提交后若有确认弹窗（通常最后一题交卷时出现），点击“确定/确认/继续”；
    点击成功返回 True"""
    try:
        confirms = driver.find_elements(By.XPATH,
            '//button[contains(., "确定") or contains(., "确认") or contains(., "继续")]')
        for c in reversed(confirms):
            if c.is_displayed() and not is_disabled(c):
                driver.execute_script("arguments[0].click();", c)
                time.sleep(2)
                ok("已确认提交")
                return True
    except Exception:
        pass
    return False
