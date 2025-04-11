# delete_task.py（完整代码）
import requests
import os
import logging
from typing import List, Dict, Tuple

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

def login_and_get_tasks(task_name: str = "") -> Tuple[requests.Session, List[Dict], bool]:
    """登录并获取任务列表，支持按任务名称过滤，返回 (会话, 任务列表, 是否成功)"""
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
    tasks_url = f"{server_url}/api/tasks"
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
        return session, [], False

    # 步骤 2：登录
    logger.info("登录...")
    login_data = {"username": username, "password": password}
    try:
        response = session.post(login_url, json=login_data, headers=headers, timeout=10)
        response.raise_for_status()
        logger.info("登录成功: %s", response.json())
    except requests.exceptions.RequestException as e:
        logger.error("登录失败: %s", e)
        return session, [], False

    # 步骤 3：获取任务列表
    logger.info("获取任务列表...")
    try:
        response = session.get(tasks_url, headers=headers, timeout=10)
        response.raise_for_status()
        tasks = response.json()
        if not tasks.get("success"):
            logger.error("获取任务列表失败: %s", tasks.get("error", "未知错误"))
            return session, [], False
        task_list = tasks.get("data", [])
        if not task_list:
            logger.info("任务列表为空")
            return session, [], True

        # 按任务名称过滤
        if task_name:
            logger.info("根据任务名称 '%s' 过滤任务...", task_name)
            filtered_tasks = []
            for task in task_list:
                resource_name = task.get("resourceName", "")
                share_folder_name = task.get("shareFolderName", "")
                full_name = f"{resource_name}/{share_folder_name}" if share_folder_name else resource_name
                if task_name.lower() in full_name.lower():
                    filtered_tasks.append(task)
            task_list = filtered_tasks

        return session, task_list, True
    except requests.exceptions.RequestException as e:
        logger.error("获取任务列表失败: %s", e)
        return session, [], False

def delete_task_by_id(session: requests.Session, task_id: str, delete_cloud: bool) -> Tuple[bool, str]:
    """根据任务 ID 删除任务，返回 (是否成功, 错误信息)"""
    server_url = os.getenv("SERVER_URL", "http://your-server:3000").rstrip('/')
    headers = {
        "Accept": "*/*",
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "Cache-Control": "no-cache"
    }

    delete_task_url = f"{server_url}/api/tasks/{task_id}"
    logger.info("删除任务 ID: %s...", task_id)
    try:
        response = session.delete(delete_task_url, json={"deleteCloud": delete_cloud}, headers=headers, timeout=10)
        response.raise_for_status()
        result = response.json()
        if not result.get("success"):
            error_msg = result.get("error", "未知错误")
            logger.error("任务 %s 删除失败: %s", task_id, error_msg)
            return False, error_msg
        logger.info("任务 %s 删除成功", task_id)
        return True, ""
    except requests.exceptions.RequestException as e:
        logger.error("任务 %s 删除失败: %s", task_id, e)
        return False, str(e)