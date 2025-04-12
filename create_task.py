import requests
import time
import argparse
import os
import logging
import sqlite3
from typing import List, Tuple, Optional

# 配置日志
def setup_logging():
    log_dir = "/app/logs"
    log_file = os.path.join(log_dir, "yabot.log")

    try:
        os.makedirs(log_dir, exist_ok=True)
    except Exception as e:
        print(f"无法创建日志目录 {log_dir}: {e}")

    handlers = [logging.StreamHandler()]
    try:
        file_handler = logging.FileHandler(log_file)
        handlers.append(file_handler)
    except Exception as e:
        print(f"无法初始化日志文件 {log_file}: {e}")

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=handlers
    )

setup_logging()
logger = logging.getLogger(__name__)

# 数据库路径（与 yabot.py 保持一致）
DB_PATH = os.getenv("DB_PATH", "/app/data/messages.db")

def init_db():
    """初始化数据库，创建 root_folders 表"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS root_folders (
            name TEXT NOT NULL,
            folder_id TEXT NOT NULL,
            parent_id TEXT NOT NULL,
            PRIMARY KEY (folder_id)
        )
    """)
    conn.commit()
    conn.close()

def get_folder_tree(session: requests.Session, server_url: str, account_id: str, folder_id: str = "-11") -> List[dict]:
    """获取账号的目录树"""
    headers = {
        "Accept": "*/*",
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "Cache-Control": "no-cache"
    }
    url = f"{server_url}/api/folders/{account_id}?folderId={folder_id}"
    try:
        response = session.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()
        if not data.get("success"):
            logger.error("获取目录失败: %s", data.get("error", "未知错误"))
            return []
        return data.get("data", [])
    except requests.exceptions.RequestException as e:
        logger.error("获取目录失败: %s", e)
        return []

def flatten_folder_tree(session: requests.Session, server_url: str, account_id: str, folders: List[dict], prefix: str = "") -> List[Tuple[str, str]]:
    """将目录树展平为 (名称路径, ID) 的列表"""
    result = []
    for folder in folders:
        path = f"{prefix}/{folder['name']}" if prefix else folder['name']
        result.append((path, folder['id']))
        sub_folders = get_folder_tree(session, server_url, account_id, folder['id'])
        result.extend(flatten_folder_tree(session, server_url, account_id, sub_folders, path))
    return result

def save_root_folders(session: requests.Session, server_url: str, account_id: str):
    """保存根目录信息到数据库"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("SELECT COUNT(*) FROM root_folders WHERE parent_id = '-11'")
    if cursor.fetchone()[0] > 0:
        conn.close()
        return
    
    logger.info("查询根目录 API 响应 (folderId=-11)")
    folders = get_folder_tree(session, server_url, account_id, folder_id="-11")
    for folder in folders:
        name = folder['name']
        folder_id = folder['id']
        parent_id = folder['pId']
        cursor.execute(
            "INSERT OR REPLACE INTO root_folders (name, folder_id, parent_id) VALUES (?, ?, ?)",
            (name, folder_id, parent_id)
        )
        logger.info(f"保存根目录: {name} (ID: {folder_id})")
    conn.commit()
    conn.close()

def get_my_transfers_folder_id():
    """从数据库获取 '我的转存' 的 folder_id"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT folder_id FROM root_folders WHERE name = '我的转存' AND parent_id = '-11'"
    )
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else None

def get_folder_from_history(target_folder_id: str) -> Optional[str]:
    """从历史记录中获取目标目录路径"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT target_folder_name FROM messages WHERE target_folder_id = ? LIMIT 1",
        (target_folder_id,)
    )
    result = cursor.fetchone()
    conn.close()
    if result:
        folder_path = result[0]
        logger.info(f"直接从历史记录获取目标目录: {folder_path} (ID: {target_folder_id})")
        return folder_path
    return None

def update_history_folder(folder_path: str, folder_id: str):
    """更新历史记录（messages 表已通过 save_to_db 更新，这里无需额外操作）"""
    pass  # yabot.py 的 save_to_db 已记录历史，无需重复

def get_folder_name_by_id(session: requests.Session, server_url: str, account_id: str, folder_id: str, max_depth: int = 10) -> str:
    """通过目录 ID 获取目录名称及其完整路径，优化查找逻辑"""
    headers = {
        "Accept": "*/*",
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "Cache-Control": "no-cache"
    }

    # 步骤 1：优先从历史记录中查找
    folder_path = get_folder_from_history(folder_id)
    if folder_path:
        return folder_path

    # 步骤 2：从 '我的转存' 开始查找
    my_transfers_id = get_my_transfers_folder_id()
    if not my_transfers_id:
        logger.info("未找到 '我的转存' 目录，保存根目录信息")
        save_root_folders(session, server_url, account_id)
        my_transfers_id = get_my_transfers_folder_id()
        if not my_transfers_id:
            logger.warning("仍未找到 '我的转存' 目录，fallback 到根目录查找")

    def find_folder_recursive(current_folder_id: str, target_folder_id: str, current_path: List[str], visited: set, depth: int = 0) -> Optional[List[str]]:
        if depth >= max_depth:
            logger.error("达到最大递归深度 (%d)，仍未找到目录 ID: %s", max_depth, target_folder_id)
            return None

        if current_folder_id in visited:
            logger.error("检测到循环，目录 ID: %s 已访问", current_folder_id)
            return None

        visited.add(current_folder_id)
        url = f"{server_url}/api/folders/{account_id}?folderId={current_folder_id}"
        try:
            response = session.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            data = response.json()
            logger.info("查询目录 API 响应 (folderId=%s): %s", current_folder_id, data)
            if not data.get("success"):
                logger.error("查询目录失败: %s", data.get("error", "未知错误"))
                return None

            folder_data = data.get("data", {})
            if not folder_data:
                logger.warning("目录数据为空 (folderId=%s)", current_folder_id)
                return None

            if isinstance(folder_data, list):
                for folder in folder_data:
                    fid = str(folder.get("id"))
                    fname = folder.get("name") or folder.get("folderName") or "未分类"
                    if fid == target_folder_id:
                        return current_path + [fname]
                    sub_path = find_folder_recursive(fid, target_folder_id, current_path + [fname], visited, depth + 1)
                    if sub_path:
                        return sub_path
            elif isinstance(folder_data, dict):
                fid = str(folder_data.get("id"))
                fname = folder_data.get("name") or folder_data.get("folderName") or "未分类"
                if fid == target_folder_id:
                    return current_path + [fname]
            else:
                logger.warning("folder_data 格式不正确: %s", folder_data)
                return None
        except requests.exceptions.RequestException as e:
            logger.error("查询目录失败: %s", e)
            return None
        return None

    # 从 '我的转存' 开始查找
    path = None
    if my_transfers_id:
        logger.info("从 '我的转存' (ID: %s) 开始查找目标目录 ID: %s", my_transfers_id, folder_id)
        path = find_folder_recursive(my_transfers_id, folder_id, ["我的转存"], set())
    
    # 如果未找到，fallback 到根目录查找
    if not path:
        logger.info("在 '我的转存' 中未找到目标目录，fallback 到根目录查找目标目录 ID: %s", folder_id)
        path = find_folder_recursive("-11", folder_id, [], set())
    
    if not path:
        logger.error("未找到目标目录 ID: %s", folder_id)
        return "未分类"
    
    full_path = "/".join(path)
    logger.info("找到目标目录路径: %s (ID: %s)", full_path, folder_id)
    # 更新历史记录（由 yabot.py 的 save_to_db 负责）
    return full_path

def match_folder_by_name(session: requests.Session, server_url: str, account_id: str, folder_name: str) -> Tuple[str, str]:
    """根据文件夹名称模糊匹配目标文件夹"""
    logger.info("根据名称 '%s' 匹配文件夹...", folder_name)
    folders = get_folder_tree(session, server_url, account_id)
    if not folders:
        logger.error("无法获取目录树")
        return None, None

    flat_folders = flatten_folder_tree(session, server_url, account_id, folders)
    matches = [(path, fid) for path, fid in flat_folders if folder_name.lower() in path.lower()]
    if not matches:
        logger.error("未找到匹配 '%s' 的文件夹", folder_name)
        return None, None
    if len(matches) > 1:
        logger.warning("找到多个匹配 '%s' 的文件夹，选择第一个: %s", folder_name, matches[0][0])
    path, fid = matches[0]
    logger.info("匹配文件夹: %s (ID: %s)", path, fid)
    return path, fid

def parse_share_folders(session: requests.Session, server_url: str, account_id: str, share_link: str, access_code: str) -> List[str]:
    """解析分享链接获取文件夹列表"""
    headers = {
        "Accept": "*/*",
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "Cache-Control": "no-cache"
    }
    url = f"{server_url}/api/share/parse"
    payload = {"shareLink": share_link, "accountId": account_id, "accessCode": access_code}
    try:
        response = session.post(url, json=payload, headers=headers, timeout=10)
        response.raise_for_status()
        result = response.json()
        if not result.get("success"):
            logger.error("解析分享链接失败: %s", result.get("error", "未知错误"))
            return []
        return result.get("data", [])
    except requests.exceptions.RequestException as e:
        logger.error("解析分享链接失败: %s", e)
        return []

def login_and_create_task(share_link: str, access_code: str = "", target_folder_id: str = "", target_folder_name: str = "") -> tuple[bool, int, str, str]:
    """登录并创建转存任务，返回 (成功状态, 转存文件总数, 目标目录 ID, 目标目录名称)"""
    session = requests.Session()
    headers = {
        "Accept": "*/*",
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "Cache-Control": "no-cache"
    }

    server_url = os.getenv("SERVER_URL", "http://your-server:3000").rstrip('/')
    login_url = f"{server_url}/api/auth/login"
    accounts_url = f"{server_url}/api/accounts"
    create_task_url = f"{server_url}/api/tasks"
    tasks_url = f"{server_url}/api/tasks"
    username = os.getenv("USERNAME", "your_username")
    password = os.getenv("PASSWORD", "your_password")
    default_folder_id = os.getenv("TARGET_FOLDER_ID", "-11")

    logger.info("获取初始 Cookie...")
    try:
        response = session.get(server_url, headers=headers, timeout=10)
        response.raise_for_status()
        logger.info("初始 Cookie 获取成功: %s", session.cookies.get_dict())
    except requests.exceptions.RequestException as e:
        logger.error("初始请求失败: %s", e)
        return False, 0, "", ""

    logger.info("登录...")
    login_data = {"username": username, "password": password}
    try:
        response = session.post(login_url, json=login_data, headers=headers, timeout=10)
        response.raise_for_status()
        logger.info("登录成功: %s", response.json())
    except requests.exceptions.RequestException as e:
        logger.error("登录失败: %s", e)
        return False, 0, "", ""

    logger.info("获取账号列表...")
    try:
        response = session.get(accounts_url, headers=headers, timeout=10)
        response.raise_for_status()
        accounts = response.json()
        account_id = str(accounts.get("data", [{}])[0].get("id")) if accounts.get("data") else None
        if not account_id:
            logger.error("未找到有效的账号 ID")
            return False, 0, "", ""
        logger.info("使用账号 ID: %s", account_id)
    except requests.exceptions.RequestException as e:
        logger.error("获取账号列表失败: %s", e)
        return False, 0, "", ""

    logger.info("解析分享链接...")
    share_folders = parse_share_folders(session, server_url, account_id, share_link, access_code)
    if not share_folders:
        logger.error("未获取到分享文件夹")
        return False, 0, "", ""
    logger.info("分享文件夹: %s", share_folders)

    final_target_folder_id = ""
    final_target_folder_name = ""
    if target_folder_id:
        logger.info("使用指定目标文件夹 ID: %s", target_folder_id)
        final_target_folder_id = target_folder_id
        final_target_folder_name = get_folder_name_by_id(session, server_url, account_id, target_folder_id)
    elif target_folder_name:
        folder_path, matched_folder_id = match_folder_by_name(session, server_url, account_id, target_folder_name)
        if matched_folder_id:
            final_target_folder_id = matched_folder_id
            final_target_folder_name = folder_path
            logger.info("使用匹配文件夹: %s (ID: %s)", folder_path, final_target_folder_id)
        else:
            logger.warning("未找到匹配 '%s' 的文件夹，使用默认文件夹 ID: %s", target_folder_name, default_folder_id)
            final_target_folder_id = default_folder_id
            final_target_folder_name = get_folder_name_by_id(session, server_url, account_id, default_folder_id)
    else:
        logger.info("未指定文件夹，使用默认文件夹 ID: %s", default_folder_id)
        final_target_folder_id = default_folder_id
        final_target_folder_name = get_folder_name_by_id(session, server_url, account_id, default_folder_id)

    logger.info("创建任务...")
    task_data = {
        "accountId": account_id,
        "shareLink": share_link,
        "totalEpisodes": "",
        "accessCode": access_code,
        "cronExpression": "",
        "enableCron": False,
        "matchOperator": "",
        "matchPattern": "",
        "matchValue": "",
        "overwriteFolder": 1,
        "remark": "",
        "targetFolderId": final_target_folder_id,
        "targetFolder": final_target_folder_name,
        "selectedFolders": share_folders
    }
    try:
        response = session.post(create_task_url, json=task_data, headers=headers, timeout=10)
        response.raise_for_status()
        result = response.json()
        if not result.get("success"):
            logger.error("任务创建失败: %s", result.get("error"))
            return False, 0, final_target_folder_id, final_target_folder_name
        task_ids = [str(task.get("id")) for task in result.get("data", [])]
        if not task_ids:
            logger.error("未找到任务 ID")
            return False, 0, final_target_folder_id, final_target_folder_name
        logger.info("任务创建成功，任务 ID: %s", task_ids)
    except requests.exceptions.RequestException as e:
        logger.error("任务创建失败: %s", e)
        return False, 0, final_target_folder_id, final_target_folder_name

    logger.info("执行任务 %s...", task_ids)
    for task_id in task_ids:
        execute_task_url = f"{server_url}/api/tasks/{task_id}/execute"
        try:
            response = session.post(execute_task_url, headers=headers, timeout=10)
            response.raise_for_status()
            result = response.json()
            if not result.get("success"):
                logger.error("任务 %s 执行失败: %s", task_id, result.get("error"))
                continue
            logger.info("任务 %s 执行成功", task_id)
        except requests.exceptions.RequestException as e:
            logger.error("任务 %s 执行失败: %s", task_id, e)
            continue

    logger.info("检查任务状态...")
    max_wait_attempts = 10
    wait_interval = 10
    all_success = True
    total_transferred_files = 0

    for task_id in task_ids:
        task_transferred_files = 0
        for attempt in range(max_wait_attempts):
            try:
                response = session.get(tasks_url, headers=headers, timeout=10)
                response.raise_for_status()
                tasks = response.json()
                task_status = None
                current_episodes = 0
                last_error = None
                for task in tasks.get("data", []):
                    if str(task.get("id")) == task_id:
                        task_status = task.get("status")
                        current_episodes = task.get("currentEpisodes", 0)
                        last_error = task.get("lastError")
                        logger.info("任务 %s 状态: %s, 已转存文件数: %d", task_id, task_status, current_episodes)
                        if last_error:
                            logger.error("任务 %s 错误: %s", task_id, last_error)
                            all_success = False
                            break
                        if current_episodes > 0 and last_error is None:
                            logger.info("任务 %s 文件已转存，视为成功，无需继续检查", task_id)
                            task_transferred_files = current_episodes
                            break
                        if task_status in ["completed", "failed"]:
                            task_transferred_files = current_episodes
                            break
                if last_error or task_status == "failed":
                    all_success = False
                    break
                if current_episodes > 0 and last_error is None:
                    task_transferred_files = current_episodes
                    break
                if task_status == "completed":
                    logger.info("任务 %s 已完成", task_id)
                    task_transferred_files = current_episodes
                    break
                logger.info("任务 %s 仍在处理中，等待 %s 秒后重试... (尝试 %s/%s)", task_id, wait_interval, attempt + 1, max_wait_attempts)
                time.sleep(wait_interval)
            except requests.exceptions.RequestException as e:
                logger.error("获取任务 %s 状态失败: %s", task_id, e)
                all_success = False
                break
        else:
            logger.warning("任务 %s 未能在预期时间内完成，但可能已转存", task_id)
            task_transferred_files = current_episodes

        total_transferred_files += task_transferred_files
        logger.info("任务 %s 最终转存文件数: %d", task_id, task_transferred_files)

    logger.info("所有任务总计转存文件数: %d", total_transferred_files)
    return all_success, total_transferred_files, final_target_folder_id, final_target_folder_name

def main():
    init_db()  # 初始化数据库
    parser = argparse.ArgumentParser(description="创建天翼云盘转存任务，支持自定义目录")
    parser.add_argument("--share-link", required=True, help="天翼云盘分享链接（必填）")
    parser.add_argument("--access-code", default="", help="分享链接的访问密码（可选）")
    parser.add_argument("--target-folder-id", help="目标文件夹 ID（可选）")
    parser.add_argument("--target-folder-name", default="", help="目标文件夹名称（可选，模糊匹配）")
    args = parser.parse_args()

    share_link = args.share_link
    access_code = args.access_code
    target_folder_id = args.target_folder_id
    target_folder_name = args.target_folder_name

    if not share_link.startswith("https://cloud.189.cn/t/"):
        logger.error("分享链接必须是天翼云盘链接（以 https://cloud.189.cn/t/ 开头）")
        exit(1)

    logger.info("分享链接: %s", share_link)
    logger.info("访问密码: %s", access_code if access_code else "无")
    if target_folder_id:
        logger.info("指定目标文件夹 ID: %s", target_folder_id)
    elif target_folder_name:
        logger.info("指定目标文件夹名称: %s", target_folder_name)

    max_retries = 3
    retry_delay = 5
    for attempt in range(max_retries):
        logger.info("尝试第 %s 次...", attempt + 1)
        success, transferred_files, final_target_folder_id, final_target_folder_name = login_and_create_task(
            share_link, access_code, target_folder_id, target_folder_name
        )
        if success:
            logger.info("脚本执行成功！总计转存文件数: %d", transferred_files)
            logger.info("最终目标目录: %s (ID: %s)", final_target_folder_name, final_target_folder_id)
            break
        else:
            if attempt < max_retries - 1:
                logger.info("等待 %s 秒后重试...", retry_delay)
                time.sleep(retry_delay)
            else:
                logger.error("达到最大重试次数，脚本执行失败！总计转存文件数: %d", transferred_files)
                exit(1)

if __name__ == "__main__":
    main()