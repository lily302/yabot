import requests
import time
import os

def login_and_execute_tasks():
    # 创建 Session 对象，自动管理 Cookie
    session = requests.Session()
    
    # 通用请求头
    headers = {
        "Accept": "*/*",
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "Cache-Control": "no-cache"
    }

    # 从环境变量读取配置
    server_url = os.getenv("SERVER_URL", "http://your-server:3000/")
    # 确保 server_url 末尾没有斜杠
    server_url = server_url.rstrip('/')
    # 动态生成 URL
    login_url = f"{server_url}/api/auth/login"
    execute_url = f"{server_url}/api/tasks/executeAll"
    username = os.getenv("USERNAME", "your_username")
    password = os.getenv("PASSWORD", "your_password")

    # 步骤 1：获取初始 Cookie
    print("正在获取初始 Cookie...")
    try:
        response = session.get(server_url, headers=headers, timeout=10)
        response.raise_for_status()
        print("初始 Cookie 获取成功:", session.cookies.get_dict())
    except requests.exceptions.RequestException as e:
        print(f"初始请求失败: {e}")
        return False

    # 步骤 2：登录
    print("正在登录...")
    login_data = {
        "username": username,
        "password": password
    }
    try:
        response = session.post(login_url, json=login_data, headers=headers, timeout=10)
        response.raise_for_status()
        print("登录成功:", response.json())
    except requests.exceptions.RequestException as e:
        print(f"登录失败: {e}")
        print("登录响应:", response.text if 'response' in locals() else "无响应")
        return False

    # 步骤 3：执行任务
    print("正在执行任务...")
    try:
        response = session.post(execute_url, headers=headers, timeout=10)
        response.raise_for_status()
        print("任务执行成功:", response.json())
        return True
    except requests.exceptions.RequestException as e:
        print(f"任务执行失败: {e}")
        print("执行响应:", response.text if 'response' in locals() else "无响应")
        return False

# 主程序：带重试逻辑
max_retries = 3
retry_delay = 5  # 秒

for attempt in range(max_retries):
    print(f"\n尝试第 {attempt + 1} 次...")
    if login_and_execute_tasks():
        print("脚本执行成功！")
        break
    else:
        if attempt < max_retries - 1:
            print(f"等待 {retry_delay} 秒后重试...")
            time.sleep(retry_delay)
        else:
            print("达到最大重试次数，脚本执行失败！")
            exit(1)