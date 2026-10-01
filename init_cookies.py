# -*- coding: utf-8 -*-
"""旧版 Cookie 初始化入口的兼容提示。新版本通过 main.py 自动扫码登录。"""


def main():
    print('新版无需手动创建或编辑 Cookie 文件。')
    print('请在项目目录运行：python main.py')
    print('程序会打开 Edge；如需登录，请扫码，随后自动保存本机登录状态。')
    print('请勿分享 cache/cookies.json，它等同于账号登录凭证。')


if __name__ == '__main__':
    main()
