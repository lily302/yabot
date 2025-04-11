#!/bin/bash

# 检查 /strm.txt 是否存在
STRM_FILE="/strm.txt"
if [ ! -f "$STRM_FILE" ]; then
    echo "错误：$STRM_FILE 不存在"
    exit 1
fi

# 确保 /media 目录存在
mkdir -p /media

# 从 strm.txt 读取配置
DOCKER_ADDRESS=$(grep -i docker_address "$STRM_FILE" | tr -d '\r' | cut -f2 -d= | sed 's/\//\\\//g; s/\s\+$//g')
SCAN_PATHS=$(grep -n scan_path "$STRM_FILE" | cut -f1 -d:)
USERNAME=$(grep username "$STRM_FILE" | tr -d '\r' | cut -f2 -d= | sed 's/\s\+$//g')
PASSWORD=$(grep password "$STRM_FILE" | tr -d '\r' | cut -f2 -d= | sed 's/\s\+$//g')

for i in $SCAN_PATHS; do
    cp /app/strm4.py /tmp/strm4.py || { echo "错误：无法复制 /app/strm4.py"; exit 1; }
    SCAN_PATH=$(head -n $i "$STRM_FILE" | tail -n 1 | tr -d '\r' | cut -f2 -d= | sed 's/\//\\\//g; s/\s\+$//g; s/&/%26/g')
    sed -i "s/DOCKER_ADDRESS/$DOCKER_ADDRESS/" /tmp/strm4.py || { echo "错误：sed 替换 DOCKER_ADDRESS 失败"; exit 1; }
    sed -i "s/SCAN_PATH/$SCAN_PATH/" /tmp/strm4.py || { echo "错误：sed 替换 SCAN_PATH 失败"; exit 1; }
    sed -i "s/USERNAME/$USERNAME/" /tmp/strm4.py || { echo "错误：sed 替换 USERNAME 失败"; exit 1; }
    sed -i "s/PASSWORD/$PASSWORD/" /tmp/strm4.py || { echo "错误：sed 替换 PASSWORD 失败"; exit 1; }
    python /tmp/strm4.py || { echo "错误：strm4.py 执行失败"; exit 1; }

    k=$(head -n $i "$STRM_FILE" | tail -n 1 | tr -d '\r' | cut -f2 -d= | sed 's/\s\+$//g; s/%20/ /g; s/&/%26/g')
    cd /media/strm"$k" || { echo "错误：无法进入目录 /media/strm$k"; exit 1; }
    find /media/strm"$k" -name "*.strm" -exec sed -i "s# #%20#g; s#|#%7C#g" {} \;
    chmod -R 777 /media/strm"$k"/*
done

echo "处理完成：$STRM_FILE"