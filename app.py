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
<title>A股短线回测 · 分析推荐</title>
<style>
:root{--bg:#f5f6fa;--card:#fff;--text:#1e293b;--text2:#64748b;--border:#e2e8f0;--accent:#3b82f6;--accent-hover:#2563eb;--green:#10b981;--red:#ef4444;--yellow:#f59e0b;--radius:16px;--shadow:0 1px 3px rgba(0,0,0,.06),0 1px 2px rgba(0,0,0,.04)}
@media(prefers-color-scheme:dark){
:root{--bg:#0f172a;--card:#1e293b;--text:#f1f5f9;--text2:#94a3b8;--border:#334155;--accent:#60a5fa;--accent-hover:#93c5fd;--shadow:0 1px 3px rgba(0,0,0,.2)}
}
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,'Inter','Noto Sans SC',sans-serif;background:var(--bg);color:var(--text);padding:0;transition:background .2s,color .2s}
.container{max-width:1120px;margin:0 auto;padding:32px 20px}
.card{background:var(--card);border-radius:var(--radius);padding:28px;margin-bottom:20px;box-shadow:var(--shadow);border:1px solid var(--border);transition:background .2s,border .2s}
h1{font-size:22px;font-weight:700;letter-spacing:-.3px;display:flex;align-items:center;gap:10px}
h1 span{background:linear-gradient(135deg,#3b82f6,#8b5cf6);-webkit-background-clip:text;-webkit-text-fill-color:transparent}
.sub{color:var(--text2);font-size:13px;margin-top:4px;margin-bottom:20px}
.form-row{display:grid;grid-template-columns:repeat(auto-fill,minmax(130px,1fr));gap:14px;margin-bottom:18px}
.form-group{display:flex;flex-direction:column;gap:5px}
.form-group label{font-size:12px;color:var(--text2);font-weight:600;text-transform:uppercase;letter-spacing:.4px}
.form-group input,.form-group select{padding:9px 12px;background:var(--bg);border:1px solid var(--border);border-radius:10px;font-size:13px;color:var(--text);outline:none;transition:border .15s;-webkit-appearance:none;appearance:none;cursor:pointer}
.form-group input:focus,.form-group select:focus{border-color:var(--accent);box-shadow:0 0 0 3px rgba(59,130,246,.15)}
.btn-group{display:flex;gap:10px;flex-wrap:wrap}
.btn{display:inline-flex;align-items:center;gap:6px;padding:10px 22px;background:var(--accent);color:#fff;border:none;border-radius:10px;font-size:14px;font-weight:600;cursor:pointer;transition:all .15s}
.btn:hover{background:var(--accent-hover);transform:translateY(-1px);box-shadow:0 4px 12px rgba(59,130,246,.3)}
.btn:active{transform:translateY(0)}
.btn:disabled{opacity:.5;cursor:not-allowed;transform:none;box-shadow:none}
.btn-outline{background:transparent;color:var(--accent);border:1px solid var(--accent)}
.btn-outline:hover{background:rgba(59,130,246,.08);box-shadow:none}
.loading{text-align:center;padding:60px 20px;display:none}
.loading-dots{display:inline-flex;gap:6px;margin-bottom:16px}
.loading-dots div{width:10px;height:10px;background:var(--accent);border-radius:50%;animation:bounce 1.2s ease-in-out infinite}
.loading-dots div:nth-child(2){animation-delay:.15s}
.loading-dots div:nth-child(3){animation-delay:.3s}
@keyframes bounce{0%,80%,100%{transform:scale(.6);opacity:.3}40%{transform:scale(1);opacity:1}}
.loading p{color:var(--text2);font-size:14px}
.results{animation:fadeIn .3s ease}
@keyframes fadeIn{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:translateY(0)}}
/* KPI 网格 */
.kpi-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(120px,1fr));gap:10px;margin-bottom:20px}
.kpi{background:var(--bg);border-radius:12px;padding:14px 12px;text-align:center;border:1px solid transparent;transition:border .2s}
.kpi .val{font-size:20px;font-weight:700;line-height:1.3}
.kpi .lbl{font-size:11px;color:var(--text2);margin-top:3px;font-weight:500}
.kpi.green .val{color:var(--green)}
.kpi.red .val{color:var(--red)}
/* 信号 */
.signal-box{padding:16px 20px;border-radius:12px;margin-bottom:16px;font-size:15px;font-weight:600;display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:8px}
.signal-buy{background:rgba(16,185,129,.1);color:var(--green);border:1px solid rgba(16,185,129,.2)}
.signal-sell{background:rgba(239,68,68,.1);color:var(--red);border:1px solid rgba(239,68,68,.2)}
.signal-hold{background:rgba(245,158,11,.1);color:var(--yellow);border:1px solid rgba(245,158,11,.2)}
.signal-neutral{background:rgba(100,116,139,.08);color:var(--text2);border:1px solid var(--border)}
.signal-box span.score{font-size:13px;font-weight:500;opacity:.8}
.rec-box{background:rgba(59,130,246,.06);border:1px solid rgba(59,130,246,.15);border-radius:10px;padding:14px 18px;margin-bottom:16px;font-size:13px;line-height:1.7}
.rec-box strong{color:var(--accent)}
.signals-list{background:var(--bg);border-radius:10px;padding:12px 16px;font-size:13px;border:1px solid var(--border)}
.signals-list div{padding:4px 0;display:flex;justify-content:space-between;align-items:center}
.signals-list .pts{color:var(--text2);font-size:11px}
/* 图表 */
img.chart-img{max-width:100%;border-radius:10px;margin-top:14px;display:block;border:1px solid var(--border)}
/* 表格 */
.trade-table{width:100%;border-collapse:separate;border-spacing:0;font-size:13px;margin-top:14px}
.trade-table th{padding:10px 12px;text-align:left;font-weight:600;color:var(--text2);font-size:11px;text-transform:uppercase;letter-spacing:.4px;background:var(--bg);border-bottom:1px solid var(--border)}
.trade-table th:first-child{border-radius:10px 0 0 0}
.trade-table th:last-child{border-radius:0 10px 0 0}
.trade-table td{padding:10px 12px;border-bottom:1px solid var(--border);transition:background .1s}
.trade-table tr:last-child td:first-child{border-radius:0 0 0 10px}
.trade-table tr:last-child td:last-child{border-radius:0 0 10px 0}
.trade-table tr:hover td{background:rgba(59,130,246,.03)}
.tag{display:inline-block;padding:2px 8px;border-radius:6px;font-size:11px;font-weight:600}
.tag.buy{background:rgba(16,185,129,.12);color:var(--green)}
.tag.sell{background:rgba(239,68,68,.12);color:var(--red)}
/* 策略选择器tab */
.strategy-tabs{display:flex;gap:0;margin-bottom:0;overflow-x:auto;border-bottom:1px solid var(--border)}
.strategy-tab{padding:10px 18px;font-size:13px;font-weight:500;color:var(--text2);cursor:pointer;border-bottom:2px solid transparent;transition:all .15s;white-space:nowrap}
.strategy-tab:hover{color:var(--text)}
.strategy-tab.active{color:var(--accent);border-bottom-color:var(--accent)}
/* 策略对比卡片 */
.compare-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(240px,1fr));gap:12px;margin-bottom:20px}
.compare-card{background:var(--bg);border-radius:12px;padding:18px;border:1px solid var(--border);transition:border .15s}
.compare-card:hover{border-color:var(--accent)}
.compare-card .name{font-size:14px;font-weight:600;margin-bottom:6px}
.compare-card .stat{display:flex;justify-content:space-between;padding:4px 0;font-size:12px;border-bottom:1px solid rgba(0,0,0,.04)}
.compare-card .stat:last-child{border:none}
.compare-card .stat .l{color:var(--text2)}
.compare-card .stat .r{font-weight:600}
.compare-card.best{border-color:var(--accent);background:rgba(59,130,246,.04)}
.compare-card.best .name{color:var(--accent)}
.compare-card .rank{display:inline-block;padding:1px 7px;border-radius:6px;font-size:11px;font-weight:700;margin-bottom:6px}
.rank-1{background:linear-gradient(135deg,#fbbf24,#f59e0b);color:#fff}
.rank-2{background:linear-gradient(135deg,#94a3b8,#64748b);color:#fff}
.rank-3{background:linear-gradient(135deg,#d97706,#b45309);color:#fff}
/* 高级折叠参数 */
.params-advanced{display:none;margin-top:12px;padding:16px;background:var(--bg);border-radius:10px;border:1px solid var(--border)}
.params-advanced.open{display:block}
.params-toggle{font-size:12px;color:var(--accent);cursor:pointer;display:inline-flex;align-items:center;gap:4px;margin-top:10px;user-select:none}
.params-toggle:hover{opacity:.8}
/* 响应式 */
@media(max-width:640px){
.container{padding:16px 12px}
.card{padding:20px 16px}
.form-row{grid-template-columns:repeat(2,1fr);gap:10px}
.kpi-grid{grid-template-columns:repeat(3,1fr);gap:8px}
.compare-grid{grid-template-columns:1fr}
.strategy-tabs{font-size:12px}
.strategy-tab{padding:8px 12px}
}
</style>
</head>
<body>
<div class="container">
<div class="card">
<h1><span>A股短线回测</span><span style="font-size:12px;background:var(--bg);padding:2px 10px;border-radius:6px;color:var(--text2);font-weight:400;-webkit-text-fill-color:var(--text2)">v2</span></h1>
<p class="sub">多策略回测 · 技术分析 · 参数调优 · 免费数据</p>
<form id="form" onsubmit="run(event)">
<div class="form-row">
<div class="form-group">
<label>股票代码</label>
<input type="text" id="code" value="000001" placeholder="000001" style="max-width:120px">
</div>
<div class="form-group">
<label>回测周期</label>
<select id="days">
<option value="60">60天</option>
<option value="120" selected>120天</option>
<option value="250">250天</option>
</select>
</div>
<div class="form-group">
<label>策略</label>
<select id="strategy">
<option value="all" selected>🏆 全部对比</option>
<option value="mean_reversion">📉 隔夜持仓</option>
<option value="golden_cross">📈 金叉死叉</option>
<option value="volume_breakout">🚀 放量突破</option>
<option value="composite">🎯 综合评分</option>
</select>
</div>
<div class="form-group">
<label>均线</label>
<select id="ma">
<option value="5">MA5</option>
<option value="10" selected>MA10</option>
<option value="20">MA20</option>
</select>
</div>
<div class="form-group">
<label>止盈</label>
<select id="tp">
<option value="3">+3%</option>
<option value="5" selected>+5%</option>
<option value="8">+8%</option>
<option value="10">+10%</option>
</select>
</div>
<div class="form-group">
<label>止损</label>
<select id="sl">
<option value="-2">-2%</option>
<option value="-3" selected>-3%</option>
<option value="-5">-5%</option>
</select>
</div>
</div>
<div style="display:flex;align-items:center;gap:12px;flex-wrap:wrap">
<button type="submit" class="btn" id="runBtn">运行回测</button>
<span class="params-toggle" onclick="toggleParams()">⚙️ 高级参数</span>
</div>
<div class="params-advanced" id="paramsAdvanced">
<div class="form-row" style="margin-bottom:0">
<div class="form-group">
<label>买入阈值</label>
<select id="buy_threshold">
<option value="0.5">>0.5%</option>
<option value="1.0" selected>>1.0%</option>
<option value="2.0">>2.0%</option>
<option value="3.0">>3.0%</option>
</select>
</div>
<div class="form-group">
<label>持仓上限(天)</label>
<select id="hold_days">
<option value="3">3天</option>
<option value="5" selected>5天</option>
<option value="10">10天</option>
<option value="20">20天</option>
</select>
</div>
</div>
</div>
</form>
</div>

<div class="loading" id="loading">
<div class="loading-dots"><div></div><div></div><div></div></div>
<p>正在获取数据并分析...</p>
</div>

<div id="results"></div>
</div>

<script>
function toggleParams(){document.getElementById('paramsAdvanced').classList.toggle('open')}
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
strategy:document.getElementById('strategy').value,
ma:parseInt(document.getElementById('ma').value),
buy_threshold:parseFloat(document.getElementById('buy_threshold').value),
tp:parseFloat(document.getElementById('tp').value),
sl:parseFloat(document.getElementById('sl').value),
hold_days:parseInt(document.getElementById('hold_days').value)
})
});
const data=await r.json();
if(data.error){results.innerHTML='<div class="card" style="color:var(--red)"><strong>错误</strong> '+data.error+'</div>';return;}
results.innerHTML=data.html;
}catch(e){results.innerHTML='<div class="card" style="color:var(--red)"><strong>请求失败</strong> '+e.message+'</div>';}
finally{btn.disabled=false;loading.style.display='none';}
}
// Tab 切换：事件委托（在 results 容器上监听，innerHTML 注入后依然生效）
document.getElementById('results').addEventListener('click', function(e){
var tab = e.target.closest('.strategy-tab');
if(tab && tab.getAttribute('data-key')){
var key = tab.getAttribute('data-key');
document.querySelectorAll('.strategy-tab').forEach(function(t){t.classList.remove('active')});
document.querySelectorAll('.strategy-panel').forEach(function(p){p.style.display='none'});
tab.classList.add('active');
var panel = document.getElementById('panel-'+key);
if(panel) panel.style.display='block';
}
});
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


def _run_backtest(df, strategy, ma, buy_threshold, tp, sl):
    """回测核心逻辑，支持多种策略

    策略:
    - 'mean_reversion': 隔夜持仓（收盘跌破MA买入，止盈止损/5天强平）
    - 'golden_cross': 金叉死叉（MA5上穿MA10买入，下穿卖出）
    """
    df = df.copy()
    trades = []
    pos = 0
    buy_price = 0
    entry_date = None
    total_return = 0
    wins = 0
    losses = 0
    max_drawdown = 0
    peak = 1.0
    equity = 1.0
    # 记录每日净值用于画资金曲线
    equity_curve = []

    if strategy == 'golden_cross':
        # ── 金叉死叉策略 ──
        # 买入：MA5 上穿 MA10（今日MA5>MA10 且 昨日MA5<=MA10）
        # 卖出：MA5 下穿 MA10（今日MA5<MA10 且 昨日MA5>=MA10）
        for i in range(1, len(df)):
            row = df.iloc[i]
            prev = df.iloc[i - 1]
            date = row['日期']

            ma5_curr = row['MA5'] if not pd.isna(row['MA5']) else np.nan
            ma10_curr = row['MA10'] if not pd.isna(row['MA10']) else np.nan
            ma5_prev = prev['MA5'] if not pd.isna(prev['MA5']) else np.nan
            ma10_prev = prev['MA10'] if not pd.isna(prev['MA10']) else np.nan

            if any(pd.isna(x) for x in [ma5_curr, ma10_curr, ma5_prev, ma10_prev]):
                equity_curve.append(equity)
                continue

            # 金叉买入
            if pos == 0 and ma5_prev <= ma10_prev and ma5_curr > ma10_curr:
                pos = 1
                buy_price = row['收盘']
                entry_date = date
                trades.append({
                    'buy_date': date.strftime('%m-%d'),
                    'buy_price': round(buy_price, 2),
                    'sell_date': '', 'sell_price': '',
                    'return': '', 'result': ''
                })

            # 死叉卖出
            elif pos == 1 and ma5_prev >= ma10_prev and ma5_curr < ma10_curr:
                sell_price = row['收盘']
                ret = (sell_price - buy_price) / buy_price * 100
                pos = 0
                pf = ret / 100 + 1
                equity *= pf
                peak = max(peak, equity)
                dd = (peak - equity) / peak * 100
                max_drawdown = max(max_drawdown, dd)
                total_return += ret
                if ret > 0: wins += 1
                else: losses += 1
                trades[-1]['sell_date'] = date.strftime('%m-%d')
                trades[-1]['sell_price'] = round(sell_price, 2)
                trades[-1]['return'] = f'{ret:+.2f}%'
                trades[-1]['result'] = '✅' if ret > 0 else '❌'
                trades[-1]['reason'] = '死叉卖出'

            # 止盈止损（金叉也支持）
            elif pos == 1:
                sell_price = row['开盘']
                ret = (sell_price - buy_price) / buy_price * 100
                if ret >= tp:
                    pos = 0
                    pf = ret / 100 + 1
                    equity *= pf
                    peak = max(peak, equity)
                    dd = (peak - equity) / peak * 100
                    max_drawdown = max(max_drawdown, dd)
                    total_return += ret
                    wins += 1
                    trades[-1]['sell_date'] = date.strftime('%m-%d')
                    trades[-1]['sell_price'] = round(sell_price, 2)
                    trades[-1]['return'] = f'{ret:+.2f}%'
                    trades[-1]['result'] = '✅'
                    trades[-1]['reason'] = f'止盈 (+{tp}%)'
                elif ret <= sl:
                    pos = 0
                    pf = ret / 100 + 1
                    equity *= pf
                    peak = max(peak, equity)
                    dd = (peak - equity) / peak * 100
                    max_drawdown = max(max_drawdown, dd)
                    total_return += ret
                    losses += 1
                    trades[-1]['sell_date'] = date.strftime('%m-%d')
                    trades[-1]['sell_price'] = round(sell_price, 2)
                    trades[-1]['return'] = f'{ret:+.2f}%'
                    trades[-1]['result'] = '❌'
                    trades[-1]['reason'] = f'止损 ({sl}%)'

            equity_curve.append(equity)

        # 如果最后一个交易日后还持仓，收盘平仓
        if pos == 1:
            last_row = df.iloc[-1]
            sell_price = last_row['收盘']
            ret = (sell_price - buy_price) / buy_price * 100
            pf = ret / 100 + 1
            equity *= pf
            total_return += ret
            if ret > 0: wins += 1
            else: losses += 1
            trades[-1]['sell_date'] = last_row['日期'].strftime('%m-%d')
            trades[-1]['sell_price'] = round(sell_price, 2)
            trades[-1]['return'] = f'{ret:+.2f}%'
            trades[-1]['result'] = '✅' if ret > 0 else '❌'
            trades[-1]['reason'] = '期末平仓'

    elif strategy == 'volume_breakout':
        # ── 放量突破策略 ──
        # 买入：成交量放量 + 收盘突破MA20 + 涨幅达标
        #       量比阈值默认1.5x，涨幅阈值默认1.5%
        vol_mult = 1.5  # 放量倍数
        min_pct = 1.5   # 最低涨幅
        for i in range(2, len(df)):
            row = df.iloc[i]
            prev = df.iloc[i - 1]
            date = row['日期']

            if pos == 0:
                vol_ma5 = row['VOL_MA5'] if not pd.isna(row['VOL_MA5']) else np.nan
                ma20 = row['MA20'] if not pd.isna(row['MA20']) else np.nan
                prev_ma20 = prev['MA20'] if not pd.isna(prev['MA20']) else np.nan
                if any(pd.isna(x) for x in [vol_ma5, ma20, prev_ma20]):
                    equity_curve.append(equity)
                    continue

                vol_ratio = row['成交量'] / vol_ma5
                pct_change = (row['收盘'] - prev['收盘']) / prev['收盘'] * 100

                # 突破条件：放量+突破MA20+涨幅达标
                if (vol_ratio >= vol_mult and
                    row['收盘'] > ma20 and prev['收盘'] <= prev_ma20 and
                    pct_change > min_pct):

                    pos = 1
                    buy_price = row['收盘']
                    entry_date = date
                    trades.append({
                        'buy_date': date.strftime('%m-%d'),
                        'buy_price': round(buy_price, 2),
                        'sell_date': '', 'sell_price': '',
                        'return': '', 'result': ''
                    })

            elif pos == 1:
                # 跌破MA20卖出
                ma20_curr = row['MA20'] if not pd.isna(row['MA20']) else np.nan
                if not pd.isna(ma20_curr) and row['收盘'] < ma20_curr:
                    sell_price = row['收盘']
                    ret = (sell_price - buy_price) / buy_price * 100
                    pos = 0
                    pf = ret / 100 + 1
                    equity *= pf
                    peak = max(peak, equity)
                    dd = (peak - equity) / peak * 100
                    max_drawdown = max(max_drawdown, dd)
                    total_return += ret
                    if ret > 0: wins += 1
                    else: losses += 1
                    trades[-1]['sell_date'] = date.strftime('%m-%d')
                    trades[-1]['sell_price'] = round(sell_price, 2)
                    trades[-1]['return'] = f'{ret:+.2f}%'
                    trades[-1]['result'] = '✅' if ret > 0 else '❌'
                    trades[-1]['reason'] = '跌破MA20卖出'
                else:
                    # 止盈止损（按开盘价）
                    sell_price = row['开盘']
                    ret = (sell_price - buy_price) / buy_price * 100
                    if ret >= tp:
                        pos = 0
                        pf = ret / 100 + 1
                        equity *= pf
                        peak = max(peak, equity)
                        dd = (peak - equity) / peak * 100
                        max_drawdown = max(max_drawdown, dd)
                        total_return += ret
                        wins += 1
                        trades[-1]['sell_date'] = date.strftime('%m-%d')
                        trades[-1]['sell_price'] = round(sell_price, 2)
                        trades[-1]['return'] = f'{ret:+.2f}%'
                        trades[-1]['result'] = '✅'
                        trades[-1]['reason'] = f'止盈 (+{tp}%)'
                    elif ret <= sl:
                        pos = 0
                        pf = ret / 100 + 1
                        equity *= pf
                        peak = max(peak, equity)
                        dd = (peak - equity) / peak * 100
                        max_drawdown = max(max_drawdown, dd)
                        total_return += ret
                        losses += 1
                        trades[-1]['sell_date'] = date.strftime('%m-%d')
                        trades[-1]['sell_price'] = round(sell_price, 2)
                        trades[-1]['return'] = f'{ret:+.2f}%'
                        trades[-1]['result'] = '❌'
                        trades[-1]['reason'] = f'止损 ({sl}%)'

            equity_curve.append(equity)

        # 期末平仓
        if pos == 1 and trades:
            last_row = df.iloc[-1]
            sell_price = last_row['收盘']
            ret = (sell_price - buy_price) / buy_price * 100
            pf = ret / 100 + 1
            equity *= pf
            total_return += ret
            if ret > 0: wins += 1
            else: losses += 1
            trades[-1]['sell_date'] = last_row['日期'].strftime('%m-%d')
            trades[-1]['sell_price'] = round(sell_price, 2)
            trades[-1]['return'] = f'{ret:+.2f}%'
            trades[-1]['result'] = '✅' if ret > 0 else '❌'
            trades[-1]['reason'] = '期末平仓'

    else:
        # ── 隔夜持仓策略（原逻辑） ──
        for i in range(1, len(df)):
            row = df.iloc[i]
            prev = df.iloc[i - 1]
            date = row['日期']

            if pos == 0:
                ma_val = prev[f'MA{ma}'] if not pd.isna(prev[f'MA{ma}']) else np.nan
                if pd.isna(ma_val):
                    equity_curve.append(equity)
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
                            'sell_date': '', 'sell_price': '',
                            'return': '', 'result': ''
                        })

            elif pos == 1:
                sell_reason = None
                sell_price = row['开盘']
                ret = (sell_price - buy_price) / buy_price * 100

                if ret >= tp:
                    sell_reason = f'止盈 (+{tp}%)'
                elif ret <= sl:
                    sell_reason = f'止损 ({sl}%)'
                elif (date - entry_date).days >= 5:
                    sell_price = row['收盘']
                    ret = (sell_price - buy_price) / buy_price * 100
                    sell_reason = '持仓超5天强制平仓'
                else:
                    equity_curve.append(equity)
                    continue

                pos = 0
                pf = ret / 100 + 1
                equity *= pf
                peak = max(peak, equity)
                dd = (peak - equity) / peak * 100
                max_drawdown = max(max_drawdown, dd)
                total_return += ret
                if ret > 0: wins += 1
                else: losses += 1

                trades[-1]['sell_date'] = date.strftime('%m-%d')
                trades[-1]['sell_price'] = round(sell_price, 2)
                trades[-1]['return'] = f'{ret:+.2f}%'
                trades[-1]['result'] = '✅' if ret > 0 else '❌'
                trades[-1]['reason'] = sell_reason or ''

            equity_curve.append(equity)

    # 计算风险指标
    total_trades = len(trades)
    win_rate = round(wins / total_trades * 100, 1) if total_trades > 0 else 0
    avg_return = round(total_return / total_trades, 2) if total_trades > 0 else 0
    avg_win = sum(float(t['return'].replace('%','')) for t in trades if '✅' in str(t.get('result',''))) / max(wins, 1)
    avg_loss = sum(float(t['return'].replace('%','')) for t in trades if '❌' in str(t.get('result',''))) / max(losses, 1)
    profit_loss_ratio = round(abs(avg_win / avg_loss), 2) if avg_loss != 0 else 0

    # 夏普比率 (年化)
    equity_series = pd.Series(equity_curve)
    daily_returns = equity_series.pct_change().dropna()
    if len(daily_returns) > 0 and daily_returns.std() != 0:
        sharpe = round(daily_returns.mean() / daily_returns.std() * (252 ** 0.5), 2)
    else:
        sharpe = 0.0

    # 最大连续亏损
    max_consec_losses = 0
    cur_consec = 0
    for t in trades:
        if '❌' in str(t.get('result','')):
            cur_consec += 1
            max_consec_losses = max(max_consec_losses, cur_consec)
        else:
            cur_consec = 0

    return {
        'trades': trades,
        'total_return': round(total_return, 2),
        'total_trades': total_trades,
        'wins': wins,
        'losses': losses,
        'win_rate': win_rate,
        'avg_return': avg_return,
        'avg_win': round(avg_win, 2),
        'avg_loss': round(avg_loss, 2),
        'profit_loss_ratio': profit_loss_ratio,
        'sharpe': sharpe,
        'max_drawdown': round(max_drawdown, 2),
        'max_consec_losses': max_consec_losses,
        'final_equity': round(equity, 4),
        'equity_curve': [round(e, 4) for e in equity_curve],
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


def _make_equity_chart(equity_curve):
    """生成资金曲线图"""
    fig, ax = plt.subplots(figsize=(11, 4))
    ax.plot(equity_curve, color='#2563eb', linewidth=1.5, label='策略净值')
    ax.axhline(y=1.0, color='#ccc', linestyle='--', linewidth=0.8, label='基准 1.0')
    ax.fill_between(range(len(equity_curve)), 1.0, equity_curve,
                    where=[e >= 1.0 for e in equity_curve],
                    color='#22c55e', alpha=0.15)
    ax.fill_between(range(len(equity_curve)), 1.0, equity_curve,
                    where=[e < 1.0 for e in equity_curve],
                    color='#ef4444', alpha=0.1)
    ax.set_ylabel('净值', fontsize=11)
    ax.set_xlabel('交易日', fontsize=11)
    ax.legend(loc='upper left', fontsize=10)
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    buf = io.BytesIO()
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
        strategy = data.get('strategy', 'mean_reversion')
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
        backtest_result = _run_backtest(df, strategy, ma, buy_threshold, tp, sl)

        # 4. 图表：K线 + 资金曲线
        chart_b64 = _make_chart(df, backtest_result['trades'])
        equity_chart_b64 = _make_equity_chart(backtest_result['equity_curve'])

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
            # 查找当日成交量
            vol_str = ''
            try:
                buy_dt = f"{df.iloc[-1]['日期'].year}-{t['buy_date']}"
                buy_idx = df[df['日期'] == pd.Timestamp(buy_dt)].index
                if len(buy_idx) > 0:
                    vol = df.loc[buy_idx[0], '成交量']
                    vol_str = f'{vol/10000:.0f}万' if vol < 1e8 else f'{vol/1e8:.1f}亿'
            except:
                pass
            trades_html += f'''<tr>
                <td>{t['buy_date']}</td>
                <td>{t['buy_price']}</td>
                <td>{t['sell_date']}</td>
                <td>{t['sell_price']}</td>
                <td>{vol_str}</td>
                <td>{t.get('reason', '')}</td>
                <td><span class="tag {tag}">{t['return']}</span></td>
                <td>{t['result']}</td>
            </tr>'''

        ret_color = 'green' if backtest_result['total_return'] > 0 else 'red'
        wr_color = 'green' if backtest_result['win_rate'] >= 50 else 'red'
        sr_color = 'green' if backtest_result['sharpe'] >= 1 else 'red'

        strategy_name = '隔夜持仓' if strategy == 'mean_reversion' else ('金叉死叉' if strategy == 'golden_cross' else '放量突破')

        # ── 构建最终 HTML ──
        parts = []

        # 技术分析卡片（所有模式都一样）
        parts.append(f'''
        <div class="card results">
            <h2 style="font-size:16px;font-weight:600;margin-bottom:14px;color:var(--accent)">技术分析 · {code}</h2>
            <div class="signal-box {signal_class}">
                {label}
                <span class="score">评分: {score}</span>
            </div>
            <div class="rec-box"><strong>操作建议</strong> {desc}</div>
            <div class="signals-list">
                {signals_html}
            </div>
        </div>''')

        if strategy == 'all':
            # ── 全策略对比模式 ──
            strategies = [
                ('mean_reversion', '隔夜持仓'),
                ('golden_cross', '金叉死叉'),
                ('volume_breakout', '放量突破'),
                ('composite', '综合评分'),
            ]
            all_results = []
            for sk, sn in strategies:
                sr = _run_backtest(df, sk, ma, buy_threshold, tp, sl)
                schart = _make_chart(df, sr['trades'])
                sequity_chart = _make_equity_chart(sr['equity_curve'])

                sret_color = 'green' if sr['total_return'] > 0 else 'red'
                swr_color = 'green' if sr['win_rate'] >= 50 else 'red'
                ssr_color = 'green' if sr['sharpe'] >= 1 else 'red'

                strades_html = ''
                for t in sr['trades']:
                    stag = 'buy' if t.get('result') == '✅' else 'sell'
                    strades_html += f'''<tr>
                <td>{t['buy_date']}</td>
                <td>{t['buy_price']}</td>
                <td>{t['sell_date']}</td>
                <td>{t['sell_price']}</td>
                <td>{t.get('reason', '')}</td>
                <td><span class="tag {stag}">{t['return']}</span></td>
                <td>{t['result']}</td>
            </tr>'''

                panel_html = f'''
        <div class="card results">
            <div class="kpi-grid">
                <div class="kpi {sret_color}"><div class="val">{sr["total_return"]:+.2f}%</div><div class="lbl">总收益率</div></div>
                <div class="kpi"><div class="val">{sr["total_trades"]}</div><div class="lbl">交易次数</div></div>
                <div class="kpi {swr_color}"><div class="val">{sr["win_rate"]}%</div><div class="lbl">胜率</div></div>
                <div class="kpi green"><div class="val">{sr["wins"]}</div><div class="lbl">盈利</div></div>
                <div class="kpi red"><div class="val">{sr["losses"]}</div><div class="lbl">亏损</div></div>
                <div class="kpi"><div class="val">{sr["avg_return"]:+.2f}%</div><div class="lbl">平均单笔</div></div>
                <div class="kpi"><div class="val">{sr["avg_win"]:+.2f}%</div><div class="lbl">平均盈利</div></div>
                <div class="kpi red"><div class="val">{sr["avg_loss"]:+.2f}%</div><div class="lbl">平均亏损</div></div>
                <div class="kpi green"><div class="val">{sr["profit_loss_ratio"]}</div><div class="lbl">盈亏比</div></div>
                <div class="kpi red"><div class="val">{sr["max_drawdown"]:.2f}%</div><div class="lbl">最大回撤</div></div>
                <div class="kpi {ssr_color}"><div class="val">{sr["sharpe"]}</div><div class="lbl">夏普比率</div></div>
                <div class="kpi red"><div class="val">{sr["max_consec_losses"]}</div><div class="lbl">最大连亏</div></div>
                <div class="kpi"><div class="val">{sr["final_equity"]}x</div><div class="lbl">最终净值</div></div>
            </div>
            <img class="chart-img" src="data:image/png;base64,{schart}" alt="K线图"/>
            <img class="chart-img" src="data:image/png;base64,{sequity_chart}" alt="资金曲线图"/>
        </div>
        <div class="card results">
            <h2 style="font-size:16px;font-weight:600;margin-bottom:14px;color:var(--accent)">交易明细</h2>
            <table class="trade-table">
            <thead><tr>
                <th>买入日</th><th>买入价</th><th>卖出日</th><th>卖出价</th><th>原因</th><th>收益率</th><th>结果</th>
            </tr></thead>
            <tbody>{strades_html or '<tr><td colspan="7" style="text-align:center;color:var(--text2);padding:30px">无交易</td></tr>'}</tbody>
            </table>
        </div>'''

                all_results.append({
                    'key': sk, 'name': sn, 'result': sr, 'html': panel_html,
                })

            # 排序对比卡片
            sorted_results = sorted(all_results, key=lambda x: x['result']['total_return'], reverse=True)
            rankings = ['🥇', '🥈', '🥉']
            compare_cards = ''
            for rank_i, item in enumerate(sorted_results):
                sname = item['name']
                sr = item['result']
                best_cls = 'best' if rank_i == 0 else ''
                rank_badge = 'rank-1' if rank_i == 0 else ('rank-2' if rank_i == 1 else 'rank-3')
                rc = 'green' if sr['total_return'] > 0 else 'red'
                wc = 'green' if sr['win_rate'] >= 50 else 'red'
                sc = 'green' if sr['sharpe'] >= 1 else 'red'
                rank_label = rankings[rank_i] if rank_i < 3 else f'#{rank_i + 1}'
                compare_cards += f'''
            <div class="compare-card {best_cls}">
                <div class="rank {rank_badge}">{rank_label}</div>
                <div class="name">{sname}策略</div>
                <div class="stat"><span class="l">收益率</span><span class="r {rc}">{sr["total_return"]:+.2f}%</span></div>
                <div class="stat"><span class="l">胜率</span><span class="r {wc}">{sr["win_rate"]}%</span></div>
                <div class="stat"><span class="l">交易</span><span class="r">{sr["total_trades"]}笔</span></div>
                <div class="stat"><span class="l">夏普</span><span class="r {sc}">{sr["sharpe"]}</span></div>
                <div class="stat"><span class="l">最大回撤</span><span class="l" style="color:var(--red)">{sr["max_drawdown"]:.1f}%</span></div>
            </div>'''

            strategy_tabs = ''.join(
                f'<div class="strategy-tab{" active" if i == 0 else ""}" data-key="{s["key"]}">{s["name"]}</div>'
                for i, s in enumerate(all_results)
            )
            strategy_panels = ''.join(
                f'<div class="strategy-panel" id="panel-{s["key"]}" style="display:{"block" if i == 0 else "none"}">{s["html"]}</div>'
                for i, s in enumerate(all_results)
            )

            # 构建 switchTab JS（用普通字符串避免三引号冲突）
            delegate_js = '''<script>
(function(){
    var r = document.getElementById('results');
    if(!r) return;
    r.addEventListener('click', function(e){
        var tab = e.target.closest('.strategy-tab');
        if(!tab || !tab.getAttribute('data-key')) return;
        var key = tab.getAttribute('data-key');
        document.querySelectorAll('.strategy-tab').forEach(function(t){t.classList.remove('active')});
        document.querySelectorAll('.strategy-panel').forEach(function(p){p.style.display='none'});
        tab.classList.add('active');
        var panel = document.getElementById('panel-'+key);
        if(panel) panel.style.display='block';
    });
})();
</script>'''

            parts.append(f'''
        <div class="card results">
            <h2 style="font-size:16px;font-weight:600;margin-bottom:14px;color:var(--accent)">策略对比</h2>
            <div class="compare-grid">{compare_cards}</div>
        </div>
        <div class="card results" style="padding-bottom:0">
            <div class="strategy-tabs">{strategy_tabs}</div>
        </div>
        {strategy_panels}
        {delegate_js}''')
        else:
            # ── 单策略模式 ──
            parts.append(f'''
        <div class="card results">
            <div class="kpi-grid">
                <div class="kpi {ret_color}"><div class="val">{backtest_result["total_return"]:+.2f}%</div><div class="lbl">总收益率</div></div>
                <div class="kpi"><div class="val">{backtest_result["total_trades"]}</div><div class="lbl">交易次数</div></div>
                <div class="kpi {wr_color}"><div class="val">{backtest_result["win_rate"]}%</div><div class="lbl">胜率</div></div>
                <div class="kpi green"><div class="val">{backtest_result["wins"]}</div><div class="lbl">盈利</div></div>
                <div class="kpi red"><div class="val">{backtest_result["losses"]}</div><div class="lbl">亏损</div></div>
                <div class="kpi"><div class="val">{backtest_result["avg_return"]:+.2f}%</div><div class="lbl">平均单笔</div></div>
                <div class="kpi"><div class="val">{backtest_result["avg_win"]:+.2f}%</div><div class="lbl">平均盈利</div></div>
                <div class="kpi red"><div class="val">{backtest_result["avg_loss"]:+.2f}%</div><div class="lbl">平均亏损</div></div>
                <div class="kpi green"><div class="val">{backtest_result["profit_loss_ratio"]}</div><div class="lbl">盈亏比</div></div>
                <div class="kpi red"><div class="val">{backtest_result["max_drawdown"]:.2f}%</div><div class="lbl">最大回撤</div></div>
                <div class="kpi {sr_color}"><div class="val">{backtest_result["sharpe"]}</div><div class="lbl">夏普比率</div></div>
                <div class="kpi red"><div class="val">{backtest_result["max_consec_losses"]}</div><div class="lbl">最大连亏</div></div>
                <div class="kpi"><div class="val">{backtest_result["final_equity"]}x</div><div class="lbl">最终净值</div></div>
            </div>
            <img class="chart-img" src="data:image/png;base64,{chart_b64}" alt="K线图"/>
            <img class="chart-img" src="data:image/png;base64,{equity_chart_b64}" alt="资金曲线图"/>
        </div>
        <div class="card results">
            <h2 style="font-size:16px;font-weight:600;margin-bottom:14px;color:var(--accent)">交易明细</h2>
            <table class="trade-table">
            <thead><tr>
                <th>买入日</th><th>买入价</th><th>卖出日</th><th>卖出价</th><th>买入量</th><th>原因</th><th>收益率</th><th>结果</th>
            </tr></thead>
            <tbody>{trades_html or '<tr><td colspan="8" style="text-align:center;color:var(--text2);padding:30px">无交易</td></tr>'}</tbody>
            </table>
        </div>''')

        html = ''.join(parts)

        return jsonify({'html': html})

    except Exception as e:
        return jsonify({'error': str(e)})


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=6789, debug=True)
