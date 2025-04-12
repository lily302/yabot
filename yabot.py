# yabot.py
# Version: 1.0.4
# Changelog:
# - Added persistent logging to /app/logs/yabot.log
# - Optimized history storage for compatibility with create_task.py
# - Improved logging readability
import sqlite3
import telegram
import requests
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    MessageHandler,
    filters,
    CommandHandler,
    CallbackQueryHandler,
    ConversationHandler,
    ContextTypes,
)
import subprocess
import logging
import os
import time
import re
from typing import List, Dict, Tuple
from collections import Counter
from delete_task import login_and_get_tasks, delete_task_by_id

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

# 从环境变量读取配置
TOKEN = os.getenv("TOKEN")
TARGET_CHAT_ID = os.getenv("TARGET_CHAT_ID")
TARGET_SENDER = os.getenv("TARGET_SENDER")
DB_PATH = os.getenv("DB_PATH", "/app/data/messages.db")
SCRIPT_PARAM = os.getenv("SCRIPT_PARAM", "")
SERVER_URL = os.getenv("SERVER_URL", "http://your-server:3000").rstrip('/')
USERNAME = os.getenv("USERNAME", "your_username")
PASSWORD = os.getenv("PASSWORD", "your_password")
DEFAULT_FOLDER_ID = os.getenv("TARGET_FOLDER_ID", "-11")

# 全局变量存储用户选择的默认目录
USER_DEFAULT_FOLDER_ID = DEFAULT_FOLDER_ID
USER_DEFAULT_FOLDER_PATH = ""

# 触发关键词
TRIGGER_MESSAGE_STRM = "入库"
TRIGGER_MESSAGE_TRANSFER = "转存"
TRIGGER_MESSAGE_EXECUTE = "全部执行"
TRIGGER_MESSAGE_DELETE = "删除任务"
TRIGGER_MESSAGE_COMMON_FOLDERS = "常用目录"

# 对话状态
SELECT_TASKS = 0
VIEW_FOLDERS = 1

# 每页显示的数量
TASKS_PER_PAGE = 5
FOLDERS_PER_PAGE = 5

# 数据库操作函数
def init_db():
    """初始化 SQLite 数据库"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS messages 
                 (id INTEGER PRIMARY KEY, 
                  sender TEXT, 
                  content TEXT, 
                  timestamp TEXT,
                  target_folder_id TEXT,
                  target_folder_name TEXT
                 )''')
    c.execute('''CREATE TABLE IF NOT EXISTS settings 
                 (key TEXT PRIMARY KEY, value TEXT)''')
    c.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", 
              ("default_folder_id", DEFAULT_FOLDER_ID))
    c.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", 
              ("default_folder_path", ""))
    conn.commit()
    conn.close()

def load_default_folder():
    """从数据库加载默认目录"""
    global USER_DEFAULT_FOLDER_ID, USER_DEFAULT_FOLDER_PATH
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT value FROM settings WHERE key = ?", ("default_folder_id",))
    result = c.fetchone()
    if result:
        USER_DEFAULT_FOLDER_ID = result[0]
    c.execute("SELECT value FROM settings WHERE key = ?", ("default_folder_path",))
    result = c.fetchone()
    if result:
        USER_DEFAULT_FOLDER_PATH = result[0]
    conn.close()
    logger.info("从数据库加载默认目录: %s (ID: %s)", USER_DEFAULT_FOLDER_PATH or "未设置", USER_DEFAULT_FOLDER_ID)

def save_default_folder(folder_id: str, folder_path: str):
    """保存默认目录到数据库"""
    global USER_DEFAULT_FOLDER_ID, USER_DEFAULT_FOLDER_PATH
    USER_DEFAULT_FOLDER_ID = folder_id
    USER_DEFAULT_FOLDER_PATH = folder_path
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", 
              ("default_folder_id", folder_id))
    c.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", 
              ("default_folder_path", folder_path))
    conn.commit()
    conn.close()
    logger.info("保存默认目录到数据库: %s (ID: %s)", folder_path, folder_id)

def save_to_db(sender: str, content: str, target_folder_id: str = None, target_folder_name: str = None):
    """将消息保存到数据库，并记录目标目录"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        "INSERT INTO messages (sender, content, timestamp, target_folder_id, target_folder_name) "
        "VALUES (?, ?, datetime('now'), ?, ?)",
        (sender, content, target_folder_id, target_folder_name)
    )
    conn.commit()
    conn.close()
    logger.info("消息已保存到数据库: %s (发送者: %s, 目标目录: %s)", content, sender, target_folder_name or "未指定")

def extract_share_link(message_text: str) -> str:
    """从消息中提取天翼云盘分享链接"""
    pattern = r"https://cloud\.189\.cn/t/[A-Za-z0-9]+"
    match = re.search(pattern, message_text)
    return match.group(0) if match else None

async def send_limited_message(chat_id: int, text: str, context: telegram.ext.ContextTypes.DEFAULT_TYPE, reply_markup=None):
    """发送消息，限制长度并支持按钮"""
    max_length = 4096
    if len(text) > max_length:
        text = text[:max_length - 3] + "..."
    try:
        message = await context.bot.send_message(
            chat_id=chat_id,
            text=text,
            reply_markup=reply_markup,
            parse_mode=None
        )
        logger.info("消息发送成功，message_id: %s", message.message_id)
        return message
    except telegram.error.TelegramError as e:
        logger.error("发送消息失败: %s", str(e))
        await context.bot.send_message(chat_id=chat_id, text=f"❌ 发送消息失败！\n错误：{str(e)}")
        return None

async def run_script(script_path: str, script_args: list, chat_id: int, context: telegram.ext.ContextTypes.DEFAULT_TYPE, action_name: str) -> tuple[bool, int, str, str, str]:
    """运行脚本并返回执行结果、数量统计、输出、目标目录 ID 和目标目录名称"""
    start_time = time.time()
    
    if not os.path.exists(script_path):
        logger.error("脚本未找到: %s", script_path)
        await send_limited_message(chat_id, f"❌ 错误：找不到{action_name}脚本！路径: {script_path}", context)
        return False, 0, "", "", ""

    try:
        process = subprocess.Popen(script_args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1, universal_newlines=True)
        output = ""
        while True:
            line = process.stdout.readline()
            if not line and process.poll() is not None:
                break
            output += line
            logger.info(line.strip())
        
        return_code = process.wait()
        duration = time.time() - start_time
        
        count = 0
        target_folder_id = ""
        target_folder_name = ""
        if "create_task.py" in script_path:
            match = re.search(r"所有任务总计转存文件数: (\d+)", output)
            if match:
                count = int(match.group(1))
            folder_match = re.search(r"最终目标目录: (.+) \(ID: (.+)\)", output)
            if folder_match:
                target_folder_name = folder_match.group(1)
                target_folder_id = folder_match.group(2)
                logger.info("从输出中提取目标目录: %s (ID: %s)", target_folder_name, target_folder_id)
            else:
                logger.warning("未从输出中提取到目标目录信息")
        elif "init4.sh" in script_path:
            video_extensions = [".mp4", ".mkv", ".avi", ".flv", ".mov", ".wmv"]
            count = sum(
                1 for line in output.splitlines()
                if "正在处理" in line and any(line.strip().endswith(ext) for ext in video_extensions)
            )
            logger.info("通过输出统计的 STRM 文件数量: %d", count)
            if count == 0:
                logger.warning("未统计到任何 STRM 文件生成，可能是输出格式不匹配或无新文件需要处理")

        if return_code != 0:
            logger.error("脚本 %s 执行失败，返回值: %s", script_path, return_code)
            feedback = (
                f"❌ {action_name}失败！\n"
                f"⏱️ 用时：{duration:.2f} 秒\n"
                f"错误：脚本返回非零退出码 {return_code}\n"
                f"输出：\n{output[:500]}{'...' if len(output) > 500 else ''}"
            )
            await send_limited_message(chat_id, feedback, context)
            return False, count, output, target_folder_id, target_folder_name

        logger.info("脚本 %s 执行成功，耗时 %s 秒，数量: %d", script_path, duration, count)
        if "create_task.py" in script_path:
            feedback = f"✅ {action_name}完成！\n⏱️ 用时：{duration:.2f} 秒\n📦 转存文件数：{count}"
            if target_folder_name:
                feedback += f"\n📁 目标目录：{target_folder_name} (ID: {target_folder_id})"
        elif "init4.sh" in script_path:
            feedback = f"✅ {action_name}完成！\n⏱️ 用时：{duration:.2f} 秒\n📜 生成 STRM 文件数：{count}"
        else:
            feedback = f"✅ {action_name}完成！\n⏱️ 用时：{duration:.2f} 秒"
        await send_limited_message(chat_id, feedback, context)
        return True, count, output, target_folder_id, target_folder_name

    except Exception as e:
        duration = time.time() - start_time
        logger.error("脚本 %s 执行时发生异常: %s", script_path, str(e))
        feedback = (
            f"❌ {action_name}失败！\n"
            f"⏱️ 用时：{duration:.2f} 秒\n"
            f"错误：{str(e)}"
        )
        await send_limited_message(chat_id, feedback, context)
        return False, 0, "", "", ""

def get_common_folders(session: requests.Session) -> List[Tuple[str, str]]:
    """从历史转存记录中提取前 10 个最常用目录"""
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT target_folder_id, target_folder_name FROM messages WHERE target_folder_id IS NOT NULL AND target_folder_name IS NOT NULL")
        folder_records = c.fetchall()
        conn.close()
    except sqlite3.Error as e:
        logger.error("读取历史记录失败: %s", e)
        return []

    if not folder_records:
        logger.info("没有历史转存记录，返回空列表")
        return []

    folder_counts = Counter((folder_id, folder_name) for folder_id, folder_name in folder_records)
    common_folders = [(name, folder_id) for (folder_id, name), count in folder_counts.most_common(10)]
    logger.info("常用目录（基于历史记录）: %s", common_folders)
    return common_folders

async def handle_message(update: telegram.Update, context: telegram.ext.ContextTypes.DEFAULT_TYPE):
    """处理非命令文本消息"""
    sender_username = update.message.from_user.username or "未知用户"
    message_text = update.message.text or "[非文本消息]"
    chat_id = update.message.chat_id
    
    logger.info("收到消息: %s (来自: @%s, Chat ID: %s)", message_text, sender_username, chat_id)
    
    if chat_id != int(TARGET_CHAT_ID) or sender_username != TARGET_SENDER:
        logger.info("消息不符合条件: Chat ID %s 或发送者 @%s 不匹配", chat_id, sender_username)
        return

    if message_text == TRIGGER_MESSAGE_STRM:
        logger.info("触发 STRM 生成: %s (来自: @%s)", message_text, sender_username)
        success, count, output, _, _ = await run_script(
            "/app/init4.sh",
            ["/bin/bash", "/app/init4.sh", SCRIPT_PARAM],
            chat_id,
            context,
            "入库"
        )
        save_to_db(sender_username, message_text)

    elif message_text.startswith(TRIGGER_MESSAGE_TRANSFER):
        logger.info("检测到转存关键词: %s (来自: @%s)", message_text, sender_username)
        parts = message_text.split()
        share_link = extract_share_link(message_text)
        if not share_link:
            logger.error("未找到有效的天翼云盘分享链接")
            await send_limited_message(chat_id, "❌ 错误：请提供有效的天翼云盘分享链接！", context)
            return
        
        target_folder_name = parts[2] if len(parts) > 2 else ""
        target_folder_id = None
        if target_folder_name:
            logger.info("指定目标文件夹名称: %s", target_folder_name)
            script_args = ["python", "/app/create_task.py", "--share-link", share_link, "--target-folder-name", target_folder_name]
        else:
            common_folders = get_common_folders(session=requests.Session())
            if not common_folders:
                logger.info("没有历史常用目录，使用默认目录 ID: %s", USER_DEFAULT_FOLDER_ID)
                target_folder_id = USER_DEFAULT_FOLDER_ID
                script_args = ["python", "/app/create_task.py", "--share-link", share_link, "--target-folder-id", target_folder_id]
            else:
                _, target_folder_id = common_folders[0]
                logger.info("未指定文件夹，使用历史常用目录 ID: %s", target_folder_id)
                script_args = ["python", "/app/create_task.py", "--share-link", share_link, "--target-folder-id", target_folder_id]

        success, count, output, final_target_folder_id, final_target_folder_name = await run_script(
            "/app/create_task.py",
            script_args,
            chat_id,
            context,
            "转存"
        )
        if success and final_target_folder_id and final_target_folder_name:
            save_to_db(sender_username, message_text, final_target_folder_id, final_target_folder_name)
        else:
            logger.warning("转存任务未成功或未获取目标目录信息，不记录到历史")

    elif message_text == TRIGGER_MESSAGE_EXECUTE:
        logger.info("触发任务执行: %s (来自: @%s)", message_text, sender_username)
        success, count, output, _, _ = await run_script(
            "/app/execute_tasks.py",
            ["python", "/app/execute_tasks.py"],
            chat_id,
            context,
            "任务执行"
        )
        save_to_db(sender_username, message_text)

    elif message_text == TRIGGER_MESSAGE_DELETE:
        logger.info("触发删除任务: %s (来自: @%s)", message_text, sender_username)
        await delete_command(update, context)

    elif message_text == TRIGGER_MESSAGE_COMMON_FOLDERS:
        logger.info("触发常用目录查看: %s (来自: @%s)", message_text, sender_username)
        await common_folders_command(update, context)

async def save_command(update: telegram.Update, context: telegram.ext.ContextTypes.DEFAULT_TYPE):
    """处理 /save 命令"""
    chat_id = update.message.chat_id
    sender_username = update.message.from_user.username or "未知用户"
    args = context.args
    
    if chat_id != int(TARGET_CHAT_ID) or sender_username != TARGET_SENDER:
        logger.info("命令 /save 不符合条件: Chat ID %s 或发送者 @%s 不匹配", chat_id, sender_username)
        return
    
    logger.info("收到命令: /save %s (来自: @%s)", ' '.join(args), sender_username)
    if not args:
        await send_limited_message(chat_id, "❌ 错误：请提供分享链接，例如 /save <链接> [目录]", context)
        return
    
    share_link = extract_share_link(" ".join(args))
    if not share_link:
        await send_limited_message(chat_id, "❌ 错误：请提供有效的天翼云盘分享链接！", context)
        return
    
    target_folder_name = args[1] if len(args) > 1 else ""
    target_folder_id = None
    if target_folder_name:
        logger.info("命令指定目标文件夹名称: %s", target_folder_name)
        script_args = ["python", "/app/create_task.py", "--share-link", share_link, "--target-folder-name", target_folder_name]
    else:
        common_folders = get_common_folders(session=requests.Session())
        if not common_folders:
            logger.info("命令未指定文件夹，且没有历史常用目录，使用默认目录 ID: %s", USER_DEFAULT_FOLDER_ID)
            target_folder_id = USER_DEFAULT_FOLDER_ID
            script_args = ["python", "/app/create_task.py", "--share-link", share_link, "--target-folder-id", target_folder_id]
        else:
            _, target_folder_id = common_folders[0]
            logger.info("命令未指定文件夹，使用历史常用目录 ID: %s", target_folder_id)
            script_args = ["python", "/app/create_task.py", "--share-link", share_link, "--target-folder-id", target_folder_id]
    
    success, count, output, final_target_folder_id, final_target_folder_name = await run_script(
        "/app/create_task.py",
        script_args,
        chat_id,
        context,
        "转存"
    )
    if success and final_target_folder_id and final_target_folder_name:
        save_to_db(sender_username, " ".join(args), final_target_folder_id, final_target_folder_name)
    else:
        logger.warning("转存任务未成功或未获取目标目录信息，不记录到历史")

async def strm_command(update: telegram.Update, context: telegram.ext.ContextTypes.DEFAULT_TYPE):
    """处理 /strm 命令"""
    chat_id = update.message.chat_id
    sender_username = update.message.from_user.username or "未知用户"
    
    if chat_id != int(TARGET_CHAT_ID) or sender_username != TARGET_SENDER:
        logger.info("命令 /strm 不符合条件: Chat ID %s 或发送者 @%s 不匹配", chat_id, sender_username)
        return
    
    logger.info("收到命令: /strm (来自: @%s)", sender_username)
    success, count, output, _, _ = await run_script(
        "/app/init4.sh",
        ["/bin/bash", "/app/init4.sh", SCRIPT_PARAM],
        chat_id,
        context,
        "入库"
    )
    save_to_db(sender_username, "/strm")

async def execute_command(update: telegram.Update, context: telegram.ext.ContextTypes.DEFAULT_TYPE):
    """处理 /execute 命令"""
    chat_id = update.message.chat_id
    sender_username = update.message.from_user.username or "未知用户"
    
    if chat_id != int(TARGET_CHAT_ID) or sender_username != TARGET_SENDER:
        logger.info("命令 /execute 不符合条件: Chat ID %s 或发送者 @%s 不匹配", chat_id, sender_username)
        return
    
    logger.info("收到命令: /execute (来自: @%s)", sender_username)
    success, count, output, _, _ = await run_script(
        "/app/execute_tasks.py",
        ["python", "/app/execute_tasks.py"],
        chat_id,
        context,
        "任务执行"
    )
    save_to_db(sender_username, "/execute")

def build_task_list_message(tasks: List[Dict], page: int, tasks_per_page: int, selected_tasks: set) -> tuple[str, InlineKeyboardMarkup]:
    """构建任务列表消息和按钮"""
    total_tasks = len(tasks)
    start_idx = page * tasks_per_page
    end_idx = min(start_idx + tasks_per_page, total_tasks)
    task_list_message = "🎉 当前任务列表：\n\n"
    
    for idx, task in enumerate(tasks[start_idx:end_idx], start_idx + 1):
        resource_name = task.get("resourceName", "")
        share_folder_name = task.get("shareFolderName", "")
        full_name = f"{resource_name}/{share_folder_name}" if share_folder_name else resource_name
        display_name = full_name[:30] + "..." if len(full_name) > 30 else full_name
        task_list_message += f"{idx}. {display_name}\n"
    
    task_list_message += f"\n页码: {page + 1}/{max(1, (total_tasks + tasks_per_page - 1) // tasks_per_page)}"
    task_list_message += "\n点击下方按钮选择任务（支持多选），完成后点击“确认删除”。" 

    buttons = []
    for idx, task in enumerate(tasks[start_idx:end_idx], start_idx):
        task_id = str(task.get("id"))
        is_selected = task_id in selected_tasks
        button_text = f"✅ {start_idx + 1 + (idx - start_idx)}" if is_selected else f"{start_idx + 1 + (idx - start_idx)}"
        buttons.append(
            InlineKeyboardButton(
                text=button_text,
                callback_data=f"select_{task_id}"
            )
        )

    keyboard = [buttons[i:i + 5] for i in range(0, len(buttons), 5)]

    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton("⬅️ 上一页", callback_data=f"page_{page - 1}"))
    if end_idx < total_tasks:
        nav_buttons.append(InlineKeyboardButton("下一页 ➡️", callback_data=f"page_{page + 1}"))
    if nav_buttons:
        keyboard.append(nav_buttons)

    action_buttons = [
        InlineKeyboardButton("✅ 确认删除", callback_data="confirm_delete"),
        InlineKeyboardButton("🗑️ 全部删除", callback_data="delete_all"),
        InlineKeyboardButton("❌ 取消", callback_data="cancel"),
    ]
    keyboard.append(action_buttons)

    return task_list_message, InlineKeyboardMarkup(keyboard)

async def delete_command(update: telegram.Update, context: telegram.ext.ContextTypes.DEFAULT_TYPE) -> int:
    """处理 /delete 命令，进入交互式删除流程"""
    chat_id = update.message.chat_id
    sender_username = update.message.from_user.username or "未知用户"

    if chat_id != int(TARGET_CHAT_ID) or sender_username != TARGET_SENDER:
        logger.info("命令 /delete 不符合条件: Chat ID %s 或发送者 @%s 不匹配", chat_id, sender_username)
        return ConversationHandler.END

    args = context.args if context.args is not None else []
    logger.info("收到命令: /delete %s (来自: @%s)", ' '.join(args), sender_username)
    
    task_name = ""
    delete_cloud = True
    i = 0
    while i < len(args):
        if args[i] == "--task-name" and i + 1 < len(args):
            task_name = args[i + 1]
            i += 2
        elif args[i] == "--no-delete-cloud":
            delete_cloud = False
            i += 1
        else:
            i += 1

    session, tasks, success = login_and_get_tasks(task_name)
    if not success:
        await send_limited_message(chat_id, "❌ 获取任务列表失败，请稍后重试", context)
        return ConversationHandler.END
    if not tasks:
        await send_limited_message(chat_id, "🎉 当前任务列表为空，无任务可删除", context)
        return ConversationHandler.END

    page = 0
    selected_tasks = set()
    context.user_data["tasks"] = tasks
    context.user_data["session"] = session
    context.user_data["delete_cloud"] = delete_cloud
    context.user_data["page"] = page
    context.user_data["selected_tasks"] = selected_tasks
    context.user_data["task_name_filter"] = task_name

    task_list_message, reply_markup = build_task_list_message(tasks, page, TASKS_PER_PAGE, selected_tasks)
    task_list_message += f"\n当前设置：{'同时删除网盘内容' if delete_cloud else '仅删除任务，不删除网盘内容'}"
    if task_name:
        task_list_message += f"\n筛选条件：任务名称包含 '{task_name}'"

    message = await send_limited_message(chat_id, task_list_message, context, reply_markup)
    if message is None:
        logger.error("无法发送任务列表消息，退出删除流程")
        return ConversationHandler.END
    context.user_data["message_id"] = message.message_id

    logger.info("进入 SELECT_TASKS 状态，等待用户选择任务")
    return SELECT_TASKS

def build_folder_list_message(folders: List[Tuple[str, str]], page: int, folders_per_page: int, current_default: str) -> tuple[str, InlineKeyboardMarkup]:
    """构建文件夹列表消息和按钮"""
    total_folders = len(folders)
    start_idx = page * folders_per_page
    end_idx = min(start_idx + folders_per_page, total_folders)
    folder_list_message = "🎉 常用目录列表（基于历史记录）：\n\n"
    
    for idx, (folder_path, folder_id) in enumerate(folders[start_idx:end_idx], start_idx + 1):
        display_name = folder_path[:30] + "..." if len(folder_path) > 30 else folder_path
        is_default = folder_id == current_default
        folder_list_message += f"{idx}. {display_name} (ID: {folder_id}){' [默认]' if is_default else ''}\n"
    
    folder_list_message += f"\n页码: {page + 1}/{max(1, (total_folders + folders_per_page - 1) // folders_per_page)}"
    folder_list_message += "\n点击下方按钮选择目录并设为默认，完成后点击“关闭”。" 

    buttons = []
    for idx, (_, folder_id) in enumerate(folders[start_idx:end_idx], start_idx):
        button_text = f"{start_idx + 1 + (idx - start_idx)}"
        buttons.append(
            InlineKeyboardButton(
                text=button_text,
                callback_data=f"folder_{folder_id}"
            )
        )

    keyboard = [buttons[i:i + 5] for i in range(0, len(buttons), 5)]

    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton("⬅️ 上一页", callback_data=f"folder_page_{page - 1}"))
    if end_idx < total_folders:
        nav_buttons.append(InlineKeyboardButton("下一页 ➡️", callback_data=f"folder_page_{page + 1}"))
    if nav_buttons:
        keyboard.append(nav_buttons)

    action_buttons = [
        InlineKeyboardButton("❌ 关闭", callback_data="cancel"),
    ]
    keyboard.append(action_buttons)

    return folder_list_message, InlineKeyboardMarkup(keyboard)

async def common_folders_command(update: telegram.Update, context: telegram.ext.ContextTypes.DEFAULT_TYPE) -> int:
    """处理 /commonfolders 命令，显示常用目录并允许选择默认"""
    chat_id = update.message.chat_id
    sender_username = update.message.from_user.username or "未知用户"

    if chat_id != int(TARGET_CHAT_ID) or sender_username != TARGET_SENDER:
        logger.info("命令 /commonfolders 不符合条件: Chat ID %s 或发送者 @%s 不匹配", chat_id, sender_username)
        return ConversationHandler.END

    logger.info("收到命令: /commonfolders (来自: @%s)", sender_username)

    session = requests.Session()
    common_folders = get_common_folders(session)
    if not common_folders:
        await send_limited_message(chat_id, "❌ 没有历史转存记录，无法获取常用目录", context)
        return ConversationHandler.END

    page = 0
    context.user_data["common_folders"] = common_folders
    context.user_data["folder_page"] = page

    folder_list_message, reply_markup = build_folder_list_message(common_folders, page, FOLDERS_PER_PAGE, USER_DEFAULT_FOLDER_ID)
    message = await send_limited_message(chat_id, folder_list_message, context, reply_markup)
    if message is None:
        logger.error("无法发送文件夹列表消息，退出流程")
        return ConversationHandler.END
    context.user_data["message_id"] = message.message_id

    logger.info("进入 VIEW_FOLDERS 状态，显示常用目录")
    return VIEW_FOLDERS

async def button_handler(update: telegram.Update, context: telegram.ext.ContextTypes.DEFAULT_TYPE) -> int:
    """处理按钮点击事件"""
    query = update.callback_query
    await query.answer()
    logger.info("收到按钮点击: %s", query.data)

    chat_id = query.message.chat_id
    message_id = query.message.message_id

    if "tasks" in context.user_data:
        tasks = context.user_data.get("tasks", [])
        session = context.user_data.get("session")
        delete_cloud = context.user_data.get("delete_cloud", True)
        page = context.user_data.get("page", 0)
        selected_tasks = context.user_data.get("selected_tasks", set())
        task_name_filter = context.user_data.get("task_name_filter", "")

        data = query.data

        if data.startswith("select_"):
            task_id = data.split("_")[1]
            if task_id in selected_tasks:
                selected_tasks.remove(task_id)
                logger.info("取消选择任务: %s", task_id)
            else:
                selected_tasks.add(task_id)
                logger.info("选择任务: %s", task_id)
            context.user_data["selected_tasks"] = selected_tasks

        elif data.startswith("page_"):
            page = int(data.split("_")[1])
            context.user_data["page"] = page
            logger.info("切换到页码: %d", page)

        elif data == "confirm_delete":
            if not selected_tasks:
                await query.edit_message_text("❌ 请至少选择一个任务进行删除")
                logger.info("用户未选择任务，提示选择")
                return SELECT_TASKS
            return await perform_delete(update, context, list(selected_tasks))

        elif data == "delete_all":
            selected_tasks = {str(task.get("id")) for task in tasks}
            logger.info("用户选择全部删除，任务数量: %d", len(selected_tasks))
            return await perform_delete(update, context, list(selected_tasks))

        elif data == "cancel":
            await query.edit_message_text("❌ 删除操作已取消")
            logger.info("用户取消删除操作")
            context.user_data.clear()
            return ConversationHandler.END

        task_list_message, reply_markup = build_task_list_message(tasks, page, TASKS_PER_PAGE, selected_tasks)
        task_list_message += f"\n当前设置：{'同时删除网盘内容' if delete_cloud else '仅删除任务，不删除网盘内容'}"
        if task_name_filter:
            task_list_message += f"\n筛选条件：任务名称包含 '{task_name_filter}'"
        await query.edit_message_text(text=task_list_message, reply_markup=reply_markup)
        return SELECT_TASKS

    elif "common_folders" in context.user_data:
        common_folders = context.user_data.get("common_folders", [])
        page = context.user_data.get("folder_page", 0)

        data = query.data

        if data.startswith("folder_"):
            folder_id = data.split("_")[1]
            folder_path = next((path for path, fid in common_folders if fid == folder_id), "")
            save_default_folder(folder_id, folder_path)
            await query.answer(f"已将默认目录设置为：{folder_path}")

        elif data.startswith("folder_page_"):
            page = int(data.split("_")[2])
            context.user_data["folder_page"] = page
            logger.info("切换到文件夹页码: %d", page)

        elif data == "cancel":
            await query.edit_message_text("❌ 已关闭")
            logger.info("用户关闭常用目录查看")
            context.user_data.clear()
            return ConversationHandler.END

        folder_list_message, reply_markup = build_folder_list_message(common_folders, page, FOLDERS_PER_PAGE, USER_DEFAULT_FOLDER_ID)
        await query.edit_message_text(text=folder_list_message, reply_markup=reply_markup)
        return VIEW_FOLDERS

async def perform_delete(update: telegram.Update, context: telegram.ext.ContextTypes.DEFAULT_TYPE, task_ids: List[str]) -> int:
    """执行删除操作"""
    query = update.callback_query
    chat_id = query.message.chat_id

    tasks = context.user_data.get("tasks", [])
    session = context.user_data.get("session")
    delete_cloud = context.user_data.get("delete_cloud", True)

    start_time = time.time()
    deleted_count = 0
    failed_tasks = []
    
    for task_id in task_ids:
        task = next((t for t in tasks if str(t.get("id")) == task_id), None)
        if not task:
            continue
        success, error_msg = delete_task_by_id(session, task_id, delete_cloud)
        if success:
            deleted_count += 1
        else:
            resource_name = task.get("resourceName", "")
            share_folder_name = task.get("shareFolderName", "")
            full_name = f"{resource_name}/{share_folder_name}" if share_folder_name else resource_name
            failed_tasks.append(f"任务ID: {task_id}, 名称: {full_name}, 错误: {error_msg}")

    duration = time.time() - start_time

    feedback = f"{'✅' if deleted_count > 0 else '❌'} 删除任务完成！\n"
    feedback += f"成功删除任务数：{deleted_count}/{len(task_ids)}\n"
    feedback += f"⏱️ 用时：{duration:.2f} 秒\n"
    if failed_tasks:
        feedback += "⚠️ 以下任务删除失败：\n" + "\n".join(failed_tasks)

    await query.edit_message_text(feedback)
    context.user_data.clear()
    return ConversationHandler.END

async def timeout(update: telegram.Update, context: telegram.ext.ContextTypes.DEFAULT_TYPE) -> int:
    """处理超时"""
    chat_id = update.effective_chat.id
    await send_limited_message(chat_id, "⏰ 操作超时，流程已取消", context)
    context.user_data.clear()
    return ConversationHandler.END

def main():
    """主函数，启动 Telegram 机器人"""
    init_db()
    load_default_folder()
    application = Application.builder().token(TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler("delete", delete_command),
            MessageHandler(filters.Regex(f"^{TRIGGER_MESSAGE_DELETE}$"), delete_command),
            CommandHandler("commonfolders", common_folders_command),
            MessageHandler(filters.Regex(f"^{TRIGGER_MESSAGE_COMMON_FOLDERS}$"), common_folders_command),
        ],
        states={
            SELECT_TASKS: [
                CallbackQueryHandler(button_handler),
            ],
            VIEW_FOLDERS: [
                CallbackQueryHandler(button_handler),
            ],
        },
        fallbacks=[
            CommandHandler("cancel", lambda update, context: ConversationHandler.END),
        ],
        conversation_timeout=60,
    )

    application.add_handler(conv_handler)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_handler(CommandHandler("save", save_command))
    application.add_handler(CommandHandler("strm", strm_command))
    application.add_handler(CommandHandler("execute", execute_command))

    logger.info("机器人已启动，监听中...")
    application.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()