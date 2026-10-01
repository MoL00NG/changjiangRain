# -*- coding: utf-8 -*-
"""作业答题主循环：截图 -> OCR -> AI 求解 -> 点击 -> 提交进入下一题"""

import time

from selenium.webdriver.common.by import By
from config import SCREENSHOT_PATH
from ai import solve_with_consensus
from ocr import ocr_image, clean_question
from browser import (
    check_if_done, get_question_container, screenshot_element,
    is_multi_choice, submit_current, handle_submit_confirm, go_next,
)
from clicker import click_answer
from util import section, info, ok, warn, error, progress


def auto_answer(driver):
    """自动答完一份作业的全部题目"""
    info("开始自动答题，每道题 AI 会思考多次并取共识")

    # 新版雨课堂把题目放在 iframe-exercise 内，必须先切换到 iframe。
    try:
        driver.switch_to.default_content()
        switched = False
        for _ in range(10):
            frames = driver.find_elements(By.XPATH, '//iframe[contains(@src, "iframe-exercise")]')
            if frames:
                driver.switch_to.frame(frames[0])
                info("已切换到新版作业题目 iframe")
                switched = True
                break
            time.sleep(0.5)
        if not switched:
            # 兼容 src 尚未填充或页面使用无 src 的 iframe 的情况
            all_frames = driver.find_elements(By.TAG_NAME, 'iframe')
            if all_frames:
                driver.switch_to.frame(all_frames[0])
                info("已切换到作业 iframe")
            else:
                warn("未找到作业 iframe")
        time.sleep(1)
    except Exception as e:
        warn(f"切换作业 iframe 失败: {e}")

    question_count = 0
    answered_count = 0

    while True:
        if check_if_done(driver):
            ok("所有题目已完成！")
            break

        container = get_question_container(driver)
        if not container:
            warn("找不到题目容器，可能已提交完成")
            break

        question_count += 1
        section(f"第 {question_count} 题")

        # 截图
        screenshot_path = screenshot_element(driver, container, SCREENSHOT_PATH)
        if not screenshot_path:
            error("截图失败")
            input("按 Enter 继续...")
            continue

        # OCR
        progress("OCR 识别中...")
        ocr_lines = ocr_image(screenshot_path)

        if not ocr_lines:
            error("OCR 失败")
            answer = input("请输入答案: ").strip().upper()
            if not answer:
                warn("跳过本题")
                input("按 Enter 继续...")
                continue
        else:
            # 清理文本，保留题干与选项，并判断题型
            question_text, q_type = clean_question(ocr_lines)

            # 从 HTML 判断是否多选（更准确）；投票题也可能是多选
            is_multi = is_multi_choice(driver) or q_type == '投票题'

            info(f"题型: {q_type} | 是否多选: {is_multi}")
            info(f"整理后文本:\n{question_text}")

            # 判断题选项是 SVG 图标，OCR 读不到文字，手动补上让 AI 作答
            if q_type == '判断题' and '选项' not in question_text:
                question_text += "\n选项：\nA. 对\nB. 错"

            if '题干' not in question_text and '选项' not in question_text:
                warn("未识别到题干/选项，请确认截图内容")

            # AI 求解（传入是否多选）
            answer = solve_with_consensus(question_text, is_multi=is_multi)

            if answer is None:
                warn("AI 无法确定答案")
                answer = input("请输入答案: ").strip().upper()
                if not answer:
                    warn("跳过本题")
                    input("按 Enter 继续...")
                    continue
            else:
                ok(f"最终答案: {answer}")

        # 点击答案
        info(f"选择: {answer}")
        if click_answer(driver, answer):
            answered_count += 1
            ok("已选择")
        else:
            warn("点击失败，请手动选择")

        info(f"第 {question_count} 题完成")
        time.sleep(0.5)

        # 点击“提交”——提交本题答案后会自动进入下一题
        if not submit_current(driver):
            # 提交不可用时退回“下一题”按钮
            if go_next(driver):
                continue
            ok("作业已完成（提交/下一题均不可用，最后一题作答后自动交卷）")
            break

        # 若出现确认弹窗（通常最后一题交卷时），点击确认完成提交
        if handle_submit_confirm(driver):
            ok("作业已最终提交")
            break

    info(f"共 {question_count} 题，已选 {answered_count} 题")
