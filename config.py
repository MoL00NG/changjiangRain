# -*- coding: utf-8 -*-
"""全局配置：路径、API 与运行参数"""

import os

# ==================== 运行目录 ====================
# 自动定位到本文件所在目录，兼容从任意位置运行
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
COOKIE_PATH = os.path.join(PROJECT_DIR, "cache", "cookies.json")
SCREENSHOT_PATH = os.path.join(PROJECT_DIR, "question.png")

os.chdir(PROJECT_DIR)

# ==================== DeepSeek API 配置 ====================
# 出于安全考虑，API Key 不再硬编码在代码中：
#   方式一（推荐）：设置环境变量 DEEPSEEK_API_KEY
#     Windows:  setx DEEPSEEK_API_KEY "sk-xxxx"
#     Linux:    export DEEPSEEK_API_KEY="sk-xxxx"
#   方式二：直接修改下方默认值，但提交代码前请务必改回空字符串
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_MODEL = "deepseek-v4-flash"
DEEPSEEK_BASE_URL = "https://api.deepseek.com"

# ==================== 答题参数 ====================
MAX_RETRIES = 2      # 每道选择题 AI 思考次数
MIN_CONSENSUS = 2    # 达到几次相同答案即采用

# ==================== 讨论发言参数 ====================
DISCUSSION_MIN_LEN = 150  # 讨论发言最少字数
DISCUSSION_MAX_LEN = 300  # 讨论发言最多字数（AI 在此范围内自行把握篇幅）

# ==================== 视频刷课参数 ====================
UNIVERSITY_ID = ""          # 可选的学校编号兜底值；通常无需填写，运行时会从课程链接自动读取
VIDEO_LEARNING_RATE = 40    # 每条心跳推进的播放秒数（越大刷得越快）
VIDEO_HEARTBEAT_BATCH = 65  # 每轮发送的心跳条数

# ==================== 图文学习参数 ====================
# 每篇图文完成前的阅读停留时间，以及两篇之间的请求间隔。
RICHTEXT_STAY_SECONDS = 3
RICHTEXT_SKIP_DELAY = 1
