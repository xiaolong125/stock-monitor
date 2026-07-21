# A 股盯盘工具

纯标准库实现，通过新浪行情 API 获取实时数据。自动判断北京时间交易时段，异常时弹出 macOS 系统通知。

## 环境要求

- Python 3.9+
- macOS（通知功能依赖 `osascript`）

## 安装

```bash
git clone https://github.com/xiaolong125/stock-monitor.git
cd stock-monitor
python3 -m venv venv
source venv/bin/activate
```

## 配置

编辑 `config.json`：

```json
{
  "watchlist": [
    "601138"
  ],
  "thresholds": {
    "price_change_pct": 3.0,
    "volume_ratio": 2.5,
    "turnover_rate": 5.0,
    "amplitude": 6.0,
    "near_limit_up": 9.0,
    "near_limit_down": -9.0
  },
  "poll_interval_minutes": 1
}
```

| 配置项 | 说明 |
|--------|------|
| `watchlist` | 自选股代码列表 |
| `price_change_pct` | 涨跌幅报警阈值（%） |
| `amplitude` | 振幅报警阈值（%） |
| `near_limit_up` | 涨停线（%） |
| `near_limit_down` | 跌停线（%） |
| `poll_interval_minutes` | 轮询间隔（分钟） |

配置修改后下次轮询生效，无需重启。

## 使用

```bash
# 单次检查
python3 stock_monitor.py

# 持续盯盘（每分钟轮询）
./run.sh

# 测试通知是否正常
python3 stock_monitor.py --test

# 禁止弹窗（仅终端输出）
python3 stock_monitor.py --no-notify

# 非交易时段也弹窗
python3 stock_monitor.py --force-notify
```

## 提醒规则

| 事件 | 触发条件 | 频率控制 |
|------|----------|----------|
| 涨停/跌停 | 涨跌幅触及阈值线 | 每次都报 |
| 由红转绿/由绿转红 | 涨跌幅正负翻转 | 每次都报 |
| 大涨/大跌 | 涨跌幅超过阈值且方向变化 | 方向不变不重复 |
| 振幅新高 | 当日振幅超过阈值且创新高 | 仅在新高时 |

## 注意事项

- **非交易时段**（盘前、午休、收盘后、周末）只展示数据不弹窗，避免打扰
- 数据来源为新浪行情 API，有 15 分钟左右延迟属正常现象
- 通知依赖 macOS `osascript`，非 macOS 系统仅终端输出
