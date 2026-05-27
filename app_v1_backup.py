"""
A股短线回测 Web 工具 - 带分析与推荐
技术栈: Flask + AKShare + mplfinance + Backtrader
"""

import os
import io
import base64
import json
from datetime import datetime, timedelta

# 启动时清除代理，避免 curl_cffi 误用
for k in ['HTTP_PROXY', 'HTTPS_PROXY', 'http_proxy', 'https_proxy', 'ALL_PROXY', 'all_proxy']:
    os.environ.pop(k, None)

import baostock as bs
import akshare as ak
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
import mplfinance as mpf
from flask import Flask, render_template_string, request, jsonify

app = Flask(__name__)

# ── 中文字体 ──
_zh_font = None
for fp in [
    '/System/Library/Fonts/Supplemental/STHeiti Medium.ttc',
    '/System/Library/Fonts/PingFang.ttc',
    '/System/Library/Fonts/Hiragino Sans GB.ttc',
]:
    if os.path.exists(fp):
        _zh_font = fm.FontProperties(fname=fp)
        break
zh = _zh_font

# ── HTML 模板 ──
HTML = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>A股短线回测 & 分析推荐</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:#f0f2f5;color:#333;padding:20px}
.container{max-width:1100px;margin:0 auto}
.card{background:#fff;border-radius:12px;padding:24px;margin-bottom:20px;box-shadow:0 2px 8px rgba(0,0,0,.08)}
h1{font-size:24px;margin-bottom:4px;color:#1a1a2e}
.sub{color:#888;margin-bottom:20px;font-size:14px}
.form-row{display:flex;flex-wrap:wrap;gap:12px;align-items:end;margin-bottom:16px}
.form-group{display:flex;flex-direction:column;gap:4px}
.form-group label{font-size:13px;color:#666;font-weight:600}
.form-group input,.form-group select{padding:8px 12px;border:1px solid #ddd;border-radius:8px;font-size:14px;outline:none}
.form-group input:focus,.form-group select:focus{border-color:#4a6cf7}
.btn{padding:10px 24px;background:#4a6cf7;color:#fff;border:none;border-radius:8px;font-size:15px;cursor:pointer;transition:.2s}
.btn:hover{background:#3b5de7}
.btn:disabled{opacity:.6;cursor:not-allowed}
.loading{text-align:center;padding:40px;color:#999;display:none}
.spinner{display:inline-block;width:32px;height:32px;border:3px solid #eee;border-top-color:#4a6cf7;border-radius:50%;animation:spin .8s linear infinite;margin-bottom:12px}
@keyframes spin{to{transform:rotate(360deg)}}
.results{margin-top:20px}
.kpi-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(140px,1fr));gap:12px;margin-bottom:20px}
.kpi{background:#f8f9ff;border-radius:10px;padding:14px;text-align:center}
.kpi .val{font-size:22px;font-weight:700;color:#1a1a2e}
.kpi .lbl{font-size:12px;color:#888;margin-top:4px}
.kpi.green .val{color:#22c55e}
.kpi.red .val{color:#ef4444}
.signal-box{padding:14px 18px;border-radius:10px;margin-bottom:20px;font-size:16px;font-weight:600}
.signal-buy{background:#dcfce7;color:#166534;border:1px solid #bbf7d0}
.signal-sell{background:#fee2e2;color:#991b1b;border:1px solid #fecaca}
.signal-hold{background:#fef9c3;color:#854d0e;border:1px solid #fef08a}
.signal-neutral{background:#f3f4f6;color:#6b7280;border:1px solid #e5e7eb}
.rec-box{background:#f0f9ff;border:1px solid #bae6fd;border-radius:10px;padding:14px 18px;margin-bottom:20px;font-size:14px;line-height:1.7}
.rec-box strong{color:#0369a1}
img{max-width:100%;border-radius:8px;margin-top:12px}
.trade-table{width:100%;border-collapse:collapse;font-size:13px;margin-top:12px}
.trade-table th{background:#f8f9ff;text-align:left;padding:8px 10px;border-bottom:2px solid #e5e7eb;font-weight:600}
.trade-table td{padding:8px 10px;border-bottom:1px solid #f0f0f0}
.tag{display:inline-block;padding:2px 8px;border-radius:4px;font-size:11px;font-weight:600}
.tag.buy{background:#dcfce7;color:#166534}
.tag.sell{background:#fee2e2;color:#991b1b}
</style>
</head>
<body>
<div class="container">
<div class="card">
<h1>📊 A股短线回测 + 分析推荐</h1>
<p class="sub">隔夜持仓策略 · 5~20日短线周期 · 免费数据源 (AKShare)</p>
<form id="form" onsubmit="run(event)">
<div class="form-row">
<div class="form-group">
<label>股票代码</label>
<input type="text" id="code" value="000001" placeholder="如 000001 或 600519" style="width:130px">
</div>
<div class="form-group">
<label>回测天数</label>
<select id="days">
<option value="60">60天（约3个月）</option>
<option value="120" selected>120天（约6个月）</option>
<option value="250">250天（约1年）</option>
</select>
</div>
<div class="form-group">
<label>均线周期</label>
<select id="ma">
<option value="5">MA5</option>
<option value="10" selected>MA10</option>
<option value="20">MA20</option>
</select>
</div>
<div class="form-group">
<label>买入阈值</label>
<select id="buy_threshold">
<option value="0.5">跌幅 &gt; 0.5%</option>
<option value="1.0" selected>跌幅 &gt; 1.0%</option>
<option value="2.0">跌幅 &gt; 2.0%</option>
<option value="3.0">跌幅 &gt; 3.0%</option>
</select>
</div>
<div class="form-group">
<label>止盈 %</label>
<select id="tp">
<option value="3">+3%</option>
<option value="5" selected>+5%</option>
<option value="8">+8%</option>
<option value="10">+10%</option>
</select>
</div>
<div class="form-group">
<label>止损 %</label>
<select id="sl">
<option value="-2">-2%</option>
<option value="-3" selected>-3%</option>
<option value="-5">-5%</option>
</select>
</div>
</div>
<button type="submit" class="btn" id="runBtn">🚀 开始回测 + 分析</button>
</form>
</div>

<div class="loading" id="loading">
<div class="spinner"></div>
<div>正在获取数据并跑回测...</div>
</div>

<div id="results"></div>
</div>

<script>
async function run(e){
e.preventDefault();
const btn=document.getElementById('runBtn');
const loading=document.getElementById('loading');
const results=document.getElementById('results');
btn.disabled=true;loading.style.display='block';results.innerHTML='';
try{
const r=await fetch('/backtest',{
method:'POST',
headers:{'Content-Type':'application/json'},
body:JSON.stringify({
code:document.getElementById('code').value.trim(),
days:parseInt(document.getElementById('days').value),
ma:parseInt(document.getElementById('ma').value),
buy_threshold:parseFloat(document.getElementById('buy_threshold').value),
tp:parseFloat(document.getElementById('tp').value),
sl:parseFloat(document.getElementById('sl').value)
})
});
const data=await r.json();
if(data.error){results.innerHTML='<div class="card" style="color:red">❌ '+data.error+'</div>';return;}
results.innerHTML=data.html;
}catch(e){results.innerHTML='<div class="card" style="color:red">❌ 请求失败：'+e.message+'</div>';}
finally{btn.disabled=false;loading.style.display='none';}
}
</script>
</body>
</html>"""


def _get_data(code, days):
    """通过 baostock 获取 A股日K数据（无需代理，稳定可靠）"""
    from datetime import datetime, timedelta
    today = datetime.now()
    start = (today - timedelta(days=days + 30)).strftime('%Y-%m-%d')
    end = today.strftime('%Y-%m-%d')

    # 登录（线程安全，多次调用无副作用）
    lg = bs.login()
    if lg.error_code != '0':
        raise ValueError(f'baostock login failed: {lg.error_msg}')

    # sh.600000 或 sz.000001
    code_padded = code.zfill(6)
    if code_padded.startswith('6'):
        bs_code = f'sh.{code_padded}'
    else:
        bs_code = f'sz.{code_padded}'

    rs = bs.query_history_k_data_plus(
        bs_code,
        'date,open,high,low,close,volume,amount',
        start_date=start, end_date=end,
        frequency='d', adjustflag='2'
    )
    if rs.error_code != '0':
        bs.logout()
        raise ValueError(f'baostock query failed: {rs.error_msg}')

    rows = []
    while rs.next():
        rows.append(rs.get_row_data())
    bs.logout()

    if not rows:
        raise ValueError(f'未获取到数据，请检查股票代码：{code}')

    df = pd.DataFrame(rows, columns=['日期', '开盘', '最高', '最低', '收盘', '成交量', '成交额'])
    for col in ['开盘', '最高', '最低', '收盘']:
        df[col] = df[col].astype(float)
    df['成交量'] = df['成交量'].astype(float)
    df['成交额'] = df['成交额'].astype(float)
    df['日期'] = pd.to_datetime(df['日期'])
    df.sort_values('日期', inplace=True)
    df.reset_index(drop=True, inplace=True)
    # 计算涨跌幅
    df['涨跌幅'] = df['收盘'].pct_change() * 100
    df['振幅'] = (df['最高'] - df['最低']) / df['开盘'].shift(1) * 100
    df['换手率'] = 0.0  # baostock 不提供换手率，设为0不影响回测
    return df


def _calc_indicators(df):
    """计算技术指标"""
    # 均线
    for m in [5, 10, 20, 30]:
        df[f'MA{m}'] = df['收盘'].rolling(m).mean()
    # MACD
    ema12 = df['收盘'].ewm(span=12).mean()
    ema26 = df['收盘'].ewm(span=26).mean()
    df['DIF'] = ema12 - ema26
    df['DEA'] = df['DIF'].ewm(span=9).mean()
    df['MACD'] = 2 * (df['DIF'] - df['DEA'])
    # KDJ
    low_min = df['最低'].rolling(9).min()
    high_max = df['最高'].rolling(9).max()
    df['RSV'] = (df['收盘'] - low_min) / (high_max - low_min) * 100
    df['K'] = df['RSV'].ewm(com=2).mean()
    df['D'] = df['K'].ewm(com=2).mean()
    df['J'] = 3 * df['K'] - 2 * df['D']
    # RSI
    delta = df['收盘'].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(14).mean()
    avg_loss = loss.rolling(14).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    df['RSI'] = 100 - (100 / (1 + rs))
    # 成交量 MA
    df['VOL_MA5'] = df['成交量'].rolling(5).mean()
    return df


def _generate_signal(df):
    """综合技术分析生成买卖信号"""
    last = df.iloc[-1]
    prev = df.iloc[-2]
    signals = []
    score = 0

    # 1. 均线信号
    if not pd.isna(last['MA5']) and not pd.isna(last['MA10']):
        if last['MA5'] > last['MA10']:
            signals.append(('✅', 'MA5 上穿 MA10（短期偏多）', '+1'))
            score += 1
        elif last['MA5'] < last['MA10']:
            signals.append(('⚠️', 'MA5 下穿 MA10（短期偏空）', '-1'))
            score -= 1
    if not pd.isna(last['MA10']) and not pd.isna(last['MA20']):
        if last['MA10'] > last['MA20']:
            signals.append(('✅', 'MA10 在 MA20 上方（中期偏多）', '+1'))
            score += 1
        else:
            signals.append(('⚠️', 'MA10 在 MA20 下方（中期偏空）', '-1'))
            score -= 1

    # 2. MACD
    if not pd.isna(last['MACD']) and not pd.isna(prev['MACD']):
        if last['MACD'] > 0 and prev['MACD'] <= 0:
            signals.append(('✅', 'MACD 金叉（买入信号）', '+2'))
            score += 2
        elif last['MACD'] < 0 and prev['MACD'] >= 0:
            signals.append(('🚨', 'MACD 死叉（卖出信号）', '-2'))
            score -= 2
        elif last['MACD'] > 0:
            signals.append(('📗', 'MACD > 0（多头区间）', '+1'))
            score += 1
        else:
            signals.append(('📕', 'MACD < 0（空头区间）', '-1'))
            score -= 1

    # 3. KDJ
    if not pd.isna(last['K']) and not pd.isna(prev['K']):
        if last['K'] > last['D']:
            signals.append(('✅', 'KDJ 多头（K > D）', '+1'))
            score += 1
        else:
            signals.append(('⚠️', 'KDJ 空头（K < D）', '-1'))
            score -= 1
        if last['J'] < 20:
            signals.append(('💡', 'J 值 < 20（超卖，可能反弹）', '+1'))
            score += 1
        elif last['J'] > 80:
            signals.append(('🚨', 'J 值 > 80（超买，注意回调）', '-1'))
            score -= 1

    # 4. RSI
    if not pd.isna(last['RSI']):
        if last['RSI'] < 30:
            signals.append(('💡', f'RSI = {last["RSI"]:.1f}（超卖区）', '+1'))
            score += 1
        elif last['RSI'] > 70:
            signals.append(('🚨', f'RSI = {last["RSI"]:.1f}（超买区）', '-1'))
            score -= 1
        else:
            signals.append(('📊', f'RSI = {last["RSI"]:.1f}（中性区间）', '+0'))

    # 5. 收盘相对均线位置
    if not pd.isna(last['MA20']):
        pct_from_ma = (last['收盘'] - last['MA20']) / last['MA20'] * 100
        if -3 < pct_from_ma < 3:
            signals.append(('📊', f'收盘价在 MA20 附近（{pct_from_ma:+.1f}%）', '+0'))
        elif pct_from_ma >= 3:
            signals.append(('⚠️', f'收盘价在 MA20 上方 {pct_from_ma:+.1f}%（偏离较大）', '-1'))
            score -= 1
        else:
            signals.append(('💡', f'收盘价在 MA20 下方 {pct_from_ma:+.1f}%（偏离较大，关注反弹）', '+1'))
            score += 1

    # 综合判定
    if score >= 4:
        conclusion = 'buy'
        label = '📈 建议买入'
        desc = '技术指标整体偏多，短线有上涨动能。可考虑在回调时轻仓介入，设好止损。'
    elif score <= -3:
        conclusion = 'sell'
        label = '📉 建议卖出/观望'
        desc = '技术指标整体偏空，短线风险较大。建议持币观望，不急于抄底。'
    elif score >= 1:
        conclusion = 'buy-weak'
        label = '📊 谨慎看多'
        desc = '部分指标偏多，但信号不够强烈。可小仓位试探，严格止损。'
    elif score <= -1:
        conclusion = 'sell-weak'
        label = '📊 谨慎看空'
        desc = '部分指标偏空，建议减仓或等待更明确的信号。'
    else:
        conclusion = 'neutral'
        label = '⚖️ 中性观望'
        desc = '多空信号均衡，方向不明。建议等待趋势明朗再做决策。'

    return signals, score, conclusion, label, desc


def _run_backtest(df, ma, buy_threshold, tp, sl):
    """隔夜持仓回测核心逻辑"""
    df = df.copy()
    trades = []
    pos = 0  # 持仓状态: 0=空仓, 1=持仓
    buy_price = 0
    entry_date = None
    total_return = 0
    wins = 0
    losses = 0
    max_drawdown = 0
    peak = 1.0
    equity = 1.0

    for i in range(1, len(df)):
        row = df.iloc[i]
        prev = df.iloc[i - 1]
        date = row['日期']

        if pos == 0:
            # 空仓 → 判断买入
            # 条件：今日收盘 < MA, 且今日跌幅 > buy_threshold
            ma_val = prev[f'MA{ma}'] if not pd.isna(prev[f'MA{ma}']) else np.nan
            if pd.isna(ma_val):
                continue
            if row['收盘'] < ma_val:
                decline = (row['收盘'] - prev['收盘']) / prev['收盘']
                if decline < -buy_threshold / 100:
                    pos = 1
                    buy_price = row['收盘']
                    entry_date = date
                    trades.append({
                        'buy_date': date.strftime('%m-%d'),
                        'buy_price': round(buy_price, 2),
                        'sell_date': '',
                        'sell_price': '',
                        'return': '',
                        'result': ''
                    })

        elif pos == 1:
            # 持仓 → 判断卖出（隔夜持仓）
            sell_reason = None
            sell_price = row['开盘']  # 次日开盘卖出

            ret = (sell_price - buy_price) / buy_price * 100

            if ret >= tp:
                sell_reason = f'止盈 (+{tp}%)'
            elif ret <= sl:
                sell_reason = f'止损 ({sl}%)'
            # 如果没有触达止盈止损，也可以按收盘价或次日收盘来卖
            # 这里策略：如果持仓超过5天，按当日收盘强制平仓
            elif (date - entry_date).days >= 5:
                sell_price = row['收盘']
                ret = (sell_price - buy_price) / buy_price * 100
                sell_reason = '持仓超5天强制平仓'
            else:
                # 继续持有到明天再判断
                continue

            # 平仓
            pos = 0
            pf = ret / 100 + 1
            equity *= pf
            peak = max(peak, equity)
            dd = (peak - equity) / peak * 100
            max_drawdown = max(max_drawdown, dd)
            total_return += ret
            if ret > 0:
                wins += 1
            else:
                losses += 1

            trades[-1]['sell_date'] = date.strftime('%m-%d')
            trades[-1]['sell_price'] = round(sell_price, 2)
            trades[-1]['return'] = f'{ret:+.2f}%'
            trades[-1]['result'] = '✅' if ret > 0 else '❌'
            trades[-1]['reason'] = sell_reason

    # 统计
    total_trades = len(trades)
    win_rate = round(wins / total_trades * 100, 1) if total_trades > 0 else 0
    avg_return = round(total_return / total_trades, 2) if total_trades > 0 else 0

    return {
        'trades': trades,
        'total_return': round(total_return, 2),
        'total_trades': total_trades,
        'wins': wins,
        'losses': losses,
        'win_rate': win_rate,
        'avg_return': avg_return,
        'max_drawdown': round(max_drawdown, 2),
        'final_equity': round(equity, 4),
    }


def _make_chart(df, trades):
    """生成 K线 + 均线 + 买卖点图表"""
    df_chart = df.copy()
    df_chart.set_index('日期', inplace=True)

    # 构造 mplfinance 格式
    ohlc = df_chart[['开盘', '最高', '最低', '收盘', '成交量']].copy()
    ohlc.columns = ['Open', 'High', 'Low', 'Close', 'Volume']

    # 买卖点标记
    buy_dates = set()
    sell_dates = set()
    for t in trades:
        try:
            buy_dates.add(t['buy_date'])
            if t.get('sell_date'):
                sell_dates.add(t['sell_date'])
        except:
            pass

    year = df.iloc[-1]['日期'].year
    marker_buy = pd.Series(index=ohlc.index, dtype=float)
    marker_sell = pd.Series(index=ohlc.index, dtype=float)

    for bd_str in buy_dates:
        try:
            dt = pd.Timestamp(f'{year}-{bd_str}')
            if dt in ohlc.index:
                marker_buy.loc[dt] = ohlc.loc[dt, 'Low'] * 0.97
        except:
            pass
    for sd_str in sell_dates:
        try:
            dt = pd.Timestamp(f'{year}-{sd_str}')
            if dt in ohlc.index:
                marker_sell.loc[dt] = ohlc.loc[dt, 'High'] * 1.03
        except:
            pass

    apds = []
    for m in [5, 10, 20]:
        col = f'MA{m}'
        if col in df_chart.columns and df_chart[col].notna().sum() > 0:
            apds.append(mpf.make_addplot(df_chart[col]))

    if marker_buy.notna().any():
        apds.append(mpf.make_addplot(
            marker_buy, type='scatter',
            markersize=120, marker='^', color='red'
        ))

    if marker_sell.notna().any():
        apds.append(mpf.make_addplot(
            marker_sell, type='scatter',
            markersize=120, marker='v', color='green'
        ))

    buf = io.BytesIO()
    style = mpf.make_mpf_style(base_mpf_style='yahoo', rc={
        'font.size': 10,
    })
    fig, axes = mpf.plot(
        ohlc, type='candle', volume=True,
        addplot=apds, style=style,
        figsize=(11, 6), returnfig=True,
        title='', ylabel='价格', ylabel_lower='成交量',
    )
    fig.savefig(buf, format='png', dpi=120, bbox_inches='tight')
    plt.close(fig)
    buf.seek(0)
    return base64.b64encode(buf.read()).decode()


@app.route('/')
def index():
    return render_template_string(HTML)


@app.route('/backtest', methods=['POST'])
def backtest():
    try:
        data = request.get_json()
        code = data['code']
        days = data['days']
        ma = data['ma']
        buy_threshold = data['buy_threshold']
        tp = data['tp']
        sl = data['sl']

        # 1. 获取数据
        df = _get_data(code, days)
        df = _calc_indicators(df)

        # 2. 技术分析信号
        signals, score, conclusion, label, desc = _generate_signal(df)

        # 3. 回测
        backtest_result = _run_backtest(df, ma, buy_threshold, tp, sl)

        # 4. 图表
        chart_b64 = _make_chart(df, backtest_result['trades'])

        # 5. 渲染结果 HTML
        signal_class = {
            'buy': 'signal-buy',
            'sell': 'signal-sell',
            'buy-weak': 'signal-hold',
            'sell-weak': 'signal-hold',
            'neutral': 'signal-neutral',
        }.get(conclusion, 'signal-neutral')

        signals_html = ''.join(
            f'<div style="font-size:13px;padding:3px 0">{s[0]} {s[1]} <span style="color:#999;float:right">{s[2]}</span></div>'
            for s in signals
        )

        trades_html = ''
        for t in backtest_result['trades']:
            tag = 'buy' if t.get('result') == '✅' else 'sell'
            trades_html += f'''<tr>
                <td>{t['buy_date']}</td>
                <td>{t['buy_price']}</td>
                <td>{t['sell_date']}</td>
                <td>{t['sell_price']}</td>
                <td>{t.get('reason', '')}</td>
                <td><span class="tag {tag}">{t['return']}</span></td>
                <td>{t['result']}</td>
            </tr>'''

        ret_color = 'green' if backtest_result['total_return'] > 0 else 'red'
        wr_color = 'green' if backtest_result['win_rate'] >= 50 else 'red'

        html = f'''
        <div class="card">
            <h2 style="margin-bottom:12px">🔍 技术分析 — {code}</h2>
            <div class="signal-box {signal_class}">
                {label}
                <span style="float:right;font-size:14px">综合评分: {score}</span>
            </div>
            <div class="rec-box"><strong>操作建议：</strong>{desc}</div>
            <div style="background:#f9fafb;border-radius:8px;padding:12px;font-size:13px">
                {signals_html}
            </div>
        </div>

        <div class="card">
            <h2 style="margin-bottom:12px">📈 回测结果</h2>
            <div class="kpi-grid">
                <div class="kpi {ret_color}"><div class="val">{backtest_result["total_return"]:+.2f}%</div><div class="lbl">总收益率</div></div>
                <div class="kpi"><div class="val">{backtest_result["total_trades"]}</div><div class="lbl">交易次数</div></div>
                <div class="kpi {wr_color}"><div class="val">{backtest_result["win_rate"]}%</div><div class="lbl">胜率</div></div>
                <div class="kpi green"><div class="val">{backtest_result["wins"]}</div><div class="lbl">盈利次数</div></div>
                <div class="kpi red"><div class="val">{backtest_result["losses"]}</div><div class="lbl">亏损次数</div></div>
                <div class="kpi"><div class="val">{backtest_result["avg_return"]:+.2f}%</div><div class="lbl">平均单笔收益</div></div>
                <div class="kpi red"><div class="val">{backtest_result["max_drawdown"]:.2f}%</div><div class="lbl">最大回撤</div></div>
                <div class="kpi"><div class="val">{backtest_result["final_equity"]}x</div><div class="lbl">最终净值</div></div>
            </div>
            <img src="data:image/png;base64,{chart_b64}" alt="K线图"/>
        </div>

        <div class="card">
            <h2 style="margin-bottom:12px">📋 交易明细</h2>
            <table class="trade-table">
            <thead><tr>
                <th>买入日</th><th>买入价</th><th>卖出日</th><th>卖出价</th><th>平仓原因</th><th>收益率</th><th>结果</th>
            </tr></thead>
            <tbody>{trades_html or '<tr><td colspan="7" style="text-align:center;color:#999">无交易</td></tr>'}</tbody>
            </table>
        </div>
        '''

        return jsonify({'html': html})

    except Exception as e:
        return jsonify({'error': str(e)})


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=6789, debug=True)
