#!/usr/bin/env python3
"""A股盯盘工具 - 纯标准库实现，通过新浪行情API获取实时数据。

自动判断北京时间交易时段，非交易时段只展示数据不弹窗。
振幅等累积指标只在创新高时提醒，避免重复噪音。

用法:
    python3 stock_monitor.py              # 单次检查
    python3 stock_monitor.py --test       # 测试通知是否正常
"""

import json
import os
import re
import subprocess
import sys
import urllib.request
from datetime import datetime, timezone, timedelta

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(SCRIPT_DIR, "config.json")
STATE_PATH = os.path.join(SCRIPT_DIR, "state.json")  # 当日状态（振幅峰值等）

SINA_URL = "http://hq.sinajs.cn/list={codes}"
SINA_HEADERS = {"Referer": "https://finance.sina.com.cn"}
BEIJING_TZ = timezone(timedelta(hours=8))


def load_config():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def load_state() -> dict:
    """加载当日状态，跨天自动重置。"""
    try:
        with open(STATE_PATH, "r", encoding="utf-8") as f:
            state = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        state = {}

    today = beijing_now().strftime("%Y-%m-%d")
    if state.get("date") != today:
        state = {"date": today, "stocks": {}}
    return state


def save_state(state: dict):
    """保存当日状态。"""
    with open(STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def beijing_now() -> datetime:
    return datetime.now(timezone.utc).astimezone(BEIJING_TZ)


def is_trading_time(dt: datetime | None = None) -> tuple[bool, str]:
    if dt is None:
        dt = beijing_now()
    weekday = dt.weekday()
    t = dt.hour * 60 + dt.minute
    if weekday >= 5:
        return False, "周末休市" if weekday == 5 else "周日休市"
    if 9 * 60 + 30 <= t < 11 * 60 + 30:
        return True, "早盘交易中"
    elif 11 * 60 + 30 <= t < 13 * 60:
        return False, "午间休市"
    elif 13 * 60 <= t < 15 * 60:
        return True, "午盘交易中"
    elif t < 9 * 60 + 30:
        return False, "盘前等待"
    else:
        return False, "已收盘"


def code_to_sina_symbol(code: str) -> str:
    return f"sh{code}" if code.startswith(("60", "68")) else f"sz{code}"


def fetch_all_stocks(codes: list[str]) -> dict[str, dict]:
    symbols = [code_to_sina_symbol(c) for c in codes]
    url = SINA_URL.format(codes=",".join(symbols))
    try:
        req = urllib.request.Request(url, headers=SINA_HEADERS)
        with urllib.request.urlopen(req, timeout=10) as resp:
            raw = resp.read()
    except Exception as e:
        print(f"  网络错误: {e}", file=sys.stderr)
        return {}

    text = raw.decode("gbk", errors="replace")
    results = {}

    for line in text.strip().splitlines():
        m = re.match(r'var hq_str_(\w+)="(.*)";', line)
        if not m:
            continue
        symbol, payload = m.group(1), m.group(2)
        fields = payload.split(",")
        if len(fields) < 32:
            continue
        code = symbol[2:]

        def num(s: str) -> float | None:
            if not s or s.strip() == "":
                return None
            try:
                return float(s)
            except ValueError:
                return None

        price = num(fields[3])
        prev_close = num(fields[2])
        high = num(fields[4])
        low = num(fields[5])
        data_valid = price is not None and price > 0

        change_pct = None
        if data_valid and prev_close is not None and prev_close != 0:
            change_pct = (price - prev_close) / prev_close * 100

        amplitude = None
        if data_valid and high is not None and low is not None and prev_close is not None and prev_close != 0:
            amplitude = (high - low) / prev_close * 100

        data_dt = None
        try:
            data_dt = datetime.strptime(
                f"{fields[30]} {fields[31]}", "%Y-%m-%d %H:%M:%S"
            ).replace(tzinfo=BEIJING_TZ)
        except (ValueError, IndexError):
            pass

        results[code] = {
            "_code": code,
            "_name": fields[0],
            "_valid": data_valid,
            "price": price,
            "prev_close": prev_close,
            "open": num(fields[1]),
            "high": high,
            "low": low,
            "volume": num(fields[8]),
            "amount": num(fields[9]),
            "change_pct": change_pct,
            "amplitude": amplitude,
            "data_time": data_dt,
        }
    return results


def detect_anomalies(data: dict, thresholds: dict, state: dict) -> list[str]:
    """检测异常，振幅等累积指标只在新高时提醒。"""
    if not data.get("_valid"):
        return []

    alerts = []
    code = data["_code"]
    name = data["_name"]
    price = data.get("price") or 0
    change_pct = data.get("change_pct")
    amplitude = data.get("amplitude")

    # 确保当天状态中有该股票
    if code not in state["stocks"]:
        state["stocks"][code] = {}
    stock_state = state["stocks"][code]

    if change_pct is not None and change_pct != 0:
        limit_up = thresholds.get("near_limit_up", 9.0)
        limit_down = thresholds.get("near_limit_down", -9.0)
        price_change_threshold = thresholds.get("price_change_pct", 3.0)
        direction = "up" if change_pct > 0 else "down"

        # 涨跌停：始终提醒
        if change_pct >= limit_up:
            alerts.append(f"🚀 {name}({code}) 涨停 +{change_pct:.2f}% 现价{price:.2f}")
        elif change_pct <= limit_down:
            alerts.append(f"🔻 {name}({code}) 跌停 {change_pct:.2f}% 现价{price:.2f}")

        # 方向翻转（由红转绿 / 由绿转红）：始终提醒，不受阈值限制
        prev_direction = stock_state.get("last_direction")
        if prev_direction is not None and prev_direction != direction:
            label = "由红转绿 🔻" if direction == "down" else "由绿转红 🚀"
            alerts.append(f"🔄 {name}({code}) {label} {change_pct:+.2f}% 现价{price:.2f}")
            # 方向变了，同步重置阈值告警状态，让大涨大跌也能重新触发
            stock_state.pop("last_alert_direction", None)
        stock_state["last_direction"] = direction

        # 大涨大跌：方向变化或重新进入阈值时才提醒
        if abs(change_pct) >= price_change_threshold:
            prev_alert_dir = stock_state.get("last_alert_direction")
            if prev_alert_dir != direction:
                label = "大涨" if direction == "up" else "大跌"
                alerts.append(f"⚠️ {name}({code}) {label} {change_pct:+.2f}% 现价{price:.2f}")
                stock_state["last_alert_direction"] = direction
        else:
            # 回到阈值以下，重置告警方向，以便下次重新进入时提醒
            stock_state.pop("last_alert_direction", None)

    # 振幅：只在创新高时提醒
    if amplitude is not None and amplitude >= thresholds.get("amplitude", 6.0):
        prev_max = stock_state.get("max_amplitude", 0)
        if amplitude > prev_max + 0.01:  # 0.01 容差避免浮点抖动
            alerts.append(f"📈 {name}({code}) 振幅新高 {amplitude:.2f}%")
            stock_state["max_amplitude"] = amplitude

    return alerts


def send_notification(title: str, body: str, sound: str = "Glass"):
    safe_title = title.replace('"', '\\"').replace("\\", "\\\\")
    safe_body = body.replace('"', '\\"').replace("\\", "\\\\")
    script = (
        f'display notification "{safe_body}"'
        f' with title "{safe_title}"'
        f' sound name "{sound}"'
    )
    try:
        subprocess.run(["osascript", "-e", script], capture_output=True, timeout=5)
    except Exception as e:
        print(f"  通知发送失败: {e}", file=sys.stderr)


def format_stock_line(data: dict) -> str:
    name = data.get("_name", "???")
    code = data["_code"]
    if not data.get("_valid"):
        prev_close = data.get("prev_close") or 0
        return f"  {name:8s} {code:6s}  {'—':>8s}  停牌/未开盘  昨收:{prev_close:.2f}"

    price = data.get("price") or 0
    change_pct = data.get("change_pct") or 0
    direction = "↑" if (change_pct or 0) > 0 else "↓" if (change_pct or 0) < 0 else "→"
    data_time = data.get("data_time")
    age_str = ""
    if data_time:
        age_min = (beijing_now() - data_time).total_seconds() / 60
        if age_min > 15:
            age_str = f"  [数据{int(age_min)}分钟前]"
    return (
        f"  {name:8s} {code:6s}  {price:8.2f}  "
        f"{direction} {change_pct:+.2f}%{age_str}"
    )


def run_once(config: dict, notify: bool = True, force_notify: bool = False):
    watchlist = config["watchlist"]
    thresholds = config["thresholds"]
    bj_now = beijing_now()
    trading, status = is_trading_time(bj_now)
    state = load_state()

    print(f"\n{'='*60}")
    print(f"  A股盯盘")
    print(f"  北京时间: {bj_now.strftime('%H:%M:%S %m-%d')} ({status})")
    print(f"{'='*60}")

    all_data = fetch_all_stocks(watchlist)
    all_alerts = []

    for code in watchlist:
        data = all_data.get(code)
        if data is None:
            print(f"  [{code}] 无数据")
            continue
        print(format_stock_line(data))
        alerts = detect_anomalies(data, thresholds, state)
        all_alerts.extend(alerts)

    save_state(state)

    if all_alerts:
        print(f"\n{'─'*60}")
        print(f"  ⚡ 异常提醒 ({len(all_alerts)} 条):")
        for alert in all_alerts:
            print(f"    {alert}")
        print(f"{'─'*60}")

        should_notify = notify and (trading or force_notify)
        if should_notify:
            title = f"盯盘异常 ({len(all_alerts)}条)"
            body_lines = all_alerts[:3]
            if len(all_alerts) > 3:
                body_lines.append(f"...还有 {len(all_alerts) - 3} 条")
            body = "\\n".join(body_lines)
            send_notification(title, body)
        elif notify and not trading:
            print(f"  🔕 非交易时段，已抑制弹窗")
    else:
        print(f"\n  ✅ 无异常")

    return all_alerts


def main():
    config = load_config()

    if "--test" in sys.argv:
        print("测试通知...")
        send_notification("盯盘测试", "如果你看到这条通知，弹窗功能正常 ✅")
        print("已发送，检查屏幕右上角通知中心。")
        return

    notify = "--no-notify" not in sys.argv
    force = "--force-notify" in sys.argv
    run_once(config, notify=notify, force_notify=force)


if __name__ == "__main__":
    main()
