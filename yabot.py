import sqlite3
from telegram.ext import Application, MessageHandler, filters
import subprocess
import logging
import os
import time
import re

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

TOKEN = os.getenv("TOKEN")
TARGET_CHAT_ID = os.getenv("TARGET_CHAT_ID")
TARGET_SENDER = os.getenv("TARGET_SENDER")
SCRIPT_PARAM = os.getenv("SCRIPT_PARAM")
DB_PATH = os.getenv("DB_PATH", "/app/messages.db")

TRIGGER_MESSAGE_STRM = "入库"
TRIGGER_MESSAGE_TRANSFER = "转存"
TRIGGER_MESSAGE_EXECUTE = "全部执行"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS messages 
                 (id INTEGER PRIMARY KEY, sender TEXT, content TEXT, timestamp TEXT)''')
    conn.commit()
    conn.close()

def save_to_db(sender, content):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT INTO messages (sender, content, timestamp) VALUES (?, ?, datetime('now'))", 
              (sender, content))
    conn.commit()
    conn.close()

def count_processing_files(script_output):
    lines = script_output.splitlines()
    processing_files = [line for line in lines if line.startswith("正在处理")]
    return len(processing_files)

def count_transfer_files(script_output):
    match = re.search(r"已转存文件数: (\d+)", script_output)
    return int(match.group(1)) if match else 0

def extract_share_link(message_text):
    pattern = r"https://cloud\.189\.cn/t/[A-Za-z0-9]+"
    match = re.search(pattern, message_text)
    return match.group(0) if match else None

async def send_limited_message(chat_id, text, context):
    max_length = 4096
    if len(text) > max_length:
        text = text[:max_length - 3] + '...'
    try:
        await context.bot.send_message(chat_id=chat_id, text=text)
    except Exception as e:
        logger.error(f"发送消息失败: {str(e)}")
        await context.bot.send_message(chat_id=chat_id, text=f"❌ 发送消息失败！\n错误：{str(e)}")

async def run_script(script_path, script_args, chat_id, context, action_name, count_func=None):
    start_time = time.time()
    
    if not os.path.exists(script_path):
        logger.error(f"脚本未找到: {script_path}")
        await send_limited_message(chat_id, f"❌ 错误：找不到{action_name}脚本！路径: {script_path}", context)
        return False, 0

    try:
        cmd = script_args
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1, universal_newlines=True)
        output = ""
        while True:
            line = process.stdout.readline()
            if not line and process.poll() is not None:
                break
            output += line
            logger.info(line.strip())
        
        return_code = process.wait()
        duration = time.time() - start_time
        
        if return_code != 0:
            logger.error(f"脚本 {script_path} 执行失败，返回值: {return_code}")
            feedback = (
                f"❌ {action_name}失败！\n"
                f"⏱️ 用时：{duration:.2f} 秒\n"
                f"错误：脚本返回非零退出码 {return_code}"
            )
            await send_limited_message(chat_id, feedback, context)
            return False, 0

        count = count_func(output) if count_func else 0
        logger.info(f"脚本 {script_path} 执行成功，耗时 {duration:.2f} 秒")
        feedback = (
            f"✅ {action_name}完成！\n"
            f"⏱️ 用时：{duration:.2f} 秒\n"
            f"📦 结果：{count} 个" if count_func else f"✅ {action_name}完成！\n⏱️ 用时：{duration:.2f} 秒"
        )
        await send_limited_message(chat_id, feedback, context)
        return True, count

    except Exception as e:
        duration = time.time() - start_time
        logger.error(f"脚本 {script_path} 执行时发生异常: {str(e)}")
        feedback = (
            f"❌ {action_name}失败！\n"
            f"⏱️ 用时：{duration:.2f} 秒\n"
            f"错误：{str(e)}"
        )
        await send_limited_message(chat_id, feedback, context)
        return False, 0

async def handle_message(update, context):
    sender_username = update.message.from_user.username if update.message.from_user.username else "未知用户"
    message_text = update.message.text if update.message.text else "[非文本消息]"
    chat_id = update.message.chat_id
    
    logger.info(f"收到消息: {message_text} (来自: @{sender_username}, Chat ID: {chat_id})")
    
    if chat_id != int(TARGET_CHAT_ID) or sender_username != TARGET_SENDER:
        logger.info(f"消息不符合条件: Chat ID {chat_id} 或发送者 @{sender_username} 不匹配")
        return

    save_to_db(sender_username, message_text)

    if message_text == TRIGGER_MESSAGE_STRM:
        logger.info(f"触发条件满足: {message_text} (来自: @{sender_username})")
        await run_script(
            "/app/init4.sh",
            ["bash", "/app/init4.sh", SCRIPT_PARAM],
            chat_id,
            context,
            "入库",
            count_processing_files
        )

    elif message_text.startswith(TRIGGER_MESSAGE_TRANSFER):
        logger.info(f"检测到转存关键词: {message_text} (来自: @{sender_username})")
        share_link = extract_share_link(message_text)
        if not share_link:
            logger.error("未找到有效的天翼云盘分享链接")
            await send_limited_message(chat_id, "❌ 错误：请提供有效的天翼云盘分享链接！", context)
            return
        access_code = ""
        await run_script(
            "/app/create_task.py",
            ["python", "/app/create_task.py", "--share-link", share_link] + (["--access-code", access_code] if access_code else []),
            chat_id,
            context,
            "转存",
            count_transfer_files
        )

    elif message_text == TRIGGER_MESSAGE_EXECUTE:
        logger.info(f"触发条件满足: {message_text} (来自: @{sender_username})")
        await run_script(
            "/app/execute_tasks.py",
            ["python", "/app/execute_tasks.py"],
            chat_id,
            context,
            "任务执行"
        )

def main():
    init_db()
    application = Application.builder().token(TOKEN).build()
    application.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, handle_message))
    logger.info("机器人已启动，监听中...")
    application.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()