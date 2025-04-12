FROM python:3.9-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    curl \
    bash \
    && rm -rf /var/lib/apt/lists/*

# 升级 pip
RUN pip install --upgrade pip

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY yabot.py .
COPY execute_tasks.py .
COPY create_task.py .
COPY strm4.py .
COPY init4.sh .
COPY delete_task.py .

RUN chmod +x /app/init4.sh

CMD ["python", "yabot.py"]