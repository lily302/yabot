import requests
import time
import argparse
import os

def login_and_create_task(share_link, access_code=""):
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
    accounts_url = f"{server_url}/api/accounts"
    create_task_url = f"{server_url}/api/tasks"
    tasks_url = f"{server_url}/api/tasks"
    username = os.getenv("USERNAME", "your_username")
    password = os.getenv("PASSWORD", "your_password")
    target_folder_id = os.getenv("TARGET_FOLDER_ID", "your_target_folder_id")

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

    # 步骤 3：获取账号列表
    print("正在获取账号列表...")
    try:
        response = session.get(accounts_url, headers=headers, timeout=10)
        response.raise_for_status()
        accounts = response.json()
        print("账号列表:", accounts)
        # 取第一个账号的 ID
        account_id = str(accounts.get("data", [{}])[0].get("id")) if accounts.get("data") else None
        if not account_id:
            print("未找到有效的账号 ID")
            return False
        print(f"使用账号 ID: {account_id}")
    except requests.exceptions.RequestException as e:
        print(f"获取账号列表失败: {e}")
        print("响应:", response.text if 'response' in locals() else "无响应")
        return False

    # 步骤 4：获取文件夹列表
    print("正在获取文件夹列表...")
    print(f"使用目标文件夹 ID: {target_folder_id}")

    # 步骤 5：创建任务
    print("正在创建任务...")
    task_data = {
        "accountId": account_id,
        "shareLink": share_link,
        "totalEpisodes": "",
        "accessCode": access_code,
        "cronExpression": "",
        "enableCron": False,
        "matchOperator": "lt",
        "matchPattern": "",
        "matchValue": "",
        "overwriteFolder": 1,
        "remark": "",
        "targetFolderId": target_folder_id
    }
    try:
        response = session.post(create_task_url, json=task_data, headers=headers, timeout=10)
        response.raise_for_status()
        result = response.json()
        print("任务创建结果:", result)
        if not result.get("success"):
            print(f"任务创建失败: {result.get('error')}")
            return False
        # 获取任务 ID
        task_id = str(result.get("data", [{}])[0].get("id")) if result.get("data") else None
        if not task_id:
            print("未找到任务 ID")
            return False
        print(f"任务 ID: {task_id}")
    except requests.exceptions.RequestException as e:
        print(f"任务创建失败: {e}")
        print("创建响应:", response.text if 'response' in locals() else "无响应")
        return False

    # 步骤 6：执行任务
    print("正在执行任务...")
    execute_task_url = f"{server_url}/api/tasks/{task_id}/execute"
    try:
        response = session.post(execute_task_url, headers=headers, timeout=10)
        response.raise_for_status()
        result = response.json()
        print("任务执行结果:", result)
        if not result.get("success"):
            print(f"任务执行失败: {result.get('error')}")
            return False
    except requests.exceptions.RequestException as e:
        print(f"任务执行失败: {e}")
        print("执行响应:", response.text if 'response' in locals() else "无响应")
        return False

    # 步骤 7：检查任务状态
    print("正在检查任务状态...")
    max_wait_attempts = 10
    wait_interval = 10  # 秒
    for attempt in range(max_wait_attempts):
        try:
            response = session.get(tasks_url, headers=headers, timeout=10)
            response.raise_for_status()
            tasks = response.json()
            print("任务列表:", tasks)
            # 查找当前任务的状态
            task_status = None
            current_episodes = 0
            last_error = None
            for task in tasks.get("data", []):
                if str(task.get("id")) == task_id:
                    task_status = task.get("status")
                    current_episodes = task.get("currentEpisodes", 0)
                    last_error = task.get("lastError")
                    print(f"任务 {task_id} 状态: {task_status}")
                    print(f"已转存文件数: {current_episodes}")
                    if last_error:
                        print(f"任务错误: {last_error}")
                        return False
                    break
            # 如果有文件转存且无错误，认为任务成功
            if current_episodes > 0 and last_error is None:
                print("文件已转存，任务视为成功！")
                return True
            # 否则继续等待状态变为 completed 或 failed
            if task_status in ["completed", "failed"]:
                break
            print(f"任务仍在处理中，等待 {wait_interval} 秒后重试... (尝试 {attempt + 1}/{max_wait_attempts})")
            time.sleep(wait_interval)
        except requests.exceptions.RequestException as e:
            print(f"获取任务列表失败: {e}")
            print("响应:", response.text if 'response' in locals() else "无响应")
            return False

    if task_status != "completed":
        print("任务未能在预期时间内完成状态更新，但文件可能已转存，请检查目标文件夹")
        return True  # 文件已转存，视为成功

    return True

# 主程序：处理命令行参数
def main():
    # 设置命令行参数
    parser = argparse.ArgumentParser(description="创建天翼云盘转存任务")
    parser.add_argument("--share-link", required=True, help="天翼云盘分享链接（必填）")
    parser.add_argument("--access-code", default="", help="分享链接的访问密码（可选）")
    args = parser.parse_args()

    # 获取参数
    share_link = args.share_link
    access_code = args.access_code

    # 验证分享链接格式
    if not share_link.startswith("https://cloud.189.cn/t/"):
        print("错误：分享链接必须是天翼云盘链接（以 https://cloud.189.cn/t/ 开头）")
        exit(1)

    # 打印参数
    print(f"分享链接: {share_link}")
    print(f"访问密码: {access_code if access_code else '无'}")

    # 带重试逻辑
    max_retries = 3
    retry_delay = 5  # 秒

    for attempt in range(max_retries):
        print(f"\n尝试第 {attempt + 1} 次...")
        if login_and_create_task(share_link, access_code):
            print("脚本执行成功！")
            break
        else:
            if attempt < max_retries - 1:
                print(f"等待 {retry_delay} 秒后重试...")
                time.sleep(retry_delay)
            else:
                print("达到最大重试次数，脚本执行失败！")
                exit(1)

if __name__ == "__main__":
    main()