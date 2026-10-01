# 长江雨课堂讨论、视频与图文辅助工具

本项目由 GitHub 用户 [MoL00NG](https://github.com/MoL00NG) 提出并发起，是其个人仓库项目，面向长江雨课堂新版课程页面，提供讨论、视频和图文学习辅助功能。MoL00NG 是本仓库唯一的主要贡献者。项目部分思路与实现参考了下方列出的上游开源项目，并在致谢中注明来源。

> 作业和考试需要自行完成。本项目不会自动打开、作答或提交作业、考试页面，也不是雨课堂官方工具。

## 从下载到运行

以下步骤适合第一次使用 Python 的 Windows 用户。除安装 Python、下载项目外，虚拟环境和依赖会在首次运行时自动准备。

### 1. 安装必需软件

安装 **64 位 Python 3.10 或更高版本**、Microsoft Edge 和 Git for Windows。安装 Python 时勾选 **Add Python to PATH**。

安装后重新打开 PowerShell，确认 Python 和 Git 可用：

```powershell
python --version
git --version
```

如果提示“无法识别”，请重新安装对应软件并重开 PowerShell。

### 2. 下载项目

打开 PowerShell，逐行复制执行：

```powershell
cd $HOME\Desktop
git clone https://github.com/MoL00NG/changjiangRain.git
cd changjiangRain
```

如果不想安装 Git，也可以在 GitHub 项目页面点 **Code → Download ZIP**，解压到桌面，然后在 PowerShell 中进入解压后的项目文件夹。

### 3. 首次启动并自动安装运行环境

在项目文件夹中执行：

```powershell
python .\main.py
```

首次启动时，程序会自动创建项目专用的 `.venv` 虚拟环境、安装依赖，并在新环境中重新启动。安装过程中请保持 PowerShell 打开并等待完成；以后再运行时会跳过已完成的安装。

如果依赖安装失败，检查网络后重新执行 `python .\main.py` 即可继续。

### 4. 扫码登录雨课堂

程序会打开一个 Edge 窗口：

- 如果登录状态仍有效，程序会直接继续。
- 首次使用或登录已过期时，请用手机扫描 Edge 页面上的雨课堂登录二维码，并在手机上确认登录。
- 登录成功后，程序会自动读取完成登录所需的 Cookie，并保存到本机 `cache/cookies.json`。终端不会显示 Cookie 内容。

Cookie 等同于账号登录凭证。不要把 `cache/cookies.json` 上传、截图或发给他人。项目已将此文件加入 Git 忽略规则。

### 5. 选择课程

登录后，终端会显示账号可访问的课程编号和课程名称。输入课程编号并按 Enter 即可选择；也可以输入课程名称中的关键词。如果多门课程名称相近，按提示输入对应编号。

学校编号会优先从当前页面地址或登录 Cookie 中读取。课程列表为空时，请确认 Edge 中登录的是正确账号并已加入课程；如果仍为空，请检查 `config.py` 中 `UNIVERSITY_ID` 的兜底值是否与学校编号一致。旧版课程主页链接中的 `university_id` 参数可供核对。

### 6. 处理课程内容

程序会打开所选课程并扫描未完成的讨论、视频和图文。讨论功能需要 DeepSeek API Key；视频和图文不需要。没有配置 Key 时，程序会跳过讨论并继续处理其他支持的内容。

作业和考试不会被程序打开或自动完成。处理结束后，按 PowerShell 中的提示按 Enter 退出；Edge 会保持打开，方便你查看页面状态。

## 配置讨论功能（可选）

只有希望使用自动生成讨论发言时才需要 DeepSeek API Key。

1. 登录 DeepSeek 开放平台，在 **API Keys** 页面创建并复制一个 Key。
2. 在 PowerShell 中设置当前窗口变量，将示例替换为自己的 Key：

```powershell
$env:DEEPSEEK_API_KEY = "sk-你的Key"
```

3. 在同一个 PowerShell 窗口运行：

```powershell
cd $HOME\Desktop\changjiangRain
python .\main.py
```

如果希望以后新开的 PowerShell 窗口也能使用，可运行 `setx DEEPSEEK_API_KEY "sk-你的Key"`，然后关闭并重新打开 PowerShell。不要将真实 Key 写入代码、提交到 GitHub 或分享给他人。

## 以后如何启动

每次打开 PowerShell 后执行：

```powershell
cd $HOME\Desktop\changjiangRain
python .\main.py
```

无需手动激活虚拟环境，也无需每次重新填写 Cookie 或课程链接。登录过期时，程序会重新打开登录页面让你扫码。

更新项目代码时，在项目文件夹执行：

```powershell
git pull --ff-only
python .\main.py
```

如果项目依赖有变化，启动器会根据 `requirements.txt` 自动更新虚拟环境。

## 可选：调整图文处理间隔

可以在 `config.py` 中修改以下数值；不确定时保留默认值：

```python
RICHTEXT_STAY_SECONDS = 3  # 每篇图文处理前的停留秒数
RICHTEXT_SKIP_DELAY = 1   # 两篇图文之间的间隔秒数
```

## 常见问题

### 找不到 Python 或 Git

安装后请重新打开 PowerShell。安装 Python 时确认勾选 **Add Python to PATH**。

### 自动创建环境或安装依赖失败

确认电脑已安装 64 位 Python 3.10 或更高版本并能访问网络，然后重新运行：

```powershell
python .\main.py
```

### 扫码后仍提示登录失败

确认扫描的是 Edge 窗口中长江雨课堂页面的二维码，并在手机上完成确认。等待超时后重新运行程序即可再次扫码。

### 提示 Cookie 失效

程序会重新打开登录页面。扫码成功后会自动更新本机 Cookie 文件。

### DeepSeek API 错误 401

检查 Key 是否有效，并确认在同一个 PowerShell 窗口设置了 `DEEPSEEK_API_KEY`。视频和图文可以不配置 Key；讨论功能需要有效 Key。

### OCR 模型首次下载失败

检查网络后重新运行程序；也可以在项目文件夹运行：

```powershell
python .\install_models.py
```

## 免责声明

本项目为非官方的个人学习与技术研究工具，仅供合法、合规的学习研究用途。使用者应自行确认并遵守所在学校、课程教师及雨课堂平台的相关规定与服务条款，不得将本项目用于代替本人完成应当独立完成的学习或考核任务。

使用本项目产生的一切行为、学习记录变化、账号或课程风险均由使用者自行承担。仓库所有者与贡献者不对因使用、误用或无法使用本项目造成的任何直接或间接后果负责。请妥善保管 Cookie、API Key 等凭证，切勿上传、泄露或分享。

## 致谢与来源

项目提出者、仓库所有者及唯一主要贡献者：[MoL00NG](https://github.com/MoL00NG)。本项目部分思路与实现参考以下上游开源项目，感谢原项目作者及贡献者：

- [hewei2723/yuketang](https://github.com/hewei2723/yuketang)：原始讨论、课程自动化项目。
- [Gary-666/yuketang](https://github.com/Gary-666/yuketang)：图文节点发现与图文完成流程参考。

本仓库围绕项目提出者的需求，对新版长江雨课堂页面进行整合与适配。上述上游项目及其作者保留原有署名与版权；如需确认具体代码来源，请查看对应上游仓库和本仓库 Git 历史。
