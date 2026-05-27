#!/usr/bin/env python3
"""批量验证回测数据准确性 - 带完整输出"""
import sys
import baostock as bs
import pandas as pd
import numpy as np

stocks = {
    '000001': '平安银行',
    '600519': '贵州茅台',
    '000858': '五粮液',
    '600036': '招商银行',
    '002594': '比亚迪',
}

def get_data(code):
    lg = bs.login()
    code = code.zfill(6)
    bs_code = f'sh.{code}' if code.startswith('6') else f'sz.{code}'
    rs = bs.query_history_k_data_plus(
        bs_code, 'date,open,high,low,close,volume',
        start_date='2026-01-01', end_date='2026-05-26',
        frequency='d', adjustflag='2')
    rows = []
    while rs.next():
        rows.append(rs.get_row_data())
    bs.logout()
    if not rows:
        return None
    df = pd.DataFrame(rows, columns=['日期','开盘','最高','最低','收盘','成交量'])
    for c in ['开盘','最高','最低','收盘']:
        df[c] = df[c].astype(float)
    df['日期'] = pd.to_datetime(df['日期'])
    df.sort_values('日期', inplace=True)
    df.reset_index(drop=True, inplace=True)
    for m in [5, 10, 20]:
        df[f'MA{m}'] = df['收盘'].rolling(m).mean()
    df['涨跌幅'] = df['收盘'].pct_change() * 100
    return df

def bt_mean_reversion(df, ma=10, buy_thresh=1.0, tp=5, sl=-3):
    trades = []
    pos = 0
    for i in range(1, len(df)):
        row, prev = df.iloc[i], df.iloc[i-1]
        if pos == 0:
            ma_val = prev[f'MA{ma}']
            if pd.isna(ma_val):
                continue
            decline = (row['收盘'] - prev['收盘']) / prev['收盘'] * 100
            if row['收盘'] < ma_val and decline < -buy_thresh:
                pos = 1
                trades.append({'buy_date':row['日期'], 'buy_price':row['收盘'], 'entry_date':row['日期']})
        else:
            t = trades[-1]
            sell_price = row['开盘']
            ret = (sell_price - t['buy_price']) / t['buy_price'] * 100
            if ret >= tp:
                pos = 0
                t['sell_date'] = row['日期']; t['sell_price'] = round(sell_price, 2)
                t['return_pct'] = round(ret, 2); t['reason'] = '止盈'
            elif ret <= sl:
                pos = 0
                t['sell_date'] = row['日期']; t['sell_price'] = round(sell_price, 2)
                t['return_pct'] = round(ret, 2); t['reason'] = '止损'
            elif (row['日期'] - t['entry_date']).days >= 5:
                sp = row['收盘']
                ret = (sp - t['buy_price']) / t['buy_price'] * 100
                pos = 0
                t['sell_date'] = row['日期']; t['sell_price'] = round(sp, 2)
                t['return_pct'] = round(ret, 2); t['reason'] = '强平'
            else:
                continue
    return trades

def bt_golden_cross(df, tp=5, sl=-3):
    trades = []
    pos = 0
    for i in range(1, len(df)):
        row, prev = df.iloc[i], df.iloc[i-1]
        c5, c10 = row['MA5'], row['MA10']
        p5, p10 = prev['MA5'], prev['MA10']
        if any(pd.isna(x) for x in [c5, c10, p5, p10]):
            continue
        if pos == 0 and p5 <= p10 and c5 > c10:
            pos = 1
            trades.append({'buy_date':row['日期'], 'buy_price':row['收盘']})
        elif pos == 1:
            t = trades[-1]
            if p5 >= p10 and c5 < c10:
                sp = row['收盘']; ret = (sp - t['buy_price']) / t['buy_price'] * 100
                pos = 0; t['sell_date'] = row['日期']; t['sell_price'] = round(sp, 2)
                t['return_pct'] = round(ret, 2); t['reason'] = '死叉'
            else:
                sp = row['开盘']; ret = (sp - t['buy_price']) / t['buy_price'] * 100
                if ret >= tp:
                    pos = 0; t['sell_date'] = row['日期']; t['sell_price'] = round(sp, 2)
                    t['return_pct'] = round(ret, 2); t['reason'] = '止盈'
                elif ret <= sl:
                    pos = 0; t['sell_date'] = row['日期']; t['sell_price'] = round(sp, 2)
                    t['return_pct'] = round(ret, 2); t['reason'] = '止损'
    if pos == 1 and trades:
        t = trades[-1]
        last = df.iloc[-1]
        ret = (last['收盘'] - t['buy_price']) / t['buy_price'] * 100
        t['sell_date'] = last['日期']; t['sell_price'] = round(last['收盘'],2)
        t['return_pct'] = round(ret, 2); t['reason'] = '期末'
    return trades

def verify_trade(df, t):
    if 'sell_date' not in t or t.get('sell_date') is None:
        return ('跳过', 0)
    buy_row = df[df['日期'] == t['buy_date']]
    sell_row = df[df['日期'] == t['sell_date']]
    if buy_row.empty or sell_row.empty:
        return ('日期丢失', 0)
    actual_buy = buy_row.iloc[0]['收盘']
    if t.get('reason') in ['止盈', '止损']:
        actual_sell = sell_row.iloc[0]['开盘']
    else:
        actual_sell = sell_row.iloc[0]['收盘']
    expected = round((actual_sell - actual_buy) / actual_buy * 100, 2)
    if abs(t['return_pct'] - expected) < 0.01:
        return ('准确', t['return_pct'])
    else:
        return ('偏差', expected)

# ===== 主循环 =====
print(f"{'股票':<12} {'策略':<14} {'交易数':<6} {'总收益':<9} {'胜率':<7} {'盈亏比':<8} {'夏普':<7} {'验证结果'}")
print('=' * 75)

all_pass = True
for code, name in stocks.items():
    df = get_data(code)
    if df is None:
        print(f"{name:<12} 数据获取失败")
        continue
    
    for sname, sfn in [('隔夜持仓', bt_mean_reversion), ('金叉死叉', bt_golden_cross)]:
        trades = sfn(df)
        if not trades:
            print(f"{name:<12} {sname:<14} 0      无交易")
            continue
        
        for t in trades:
            if 'return_pct' not in t:
                t['return_pct'] = 0.0
        
        total_ret = sum(t.get('return_pct', 0) for t in trades)
        wins = sum(1 for t in trades if t.get('return_pct', 0) > 0)
        total = len(trades)
        win_rate = f'{wins/total*100:.0f}%'
        avg_win = sum(t['return_pct'] for t in trades if t['return_pct'] > 0) / max(wins, 1)
        avg_loss = abs(sum(t['return_pct'] for t in trades if t['return_pct'] < 0)) / max(total - wins, 1)
        pl = f'{avg_win/avg_loss:.2f}' if avg_loss > 0 else 'N/A'
        rets = [t['return_pct'] for t in trades]
        sr = f'{np.mean(rets)/np.std(rets)*252**0.5:.1f}' if len(rets) > 1 and np.std(rets) > 0 else '0.0'
        
        # 逐笔验证
        all_ok = True
        details = []
        for t in trades:
            status, _ = verify_trade(df, t)
            if status != '准确':
                all_ok = False
                # 详细输出偏差
                buy_str = t['buy_date'].strftime('%m-%d') if hasattr(t['buy_date'], 'strftime') else str(t['buy_date'])[5:10]
                sell_str = t['sell_date'].strftime('%m-%d') if hasattr(t['sell_date'], 'strftime') else str(t['sell_date'])[5:10]
                details.append(f"    {buy_str}->{sell_str}: {status}")
        
        if all_ok:
            print(f"{name:<12} {sname:<14} {total:<6} {total_ret:<+8.2f}% {win_rate:<7} {pl:<8} {sr:<7} ✅全对")
        else:
            all_pass = False
            print(f"{name:<12} {sname:<14} {total:<6} {total_ret:<+8.2f}% {win_rate:<7} {pl:<8} {sr:<7} ❌有误")
            for d in details:
                print(d)

print()
print('=' * 75)
if all_pass:
    print('✅ 全部验证通过！所有交易数据准确无误')
else:
    print('⚠️ 存在偏差，请检查上方详情')
