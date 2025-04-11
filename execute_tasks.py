import requests
import time
import os
import logging

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

def login_and_execute_tasks():
    """登录并执行所有任务"""
    session = requests.Session()
    headers = {
        "Accept": "*/*",
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "Cache-Control": "no-cache"
    }

    # 从环境变量读取配置
    server_url = os.getenv("SERVER_URL", "http://your-server:3000").rstrip('/')
    login_url = f"{server_url}/api/auth/login"
    execute_url = f"{server_url}/api/tasks/executeAll"
    username = os.getenv("USERNAME", "your_username")
    password = os.getenv("PASSWORD", "your_password")

    # 步骤 1：获取初始 Cookie
    logger.info("获取初始 Cookie...")
    try:
        response = session.get(server_url, headers=headers, timeout=10)
        response.raise_for_status()
        logger.info("初始 Cookie 获取成功: %s", session.cookies.get_dict())
    except requests.exceptions.RequestException as e:
        logger.error("初始请求失败: %s", e)
        return False

    # 步骤 2：登录
    logger.info("登录...")
    login_data = {"username": username, "password": password}
    try:
        response = session.post(login_url, json=login_data, headers=headers, timeout=10)
        response.raise_for_status()
        logger.info("登录成功: %s", response.json())
    except requests.exceptions.RequestException as e:
        logger.error("登录失败: %s", e)
        logger.error("登录响应: %s", response.text if 'response' in locals() else "无响应")
        return False

    # 步骤 3：执行所有任务
    logger.info("执行所有任务...")
    try:
        response = session.post(execute_url, headers=headers, timeout=10)
        response.raise_for_status()
        result = response.json()
        if not result.get("success"):
            logger.error("任务执行失败: %s", result.get("error", "未知错误"))
            return False
        logger.info("任务执行成功: %s", result)
        return True
    except requests.exceptions.RequestException as e:
        logger.error("任务执行失败: %s", e)
        logger.error("执行响应: %s", response.text if 'response' in locals() else "无响应")
        return False

def main():
    max_retries = 3
    retry_delay = 5  # 秒

    for attempt in range(max_retries):
        logger.info("尝试第 %s 次...", attempt + 1)
        if login_and_execute_tasks():
            logger.info("脚本执行成功！")
            break
        else:
            if attempt < max_retries - 1:
                logger.info("等待 %s 秒后重试...", retry_delay)
                time.sleep(retry_delay)
            else:
                logger.error("达到最大重试次数，脚本执行失败！")
                exit(1)

if __name__ == "__main__":
    main()