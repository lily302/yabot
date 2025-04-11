# Yabot 项目

Yabot 是一个用于管理媒体任务的 Telegram 机器人。它可以通过 Docker 快速部署，支持多种功能，例如“入库”、“转存”等。

## 功能

- **入库**：将媒体文件添加到指定位置。
- **转存**：将文件转移到天翼云盘或其他位置。
- **全部执行**：批量处理任务。

## 环境要求

- Docker 和 Docker Compose 已安装。
- 一个 Telegram 机器人 Token（通过 [BotFather](https://t.me/BotFather) 获取）。

## 安装步骤

### 方法 1：从 Docker Hub 拉取镜像（推荐）

1. **拉取镜像**：
docker pull leslie56912/yabot:latest


2. **创建 `.env` 文件**：
- 创建一个 `.env` 文件，填入您的 Telegram 机器人 Token 和其他设置。例如：
echo "TOKEN=your-telegram-bot-token" > .env
echo "TARGET_CHAT_ID=your-chat-id" >> .env
echo "TARGET_SENDER=your-sender-id" >> .env
echo "SCRIPT_PARAM=/path/to/your/storage" >> .env
echo "DB_PATH=/app/messages.db" >> .env
echo "SERVER_URL=http://your-server:3000" >> .env
echo "USERNAME=your-username" >> .env
echo "PASSWORD=your-password" >> .env
echo "TARGET_FOLDER_ID=your-folder-id" >> .env
- **注意**：请勿将 `.env` 文件上传到 GitHub，它包含敏感信息。

3. **运行容器**：
docker run -d --name yabot --env-file .env -v $(pwd)/data:/app/data leslie56912/yabot:latest

- 这将启动 Yabot 容器，容器名为 `yabot`。
- `-v $(pwd)/data:/app/data` 将本地 `data` 目录挂载到容器内的 `/app/data`，用于持久化数据（根据您的项目需求调整）。

4. **验证运行**：
- 检查容器是否正常运行：
docker ps
- 查看日志：
docker logs yabot

### 方法 2：从源码构建

1. **克隆仓库**：
git clone https://github.com/leslie56912/yabot.git
cd yabot


2. **配置环境变量**：
- 复制 `.env.example` 文件为 `.env`：

cp .env.example .env

- 编辑 `.env` 文件，填入您的 Telegram 机器人 Token 和其他设置。例如：
TOKEN=your-telegram-bot-token
TARGET_CHAT_ID=your-chat-id
TARGET_SENDER=your-sender-id
SCRIPT_PARAM=/path/to/your/storage
DB_PATH=/app/messages.db
SERVER_URL=http://your-server:3000
USERNAME=your-username
PASSWORD=your-password
TARGET_FOLDER_ID=your-folder-id
- **注意**：请勿将 `.env` 文件上传到 GitHub，它包含敏感信息。

3. **使用 Docker Compose 运行**：

docker-compose up -d

- 这将构建并启动 Yabot 容器，容器名为 `yabot`。

4. **验证运行**：
- 检查容器是否正常运行：

docker ps

- 查看日志：

docker logs yabot


## 使用方法

- **启动机器人**：机器人会自动响应 Telegram 消息。
- **常用命令**：
- `/transfer <链接> [目录]`：转存文件到指定目录（例如 `/transfer https://cloud.189.cn/t/xxx 电影`）。
- `/strm`：执行入库操作。
- `/execute`：执行所有任务。
- **普通触发词**：
- `转存 <链接> [目录]`：转存文件（例如 `转存 https://cloud.189.cn/t/xxx 电影`）。
- `入库`：执行入库操作。
- `全部执行`：执行所有任务。

## 项目结构

- `yabot.py`：主程序文件，Telegram 机器人入口。
- `create_task.py`：创建任务的脚本。
- `execute_tasks.py`：执行任务的脚本。
- `init4.sh`：入库脚本。
- `docker-compose.yml`：Docker Compose 配置文件。
- `Dockerfile`：Docker 镜像构建文件。
- `.env.example`：环境变量模板文件。

## 版本历史

- **v1.0.1**（2025-04-11）：
- 更新了 `create_task.py`，修复了文件夹匹配中的 `NameError` 错误。
- 更新了 `yabot.py`，修复了 `/transfer` 命令未触发的问题。
- 更新了 增加了转存方式，可以添加目录，模糊匹配。
- **v1.0.0**（2025-04-09）：
- 初始版本，支持基本的入库和转存功能。

## 贡献

欢迎提交 Issue 或 Pull Request！如果您有任何建议或改进，请随时联系。

## 许可证

本项目使用 MIT 许可证。详情请查看 [LICENSE](LICENSE) 文件。