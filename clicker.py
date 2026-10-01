# -*- coding: utf-8 -*-
"""点击答案：选择题（含多选/投票题）、判断题（文字 / SVG 图标 / 顺序兜底）"""

import time

from selenium.webdriver.common.by import By

from util import ok, warn, error


def click_answer(driver, answer):
    if not answer:
        warn("答案为空")
        return False

    answer = answer.upper().strip()
    answers = [a.strip() for a in answer.split(',')]

    try:
        # 判断题：选项是 SVG 图标（#icon--tiankongtizhengque=正确 / #icon--tiankongticuowu=错误），没有文字
        if answer in ['对', '错']:
            return click_judgment(driver, answer)

        # 选择题：同时找 checkbox 和 radio
        labels = driver.find_elements(By.XPATH, '//label[contains(@class, "el-checkbox") or contains(@class, "el-radio")]')

        # 新版雨课堂将选项渲染为原生 radio/checkbox 或 ARIA radio，而非 Element UI 的 label。
        if not labels:
            labels = driver.find_elements(By.XPATH,
                '//input[@type="radio" or @type="checkbox"] | //*[@role="radio" or @role="checkbox"]')

        if not labels:
            warn("找不到选项")
            return False

        for ans in answers:
            idx = ord(ans) - ord('A')
            if 0 <= idx < len(labels):
                driver.execute_script("arguments[0].click();", labels[idx])
                time.sleep(0.2)
                ok(f"已选: {ans}")
            else:
                warn(f"无效选项: {ans}")

        return True

    except Exception as e:
        error(f"点击失败: {e}")
        return False


def click_judgment(driver, answer):
    """点击判断题选项：优先按文字，其次按 SVG 图标，最后按顺序兜底"""
    # 1) 按文字匹配（普通判断题）
    targets = ['对', '正确', '√'] if answer == '对' else ['错', '错误', '×']
    try:
        labels = driver.find_elements(By.XPATH, '//label[contains(@class, "el-checkbox") or contains(@class, "el-radio")]')
        for label in labels:
            for t in targets:
                if t in label.text:
                    driver.execute_script("arguments[0].click();", label)
                    time.sleep(0.3)
                    ok(f"已选: {answer}")
                    return True
    except Exception:
        pass

    # 2) 按 SVG 图标匹配（雨课堂判断题：zhengque=正确 / cuowu=错误）
    icon_href = 'zhengque' if answer == '对' else 'cuowu'
    try:
        icon = driver.find_element(By.XPATH, f'//use[contains(@xlink:href, "{icon_href}") or contains(@href, "{icon_href}")]')
        # 找它所在的 label 作为可点击目标；没有 label 就点图标本身（点击事件会冒泡）
        try:
            clickable = icon.find_element(By.XPATH, 'ancestor::label[1]')
        except Exception:
            clickable = icon
        driver.execute_script("arguments[0].click();", clickable)
        time.sleep(0.3)
        ok(f"已选: {answer}（SVG 图标）")
        return True
    except Exception:
        pass

    # 3) 顺序兜底：判断题通常第 1 个是“对”、第 2 个是“错”
    try:
        labels = driver.find_elements(By.XPATH, '//label[contains(@class, "el-checkbox") or contains(@class, "el-radio")]')
        if len(labels) >= 2:
            idx = 0 if answer == '对' else 1
            driver.execute_script("arguments[0].click();", labels[idx])
            time.sleep(0.3)
            warn(f"已选: {answer}（按顺序点第 {idx + 1} 个，请留意是否正确）")
            return True
    except Exception:
        pass

    warn("找不到判断题选项")
    return False
