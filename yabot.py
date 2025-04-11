import sqlite3
import telegram
from telegram.ext import Application, MessageHandler, filters, CommandHandler
import subprocess
import logging
import os
import time
import re

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# 从环境变量读取配置
TOKEN = os.getenv("TOKEN")
TARGET_CHAT_ID = os.getenv("TARGET_CHAT_ID")
TARGET_SENDER = os.getenv("TARGET_SENDER")
DB_PATH = os.getenv("DB_PATH", "/app/messages.db")
SCRIPT_PARAM = os.getenv("SCRIPT_PARAM", "")

# 触发关键词
TRIGGER_MESSAGE_STRM = "入库"
TRIGGER_MESSAGE_TRANSFER = "转存"
TRIGGER_MESSAGE_EXECUTE = "全部执行"

def init_db():
    """初始化 SQLite 数据库"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS messages 
                 (id INTEGER PRIMARY KEY, sender TEXT, content TEXT, timestamp TEXT)''')
    conn.commit()
    conn.close()

def save_to_db(sender: str, content: str):
    """将消息保存到数据库"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT INTO messages (sender, content, timestamp) VALUES (?, ?, datetime('now'))", 
              (sender, content))
    conn.commit()
    conn.close()

def extract_share_link(message_text: str) -> str:
    """从消息中提取天翼云盘分享链接"""
    pattern = r"https://cloud\.189\.cn/t/[A-Za-z0-9]+"
    match = re.search(pattern, message_text)
    return match.group(0) if match else None

async def send_limited_message(chat_id: int, text: str, context: telegram.ext.ContextTypes.DEFAULT_TYPE):
    """发送消息，限制长度为 Telegram 的最大消息长度"""
    max_length = 4096
    if len(text) > max_length:
        text = text[:max_length - 3] + "..."
    try:
        await context.bot.send_message(chat_id=chat_id, text=text)
    except Exception as e:
        logger.error("发送消息失败: %s", str(e))
        await context.bot.send_message(chat_id=chat_id, text=f"❌ 发送消息失败！\n错误：{str(e)}")

async def run_script(script_path: str, script_args: list, chat_id: int, context: telegram.ext.ContextTypes.DEFAULT_TYPE, action_name: str) -> tuple[bool, int, str]:
    """运行脚本并返回执行结果、数量统计和输出"""
    start_time = time.time()
    
    if not os.path.exists(script_path):
        logger.error("脚本未找到: %s", script_path)
        await send_limited_message(chat_id, f"❌ 错误：找不到{action_name}脚本！路径: {script_path}", context)
        return False, 0, ""

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
        
        # 统计数量（根据脚本类型）
        count = 0
        if "create_task.py" in script_path:
            # 从 create_task.py 输出中提取转存文件总数
            match = re.search(r"所有任务总计转存文件数: (\d+)", output)
            if match:
                count = int(match.group(1))
        elif "init4.sh" in script_path:
            # 只统计“正在处理”行，支持多种视频格式
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
            return False, count, output

        logger.info("脚本 %s 执行成功，耗时 %s 秒，数量: %d", script_path, duration, count)
        if "create_task.py" in script_path:
            feedback = f"✅ {action_name}完成！\n⏱️ 用时：{duration:.2f} 秒\n📦 转存文件数：{count}"
        elif "init4.sh" in script_path:
            feedback = f"✅ {action_name}完成！\n⏱️ 用时：{duration:.2f} 秒\n📜 生成 STRM 文件数：{count}"
        else:
            feedback = f"✅ {action_name}完成！\n⏱️ 用时：{duration:.2f} 秒"
        await send_limited_message(chat_id, feedback, context)
        return True, count, output

    except Exception as e:
        duration = time.time() - start_time
        logger.error("脚本 %s 执行时发生异常: %s", script_path, str(e))
        feedback = (
            f"❌ {action_name}失败！\n"
            f"⏱️ 用时：{duration:.2f} 秒\n"
            f"错误：{str(e)}"
        )
        await send_limited_message(chat_id, feedback, context)
        return False, 0, ""

async def handle_message(update: telegram.Update, context: telegram.ext.ContextTypes.DEFAULT_TYPE):
    """处理非命令文本消息"""
    sender_username = update.message.from_user.username or "未知用户"
    message_text = update.message.text or "[非文本消息]"
    chat_id = update.message.chat_id
    
    logger.info("收到消息: %s (来自: @%s, Chat ID: %s)", message_text, sender_username, chat_id)
    
    if chat_id != int(TARGET_CHAT_ID) or sender_username != TARGET_SENDER:
        logger.info("消息不符合条件: Chat ID %s 或发送者 @%s 不匹配", chat_id, sender_username)
        return

    save_to_db(sender_username, message_text)

    if message_text == TRIGGER_MESSAGE_STRM:
        logger.info("触发 STRM 生成: %s (来自: @%s)", message_text, sender_username)
        await run_script(
            "/app/init4.sh",
            ["/bin/bash", "/app/init4.sh", SCRIPT_PARAM],
            chat_id,
            context,
            "入库"
        )

    elif message_text.startswith(TRIGGER_MESSAGE_TRANSFER):
        logger.info("检测到转存关键词: %s (来自: @%s)", message_text, sender_username)
        parts = message_text.split()
        share_link = extract_share_link(message_text)
        if not share_link:
            logger.error("未找到有效的天翼云盘分享链接")
            await send_limited_message(chat_id, "❌ 错误：请提供有效的天翼云盘分享链接！", context)
            return
        
        target_folder_name = parts[2] if len(parts) > 2 else ""
        if target_folder_name:
            logger.info("指定目标文件夹名称: %s", target_folder_name)
        else:
            logger.info("未指定文件夹，使用默认文件夹")

        script_args = ["python", "/app/create_task.py", "--share-link", share_link]
        if target_folder_name:
            script_args.extend(["--target-folder-name", target_folder_name])

        await run_script(
            "/app/create_task.py",
            script_args,
            chat_id,
            context,
            "转存"
        )

    elif message_text == TRIGGER_MESSAGE_EXECUTE:
        logger.info("触发任务执行: %s (来自: @%s)", message_text, sender_username)
        await run_script(
            "/app/execute_tasks.py",
            ["python", "/app/execute_tasks.py"],
            chat_id,
            context,
            "任务执行"
        )

async def transfer_command(update: telegram.Update, context: telegram.ext.ContextTypes.DEFAULT_TYPE):
    """处理 /transfer 命令"""
    chat_id = update.message.chat_id
    sender_username = update.message.from_user.username or "未知用户"
    args = context.args
    
    if chat_id != int(TARGET_CHAT_ID) or sender_username != TARGET_SENDER:
        logger.info("命令 /transfer 不符合条件: Chat ID %s 或发送者 @%s 不匹配", chat_id, sender_username)
        return
    
    logger.info("收到命令: /transfer %s (来自: @%s)", ' '.join(args), sender_username)
    if not args:
        await send_limited_message(chat_id, "❌ 错误：请提供分享链接，例如 /transfer <链接> [目录]", context)
        return
    
    share_link = extract_share_link(" ".join(args))
    if not share_link:
        await send_limited_message(chat_id, "❌ 错误：请提供有效的天翼云盘分享链接！", context)
        return
    
    target_folder_name = args[1] if len(args) > 1 else ""
    if target_folder_name:
        logger.info("命令指定目标文件夹名称: %s", target_folder_name)
    else:
        logger.info("命令未指定文件夹，使用默认文件夹")
    
    script_args = ["python", "/app/create_task.py", "--share-link", share_link]
    if target_folder_name:
        script_args.extend(["--target-folder-name", target_folder_name])
    
    await run_script(
        "/app/create_task.py",
        script_args,
        chat_id,
        context,
        "转存"
    )

async def strm_command(update: telegram.Update, context: telegram.ext.ContextTypes.DEFAULT_TYPE):
    """处理 /strm 命令"""
    chat_id = update.message.chat_id
    sender_username = update.message.from_user.username or "未知用户"
    
    if chat_id != int(TARGET_CHAT_ID) or sender_username != TARGET_SENDER:
        logger.info("命令 /strm 不符合条件: Chat ID %s 或发送者 @%s 不匹配", chat_id, sender_username)
        return
    
    logger.info("收到命令: /strm (来自: @%s)", sender_username)
    await run_script(
        "/app/init4.sh",
        ["/bin/bash", "/app/init4.sh", SCRIPT_PARAM],
        chat_id,
        context,
        "入库"
    )

async def execute_command(update: telegram.Update, context: telegram.ext.ContextTypes.DEFAULT_TYPE):
    """处理 /execute 命令"""
    chat_id = update.message.chat_id
    sender_username = update.message.from_user.username or "未知用户"
    
    if chat_id != int(TARGET_CHAT_ID) or sender_username != TARGET_SENDER:
        logger.info("命令 /execute 不符合条件: Chat ID %s 或发送者 @%s 不匹配", chat_id, sender_username)
        return
    
    logger.info("收到命令: /execute (来自: @%s)", sender_username)
    await run_script(
        "/app/execute_tasks.py",
        ["python", "/app/execute_tasks.py"],
        chat_id,
        context,
        "任务执行"
    )

def main():
    """主函数，启动 Telegram 机器人"""
    init_db()
    application = Application.builder().token(TOKEN).build()
    
    # 处理非命令的文本消息
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    # 处理命令
    application.add_handler(CommandHandler("transfer", transfer_command))
    application.add_handler(CommandHandler("strm", strm_command))
    application.add_handler(CommandHandler("execute", execute_command))
    
    logger.info("机器人已启动，监听中...")
    application.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()