# -*- coding: utf-8 -*-
"""讨论作答：获取讨论主题 -> AI 生成发言 -> 填入文本框并发送"""

import re
import time

from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys

from config import SCREENSHOT_PATH
from ai import generate_discussion_answer
from ocr import ocr_image, extract_text, _is_noise_line, _has_cjk
from browser import is_disabled
from util import info, ok, warn, error, progress


def is_discussion_page(driver):
    """判断当前页面是否为讨论页（兼容旧 textarea 与新版 contenteditable）。"""
    try:
        if '/forum/' in (driver.current_url or ''):
            return True
        for ta in driver.find_elements(
                By.XPATH, '//textarea[contains(@class, "el-textarea__inner")] | //*[@contenteditable="true"]'):
            ph = ' '.join(filter(None, (
                ta.get_attribute('placeholder'), ta.get_attribute('aria-label'), ta.get_attribute('title'))))
            if any(k in ph for k in ('发表', '观点', '讨论', '回复')):
                return True
    except Exception:
        pass
    return False


def _looks_like_topic(text):
    """排除新版论坛的导航、课程名和状态文字，保留真正的讨论题目。"""
    text = ' '.join((text or '').split())
    if not (5 <= len(text) <= 500) or not _has_cjk(text):
        return False
    if any(token in text for token in (
            '讨论区', '讨论单元', '考核截止', '未发言', '已发言', 'Enter发送',
            'Shift+Enter', '学习内容', '课程班级', '返回旧版')):
        return False
    # “2026秋-……1班”等是课程/班级名，不是题目。
    if re.search(r'20\d{2}.*(?:春|夏|秋|冬).*(?:班|课程)$', text):
        return False
    return True


def _topic_near_forum_heading(driver):
    """新版论坛把题目放在“讨论区（n）”标题之前，按这个相邻关系提取。"""
    try:
        raw = driver.execute_script('return document.body.innerText;') or ''
        lines = [' '.join(line.split()) for line in raw.split('\n') if line.strip()]
        for index, line in enumerate(lines):
            if re.match(r'^讨论区(?:\s*[（(]\s*\d+\s*[)）])?$', line):
                # 标题前四行中，离标题最近的有效文本就是题目。
                for candidate in reversed(lines[max(0, index - 4):index]):
                    if _looks_like_topic(candidate):
                        return candidate
    except Exception:
        pass
    return None


def get_discussion_question(driver):
    """获取讨论主题：
    1) 优先从题目区域提取（custom_ueditor_cn_body 等容器）
    2) 其次整页 DOM 文本取最长行
    3) 最后截图 OCR 兜底
    """
    # 1) 新版论坛的题目与“讨论区（人数）”标题相邻。这一步必须先做，
    # 否则整页选择器会误取课程名或其他同学的长篇发言。
    question = _topic_near_forum_heading(driver)
    if question:
        return question

    # 2) 从题目区域精确提取
    try:
        for selector in (
            '//div[contains(@class, "custom_ueditor_cn_body")]',
            '//div[contains(@class, "custom-ueditor")]',
            '//section[contains(@class, "content")]',
        ):
            for el in driver.find_elements(By.XPATH, selector):
                if el.is_displayed():
                    t = (el.text or '').strip()
                    if _looks_like_topic(t):
                        return t
    except Exception:
        pass

    # 3) 从 DOM 文本中优先取带提问语气的短行，避免误用帖子正文。
    try:
        text = driver.execute_script('return document.body.innerText;') or ''
        lines = [l.strip() for l in text.split('\n') if l.strip()]
        lines = [l for l in lines if not _is_noise_line(l) and _looks_like_topic(l)]
        prompt_lines = [l for l in lines if any(k in l for k in ('谈一谈', '讨论', '请', '如何', '为什么', '关系'))]
        if prompt_lines:
            return min(prompt_lines, key=len)
        if lines:
            return min(lines, key=len)
    except Exception:
        pass

    # 4) OCR 兜底：整页截图识别
    try:
        body = driver.find_element(By.TAG_NAME, 'body')
        driver.execute_script("arguments[0].scrollIntoView({block: 'start'});", body)
        time.sleep(0.3)
        body.screenshot(SCREENSHOT_PATH)
        lines = ocr_image(SCREENSHOT_PATH)
        if lines:
            return extract_text(lines)
    except Exception as e:
        error(f"讨论主题提取失败: {e}")
    return None


def post_discussion(driver, text):
    """把发言填入文本框并点击发送按钮"""
    try:
        ta = None
        for el in driver.find_elements(By.XPATH, '//textarea[contains(@class, "el-textarea__inner")] | //*[@contenteditable="true"]'):
            if el.is_displayed():
                ta = el
                break
        if ta is None:
            warn("找不到发言输入框")
            return False

        # 用原生 setter 赋值并触发输入事件，确保 Vue/React 能感知输入。
        driver.execute_script("""
            var el = arguments[0];
            if (el.isContentEditable) {
                el.textContent = arguments[1];
            } else {
                var setter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value').set;
                setter.call(el, arguments[1]);
            }
            el.dispatchEvent(new InputEvent('input', {
                bubbles: true, inputType: 'insertText', data: arguments[1]
            }));
            el.dispatchEvent(new Event('change', {bubbles: true}));
        """, ta, text)

        def editor_value():
            try:
                if ta.get_attribute('contenteditable') == 'true':
                    return (ta.get_attribute('textContent') or '').strip()
                return (ta.get_attribute('value') or '').strip()
            except Exception:
                return ''

        if not editor_value():
            warn("发言内容未能写入输入框")
            return False

        # 新版论坛明确提示“Enter发送 / Shift+Enter换行”，回车是其官方发送方式。
        # 旧版文本框不能盲目回车，否则只会插入换行。
        try:
            body_text = driver.execute_script('return document.body.innerText;') or ''
            if '/forum/' in (driver.current_url or '') or 'Enter发送' in body_text:
                ta.click()
                ta.send_keys(Keys.ENTER)
                time.sleep(2)
                if not editor_value():
                    return True
        except Exception:
            pass

        # 等待“发送”按钮解除禁用（输入后 Vue 会移除 disabled），最多等 3 秒
        btn = None
        for _ in range(6):
            for el in driver.find_elements(By.XPATH,
                    '//button[contains(@class, "submitComment") or contains(text(), "发送")]'):
                if el.is_displayed() and not is_disabled(el):
                    btn = el
                    break
            if btn:
                break
            time.sleep(0.5)
        if btn:
            driver.execute_script("arguments[0].click();", btn)
            time.sleep(2)
            if not editor_value():
                return True

        # 新版页面可能使用 role=button 或将文字嵌套在 span 中
        for el in driver.find_elements(By.XPATH,
                '//*[@role="button" and (contains(., "发送") or contains(., "发表") or contains(., "发布") or contains(., "提交"))]'):
            if el.is_displayed() and not is_disabled(el):
                driver.execute_script("arguments[0].click();", el)
                time.sleep(2)
                if not editor_value():
                    return True

        # 新版雨课堂发送按钮是输入框右下角的纸飞机图标，没有文字。
        # 在输入框所在容器内取最后一个可见且未禁用的 button，避开前面的附件按钮。
        try:
            container = ta.find_element(
                By.XPATH, './ancestor::div[.//textarea or .//*[@contenteditable="true"]][1]')
            icon_buttons = [b for b in container.find_elements(By.XPATH, './/button')
                            if b.is_displayed() and not is_disabled(b)]
            if icon_buttons:
                driver.execute_script("arguments[0].click();", icon_buttons[-1])
                time.sleep(2)
                if not editor_value():
                    return True

            # 最后兜底：新版纸飞机固定在输入框容器右下角，按容器坐标点击。
            rect = driver.execute_script("""
                const r = arguments[0].getBoundingClientRect();
                return {left:r.left, top:r.top, width:r.width, height:r.height};
            """, container)
            if rect and rect['width'] > 100 and rect['height'] > 40:
                x = rect['left'] + rect['width'] - 28
                y = rect['top'] + rect['height'] - 28
                driver.execute_script("""
                    const el = document.elementFromPoint(arguments[0], arguments[1]);
                    if (el) el.click();
                """, x, y)
                time.sleep(2)
                if not editor_value():
                    return True
        except Exception:
            pass

        # 兜底：发表/发布/回复/提交 按钮
        btns = driver.find_elements(By.XPATH,
            '//button[contains(text(), "发表") or contains(text(), "发布") '
            'or contains(text(), "回复") or contains(text(), "提交")]')
        for b in btns:
            if b.is_displayed() and not is_disabled(b):
                driver.execute_script("arguments[0].click();", b)
                time.sleep(2)
                if not editor_value():
                    return True
        return False
    except Exception as e:
        error(f"发送失败: {e}")
        return False


def auto_answer_discussion(driver):
    """讨论作答主流程：获取主题 -> AI 生成发言 -> 自动填入并发送；成功返回 True"""
    info("开始处理讨论...")

    question = get_discussion_question(driver)
    if not question:
        warn("未获取到讨论主题")
        return False
    info(f"讨论主题: {question[:120]}")

    progress("AI 生成发言中...")
    answer = None
    for attempt in range(3):
        answer = generate_discussion_answer(question)
        if answer:
            break
        warn(f"第 {attempt + 1} 次生成失败，重试")
        time.sleep(0.5)
    if not answer:
        warn("AI 生成发言失败")
        return False
    ok(f"发言内容（{len(answer)} 字）: {answer}")

    posted = post_discussion(driver, answer)
    if posted:
        ok("讨论发言已发送")
    else:
        warn("发言已填入文本框，但未找到可点击的发送按钮")
    return posted
