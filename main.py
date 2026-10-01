# -*- coding: utf-8 -*-
"""程序入口：自动准备虚拟环境、扫码登录和选择课程。"""


def _run_application():
    import time

    import auth
    import discussion
    import runner
    from browser import click_score_tab, get_driver_with_cookies, is_list_page
    from config import DEEPSEEK_API_KEY
    from util import error, info, section, warn

    section('雨课堂讨论/视频/图文辅助工具（作业手动完成）')
    info('将自动打开 Edge；首次登录时请使用雨课堂官方扫码方式登录。')
    info('Cookie 只保存在本机 cache/cookies.json，课程由你从列表中选择。')

    info('正在打开雨课堂浏览器...')
    try:
        driver = get_driver_with_cookies(auth.HOME_URL)
    except Exception as exc:
        error(f'启动 Edge 失败：{exc}')
        info('请确认已安装 Microsoft Edge，并检查网络连接后重试。')
        return

    if not auth.wait_for_login(driver):
        driver.quit()
        return

    courses = auth.list_courses(driver)
    if courses is None:
        warn('无法读取课程列表。请确认账号已加入课程，并检查登录状态。')
        info('浏览器保持打开，你可以在浏览器中检查登录状态。')
        input('按 Enter 退出...')
        return
    if not courses:
        warn('当前账号的课程列表为空。请确认扫码登录的是正确账号。')
        input('按 Enter 退出...')
        return

    university_id = auth._university_id(driver)
    while True:
        batch = auth.choose_courses(courses, university_id)
        if not batch:
            info('已结束课程选择。')
            break

        for batch_index, (course, course_url) in enumerate(batch, start=1):
            info(f"开始处理本批第 {batch_index}/{len(batch)} 门课程：{course['name']}")
            try:
                driver.get(course_url)
                time.sleep(3)
                click_score_tab(driver)  # 兼容旧版页面；新版列表由 runner 切换。
                if is_list_page(driver):
                    runner.auto_answer_list(driver, course_url)
                elif discussion.is_discussion_page(driver):
                    if DEEPSEEK_API_KEY:
                        discussion.auto_answer_discussion(driver)
                    else:
                        warn('未配置 DeepSeek API Key，跳过讨论；视频和图文仍可使用。')
                else:
                    warn('未识别到课程列表；作业和考试页面需要手动完成。')
            except Exception as exc:
                error(f"处理课程“{course['name']}”时发生错误：{exc}")
                continue
            info(f"课程“{course['name']}”处理结束。")

        info('当前批次课程已处理完毕，可以继续选择其他课程。')

    info('浏览器保持打开')
    input('按 Enter 退出...')


def main():
    # 延迟导入 Selenium 等第三方包，先由纯标准库启动器准备 venv 与依赖。
    from launcher import ensure_project_environment

    if ensure_project_environment():
        _run_application()


if __name__ == '__main__':
    main()
