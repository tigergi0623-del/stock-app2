"""
台股即時股價網頁版（雲端簡化版）
- 即時股價 + 損益計算
- 部署至 Render
"""

import requests
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime
import threading
import time
import os
import json

STOCKS = [
    ("2330",   "台積電"),
    ("2383",   "台光電"),
    ("3563",   "牧德"),
    ("6831",   "邁科"),
    ("3030",   "德律"),
    ("3374",   "精材"),
    ("3189",   "景碩"),
    ("2327",   "國巨"),
    ("2492",   "華新科"),
    ("00981A", "主動統一台股增長"),
    ("00403A", "主動統一升級50"),
]

UPDATE_INTERVAL = 5
PORT = int(os.environ.get("PORT", 8888))

cache = {"data": [], "updated_at": "—"}


def fetch_price(stock_id):
    for market in ["tse", "otc"]:
        url = (
            f"https://mis.twse.com.tw/stock/api/getStockInfo.jsp"
            f"?ex_ch={market}_{stock_id}.tw&json=1&delay=0"
        )
        try:
            resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
            items = resp.json().get("msgArray", [])
            if items:
                d = items[0]
                price  = d.get("z", "-")
                yclose = d.get("y", "-")
                high   = d.get("h", "-")
                low    = d.get("l", "-")
                open_p = d.get("o", "-")
                if price and price != "-":
                    p   = float(price)
                    y   = float(yclose) if yclose and yclose != "-" else None
                    chg = round(p - y, 2) if y else None
                    chg_pct = round((p - y) / y * 100, 2) if y else None
                    return {
                        "price": p, "chg": chg, "chg_pct": chg_pct,
                        "high": float(high) if high and high != "-" else None,
                        "low":  float(low)  if low  and low  != "-" else None,
                        "open": float(open_p) if open_p and open_p != "-" else None,
                    }
        except Exception:
            pass
    return None


def is_trading_time():
    now = datetime.now()
    if now.weekday() >= 5:
        return False
    t = now.hour * 60 + now.minute
    return 9 * 60 <= t <= 13 * 60 + 30


def render_main_html():
    trading = is_trading_time()
    status_color = "#27ae60" if trading else "#e67e22"
    status_text  = "交易中 🟢" if trading else "非交易時間 🟡"

    rows = ""
    for i, item in enumerate(cache["data"]):
        sid  = item["id"]
        name = item["name"]
        info = item["info"]

        if info:
            price   = f"{info['price']:,.2f}"
            chg     = info["chg"] or 0
            chg_pct = info["chg_pct"] or 0
            high    = f"{info['high']:,.2f}" if info["high"] else "—"
            low     = f"{info['low']:,.2f}"  if info["low"]  else "—"
            open_p  = f"{info['open']:,.2f}" if info["open"] else "—"
            chg_val = chg
            if chg > 0:
                color = "#c0392b"; bg = "#fff5f5"; arrow = "▲"
                chg_str = f"+{chg}"; pct_str = f"+{chg_pct}%"
            elif chg < 0:
                color = "#2980b9"; bg = "#f5f9ff"; arrow = "▼"
                chg_str = f"{chg}"; pct_str = f"{chg_pct}%"
            else:
                color = "#555"; bg = "#fafafa"; arrow = "—"
                chg_str = "0"; pct_str = "0%"
        else:
            price = chg_str = pct_str = high = low = open_p = "—"
            color = "#aaa"; bg = "#fafafa"; arrow = ""; chg_val = 0

        rows += f"""
        <tr style="background:{bg}">
            <td>{sid}</td>
            <td style="text-align:left;font-weight:600">{name}</td>
            <td style="font-size:1.1em;font-weight:700;color:{color}">{price}</td>
            <td style="color:{color};font-weight:600">{arrow} {chg_str}</td>
            <td style="color:{color}">{pct_str}</td>
            <td>{open_p}</td><td>{high}</td><td>{low}</td>
            <td>
                <input type="number" min="0" value="0"
                       id="qty_{i}" data-sid="{sid}" data-chg="{chg_val}"
                       oninput="calcPnl()"
                       style="width:70px;padding:4px 6px;border:1px solid #ccc;
                              border-radius:6px;text-align:center;font-size:0.95em;">
            </td>
            <td id="pnl_{i}" style="font-weight:700;min-width:100px">—</td>
        </tr>"""

    return f"""<!DOCTYPE html>
<html lang="zh-TW">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>台股即時股價</title>
<style>
  * {{ box-sizing:border-box; margin:0; padding:0; }}
  body {{ font-family:Arial,sans-serif; background:#f0f2f5; color:#333; }}
  .header {{ background:#1a3a5c; color:white; padding:20px 30px; display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:10px; }}
  .header h1 {{ font-size:1.6em; }}
  .header .meta {{ font-size:0.85em; margin-top:6px; opacity:0.85; }}
  .status {{ display:inline-block; padding:3px 10px; border-radius:20px; background:{status_color}; color:white; font-size:0.8em; margin-left:10px; }}
  .container {{ padding:20px; overflow-x:auto; }}
  table {{ width:100%; border-collapse:collapse; background:white; border-radius:10px; overflow:hidden; box-shadow:0 2px 12px rgba(0,0,0,0.08); }}
  th {{ background:#1a3a5c; color:white; padding:12px 14px; font-size:0.88em; }}
  td {{ padding:10px 14px; border-bottom:1px solid #eee; text-align:center; font-size:0.95em; }}
  tr:last-child td {{ border-bottom:none; }}
  .total-row td {{ background:#1a3a5c !important; color:white; font-weight:700; font-size:1.05em; padding:14px; }}
  .footer {{ text-align:center; color:#aaa; font-size:0.8em; padding:16px; }}
</style>
</head>
<body>
<div class="header">
  <div>
    <h1>📈 台股即時股價 <span class="status">{status_text}</span></h1>
    <div class="meta">
      更新時間：{cache["updated_at"]}　每 {UPDATE_INTERVAL} 秒自動更新
      <span id="countdown"></span>
    </div>
  </div>
</div>
<div class="container">
<table>
  <thead>
  <tr>
    <th>代號</th><th>名稱</th><th>成交價</th>
    <th>漲跌</th><th>漲跌幅</th>
    <th>開盤</th><th>最高</th><th>最低</th>
    <th>張數</th><th>當日損益</th>
  </tr>
  </thead>
  <tbody>
  {rows}
  <tr class="total-row">
    <td colspan="9" style="text-align:right">📊 當日損益合計</td>
    <td id="total">—</td>
  </tr>
  </tbody>
</table>
</div>
<div class="footer">資料來源：台灣證券交易所</div>

<script>
  const QTY_KEY = "stock_qty";
  const n = {len(cache["data"])};
  let sec = {UPDATE_INTERVAL};

  function saveQty() {{
    const qtys = {{}};
    for (let i = 0; i < n; i++) {{
      const el = document.getElementById("qty_" + i);
      if (el) qtys[el.dataset.sid] = el.value;
    }}
    localStorage.setItem(QTY_KEY, JSON.stringify(qtys));
  }}

  function loadQty() {{
    const saved = localStorage.getItem(QTY_KEY);
    if (!saved) return;
    const qtys = JSON.parse(saved);
    for (let i = 0; i < n; i++) {{
      const el = document.getElementById("qty_" + i);
      if (el && qtys[el.dataset.sid] !== undefined) el.value = qtys[el.dataset.sid];
    }}
  }}

  function calcPnl() {{
    saveQty();
    let total = 0, hasAny = false;
    for (let i = 0; i < n; i++) {{
      const qtyEl = document.getElementById("qty_" + i);
      const pnlEl = document.getElementById("pnl_" + i);
      if (!qtyEl || !pnlEl) continue;
      const qty = parseFloat(qtyEl.value) || 0;
      const chg = parseFloat(qtyEl.dataset.chg) || 0;
      const pnl = qty * chg * 1000;
      if (qty > 0) {{
        hasAny = true;
        pnlEl.textContent = (pnl >= 0 ? "+" : "") + pnl.toLocaleString() + " 元";
        pnlEl.style.color = pnl > 0 ? "#c0392b" : pnl < 0 ? "#2980b9" : "#555";
        total += pnl;
      }} else {{
        pnlEl.textContent = "—"; pnlEl.style.color = "#aaa";
      }}
    }}
    const totalEl = document.getElementById("total");
    if (hasAny) {{
      totalEl.textContent = (total >= 0 ? "+" : "") + total.toLocaleString() + " 元";
      totalEl.style.color = total > 0 ? "#ffcccc" : total < 0 ? "#cce0ff" : "white";
    }} else {{
      totalEl.textContent = "—"; totalEl.style.color = "white";
    }}
  }}

  function tick() {{
    document.getElementById("countdown").textContent = "（" + sec + " 秒後更新）";
    if (sec <= 0) location.reload();
    sec--;
  }}
  tick();
  setInterval(tick, 1000);

  loadQty();
  calcPnl();
</script>
</body>
</html>"""


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/":
            html = render_main_html().encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(html)
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        pass


def update_loop():
    while True:
        results = []
        for stock_id, name in STOCKS:
            info = fetch_price(stock_id)
            results.append({"id": stock_id, "name": name, "info": info})
        cache["data"] = results
        cache["updated_at"] = datetime.now().strftime("%Y/%m/%d %H:%M:%S")
        time.sleep(UPDATE_INTERVAL)


def main():
    print(f"🚀 台股即時股價啟動！PORT: {PORT}")
    threading.Thread(target=update_loop, daemon=True).start()

    print("   正在抓取第一次股價...", end=" ", flush=True)
    while not cache["data"]:
        time.sleep(1)
    print("完成！")

    server = HTTPServer(("0.0.0.0", PORT), Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n⏹️  已停止。")


if __name__ == "__main__":
    main()
