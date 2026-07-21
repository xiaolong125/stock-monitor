# A 股盯盘工具

纯标准库实现，通过新浪行情 API 获取实时数据。在 Claude Code 中运行，异常实时推送到对话中。

## 环境要求

- Python 3.9+

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

在 Claude Code 中说"开始盯盘"，Claude 会自动启动后台轮询并实时推送异常：

```
开始盯盘
```

或手动运行：

```bash
# 单次检查
python3 stock_monitor.py

# 持续盯盘（每分钟轮询）
./run.sh
```

## 提醒规则

| 事件 | 触发条件 | 频率控制 |
|------|----------|----------|
| 涨停/跌停 | 涨跌幅触及阈值线 | 每次都报 |
| 由红转绿/由绿转红 | 涨跌幅正负翻转 | 每次都报 |
| 大涨/大跌 | 涨跌幅超过阈值且方向变化 | 方向不变不重复 |
| 振幅新高 | 当日振幅超过阈值且创新高 | 仅在新高时 |

## 工作原理

- 通过新浪行情 API 获取实时数据
- 自动判断北京时间交易时段（盘前/早盘/午休/午盘/收盘）
- 非交易时段只展示数据不弹窗，避免打扰
- 异常检测结果直接推送到 Claude Code 对话中
