# Yabot 项目

Yabot 是一个基于 Telegram 的媒体任务管理机器人，支持快速部署和多种功能，如文件入库、转存和批量处理任务。

## 功能

- **入库**：适用于小雅项目，通过命令控制生成 STRM 文件。
- **转存**：配合天翼转存系统，将分享链接转存到天翼云盘。
- **批量执行**：配合天翼转存系统，一次性处理所有任务。
- **删除任务**：配合天翼转存系统，删除任务及网盘对应目录。
- **常用目录**：配合天翼转存系统，从最近保存的10次目录选择默认保存目录。
  
## 环境要求

- 已安装 Docker 和 Docker Compose。
- Telegram 机器人 Token（通过 [BotFather](https://t.me/BotFather) 获取）。

## 安装方法

### 方法 1：使用 Docker Hub 镜像（推荐）

1. **拉取镜像**：
   ```bash
   docker pull leslie56912/yabot:latest

2. **配置环境变量**：
   - 创建 `.env` 文件并填入以下内容（参考 `.env.example`）：
     ```env
     TOKEN=your-telegram-bot-token
     TARGET_CHAT_ID=your-chat-id
     TARGET_SENDER=your-sender-id
     SCRIPT_PARAM=/path/to/your/storage
     SCRIPT_PATH_CREATE_TASK=/app/create_task.py
     SCRIPT_PATH_EXECUTE_TASKS=/app/execute_tasks.py
     DB_PATH=/app/data/messages.db
     SERVER_URL=http://your-server:3000
     USERNAME=your-username
     PASSWORD=your-password
     TARGET_FOLDER_ID=your-folder-id
     TZ=Asia/Shanghai
     ```
   - **注意**：`.env` 文件包含敏感信息，请勿上传至 GitHub 或公开。

3. **运行容器**：
   ```bash
   docker run -d \
   --name yabot \
   --network host \
   --restart unless-stopped \
   --env-file .env \
   -v $(pwd)/data:/app/data \
   -v $(pwd)/logs:/app/logs \
   -v <your-media-path>:/media \
   -v <your-media-path>/strm.txt:/strm.txt \
   leslie56912/yabot:latest
   ```
   - 命令说明：
     - `--name yabot`：容器名称。
     - `-v $(pwd)/data:/app/data`：将本地 `data` 目录挂载到容器，用于数据持久化。
     - `-v <your-media-path>:/media`：挂载 STRM 文件目录（根据实际路径替换，同SCRIPT_PARAM）。
     - `-v <your-media-path>/strm.txt:/strm.txt`：挂载 strm.txt（同SCRIPT_PARAM）。
4. **验证运行**：
   - 检查容器状态：
     ```bash
     docker ps
     ```
   - 查看日志：
     ```bash
     docker logs yabot
     ```

### 方法 2：使用 Docker Compose

1. **克隆仓库**：
   ```bash
   git clone https://github.com/leslie56912/yabot.git
   cd yabot
   ```

2. **配置环境变量**：
   - 复制示例文件：
     ```bash
     cp .env.example .env
     ```
   - 编辑 `.env` 文件，填入与方法 1 相同的配置。

3. **运行服务**：
   - 确保 `docker-compose.yml` 文件已正确配置，例如：
     ```yaml
     version: '3'
     services:
       yabot:
         image: leslie56912/yabot:latest
         container_name: yabot
         env_file:
           - .env
         volumes:
           - ./data:/app/data
           - /path/to/your/storage:/mnt/nvme0n1-4/xiaoya_emby/xiaoya
         restart: unless-stopped
     ```
   - 启动服务：
     ```bash
     docker-compose up -d
     ```

4. **验证运行**：
   - 检查容器状态：
     ```bash
     docker ps
     ```
   - 查看日志：
     ```bash
     docker logs yabot
     ```

### 方法 3：从源码构建

1. **克隆仓库**：
   ```bash
   git clone https://github.com/leslie56912/yabot.git
   cd yabot
   ```

2. **安装依赖**：
   ```bash
   pip install -r requirements.txt
   ```

3. **配置环境变量**：
   - 复制示例文件：
     ```bash
     cp .env.example .env
     ```
   - 编辑 `.env` 文件，填入与方法 1 相同的配置。

4. **运行服务**：
   ```bash
   python yabot.py
   ```

## 使用方法

1. **启动机器人**：
   - 部署完成后，机器人会自动响应 Telegram 消息。

2. **命令列表**：
   - `/save <链接> [目录]`：转存文件到指定目录（例：`/save https://cloud.189.cn/t/xxx 电影`）。
   - `/strm`：执行入库操作，生成 STRM 文件，需要自己准备小雅strm工具的strm.txt文件放到SCRIPT_PARAM定义的目录。
   - `/execute`：批量执行所有转存任务。
   - `/delete <任务ID>`：删除指定任务（例：`/delete 123` 删除任务 ID 为 123 的任务）。
   - `/commonfolders`：显示常用目录列表并选择默认目录。

3. **触发词**：
   - `转存 <链接> [目录]`：同 `/save` 功能。
   - `入库`：同 `/strm` 功能。
   - `全部执行`：同 `/execute` 功能。
   - `删除 <任务ID>`：同 `/delete` 功能。
   - `常用目录`：同 `/commonfolders` 功能。

## 项目结构

- `yabot.py`：机器人主程序。
- `create_task.py`：任务创建脚本。
- `execute_tasks.py`：任务执行脚本。
- `delete_task.py`：任务删除脚本。
- `init4.sh`：入库脚本。
- `docker-compose.yml`：Docker Compose 配置文件。
- `Dockerfile`：Docker 镜像构建文件。
- `.env.example`：环境变量模板。
- `requirements.txt`：Python 依赖列表。

## 版本历史
- **v1.0.4**（2025-04-13）：
  - 优化了目录寻找逻辑，先从历史记录查询，其次我的转存目录，最后全局枚举。
- **v1.0.3**（2025-04-13）：
  - 修复 `create_task.py` 中 `get_folder_name_by_id` 函数的无限循环问题。
  - 更新数据库路径为 `/app/data/messages.db`，确保数据持久化。
  - 更新转存命令为 `/save`，并同步文档。
  - 更新项目结构，新增 `delete_task.py`。
  - 完善常用目录功能，新增 `/commonfolders` 命令，用于显示常用目录列表并选择默认目录。
- **v1.0.2**（2025-04-11）：
  - 适配 `cloud189-auto-save:v2.2.9`。
- **v1.0.1**（2025-04-11）：
  - 修复 `create_task.py` 中的文件夹匹配 `NameError` 错误。
  - 修复 `yabot.py` 中 `/transfer` 命令未触发问题。
  - 新增转存目录支持及模糊匹配功能。
- **v1.0.0**（2025-04-09）：
  - 初始版本，支持入库和转存功能。

## 常见问题 (FAQ)

- **Q：转存任务失败，日志显示 "未找到目标目录"？**  
  A：检查 `.env` 文件中的 `TARGET_FOLDER_ID` 是否正确。可以通过 API 查询目录 ID：
  ```bash
  curl -X GET "http://your-server:3000/api/folders/<account_id>?folderId=-11" -H "Cookie: <your_cookie>"
  ```

- **Q：容器启动后，数据库文件未生成？**  
  A：确保 `docker-compose.yml` 或 `docker run` 命令中正确映射了 `/app/data` 目录，例如 `-v $(pwd)/data:/app/data`。

- **Q：如何备份数据库？**  
  A：数据库文件位于宿主机的 `./data/messages.db`，可以定期备份：
  ```bash
  cp ./data/messages.db ./data/messages.db.bak
  ```

## 贡献

欢迎通过提交 Issue 或 Pull Request 提供反馈和改进建议。

## 许可证

本项目采用 MIT 许可证，详情见 [LICENSE](LICENSE) 文件。
```
