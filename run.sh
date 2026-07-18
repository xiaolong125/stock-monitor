#!/bin/bash
# A股盯盘 - 快捷运行脚本
cd "$(dirname "$0")"
python3 stock_monitor.py "$@"
