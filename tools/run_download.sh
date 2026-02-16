#!/bin/bash
# run_download.sh - 包装脚本

# 直接设置环境变量
export JAXA_USER=jinhui.sg_gmail.com
export JAXA_PASS='SP+wari8'

# 运行下载 - 全部数据
./bulk_download_to_s3.sh 2025-10-01 2026-01-27
