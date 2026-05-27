"""批量验证回测数据准确性"""
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
            reason = None
            if ret >= tp:
                reason = '止盈'
                sell_price_use = sell_price
            elif ret <= sl:
                reason = '止损'
                sell_price_use = sell_price
            elif (row['日期'] - t['entry_date']).days >= 5:
                sell_price_use = row['收盘']
                ret = (sell_price_use - t['buy_price']) / t['buy_price'] * 100
                reason = '强平'
            else:
                continue
            pos = 0
            t['sell_date'] = row['日期']
            t['sell_price'] = round(sell_price_use, 2)
            t['return_pct'] = round(ret, 2)
            t['reason'] = reason
    return trades

def bt_golden_cross(df, tp=5, sl=-3):
    trades = []
    pos = 0
    for i in range(1, len(df)):
        row, prev = df.iloc[i], df.iloc[i-1]
        ma5_c, ma10_c = row['MA5'], row['MA10']
        ma5_p, ma10_p = prev['MA5'], prev['MA10']
        if any(pd.isna(x) for x in [ma5_c, ma10_c, ma5_p, ma10_p]):
            continue
        if pos == 0 and ma5_p <= ma10_p and ma5_c > ma10_c:
            pos = 1
            trades.append({'buy_date':row['日期'], 'buy_price':row['收盘']})
        elif pos == 1:
            t = trades[-1]
            if ma5_p >= ma10_p and ma5_c < ma10_c:
                sell_price = row['收盘']
                ret = (sell_price - t['buy_price']) / t['buy_price'] * 100
                pos = 0
                t['sell_date'] = row['日期']
                t['sell_price'] = round(sell_price, 2)
                t['return_pct'] = round(ret, 2)
                t['reason'] = '死叉'
            else:
                sell_price = row['开盘']
                ret = (sell_price - t['buy_price']) / t['buy_price'] * 100
                if ret >= tp:
                    pos = 0
                    t['sell_date'] = row['日期']
                    t['sell_price'] = round(sell_price, 2)
                    t['return_pct'] = round(ret, 2)
                    t['reason'] = '止盈'
                elif ret <= sl:
                    pos = 0
                    t['sell_date'] = row['日期']
                    t['sell_price'] = round(sell_price, 2)
                    t['return_pct'] = round(ret, 2)
                    t['reason'] = '止损'
    if pos == 1 and trades:
        t = trades[-1]
        if 'return_pct' not in t:
            last = df.iloc[-1]
            ret = (last['收盘'] - t['buy_price']) / t['buy_price'] * 100
            t['sell_date'] = last['日期']
            t['sell_price'] = round(last['收盘'],2)
            t['return_pct'] = round(ret,2)
            t['reason'] = '期末'
    # 兜底：确保所有交易都有 return_pct
    for t in trades:
        if 'return_pct' not in t:
            t['return_pct'] = 0.0
    return trades

def verify_trade(df, t):
    """验证单笔交易：用原始数据重新计算"""
    if 'sell_date' not in t or t.get('sell_date') is None:
        return '无卖出日期'
    
    buy_row = df[df['日期'] == t['buy_date']]
    sell_row = df[df['日期'] == t['sell_date']]
    if buy_row.empty or sell_row.empty:
        return f'找不到日期'
    
    actual_buy = buy_row.iloc[0]['收盘']
    
    # 根据平仓原因判断是用开盘价还是收盘价
    if t.get('reason') in ['止盈', '止损']:
        actual_sell = sell_row.iloc[0]['开盘']
    else:
        actual_sell = sell_row.iloc[0]['收盘']
    
    expected_ret = round((actual_sell - actual_buy) / actual_buy * 100, 2)
    
    if abs(t['return_pct'] - expected_ret) < 0.01:
        return '准确'
    else:
        return f'偏差: 记录{t["return_pct"]}% vs 重算{expected_ret}% (买{actual_buy:.2f} 卖{actual_sell:.2f})'

# ===== 主循环 =====
print(f"{'股票':<12} {'策略':<14} {'交易数':<6} {'总收益':<9} {'胜率':<7} {'盈亏比':<8} {'夏普':<7} {'验证结果'}")
print('=' * 75)

all_pass = True
for code, name in stocks.items():
    df = get_data(code)
    if df is None:
        print(f"{name:<12} ❌ 无数据")
        continue
    
        for sname, sfn in [('隔夜持仓', bt_mean_reversion), ('金叉死叉', bt_golden_cross)]:
            trades = sfn(df)
            if not trades:
                print(f"{name:<12} {sname:<14} {'0':<6} 无交易")
                continue
            
            # 调试：检查所有交易的字段
            for i, t in enumerate(trades):
                if 'return_pct' not in t:
                    print(f"  DEBUG: {code} {sname} 第{i}笔交易缺 return_pct: buy={t['buy_date']} buy_price={t['buy_price']}")
                    t['return_pct'] = 0.0
                for field in ['return_pct', 'buy_price']:
                    if isinstance(t.get(field), (int, float)):
                        pass
                    elif isinstance(t.get(field), str) and field == 'buy_price':
                        t[field] = float(t[field])
            
            total_ret = sum(t.get('return_pct', 0) for t in trades)
        wins = sum(1 for t in trades if t.get('return_pct', 0) > 0)
        total = len(trades)
        win_rate = f'{wins/total*100:.0f}%'
        
        avg_win = sum(t['return_pct'] for t in trades if t.get('return_pct', 0) > 0) / max(wins, 1)
        avg_loss = abs(sum(t['return_pct'] for t in trades if t.get('return_pct', 0) < 0)) / max(total - wins, 1)
        pl_ratio = f'{avg_win/avg_loss:.2f}' if avg_loss > 0 else 'N/A'
        
        if total > 1:
            rets = [t['return_pct'] for t in trades]
            sr = f'{np.mean(rets)/np.std(rets)*252**0.5:.1f}' if np.std(rets) > 0 else '0.0'
        else:
            sr = '0.0'
        
        # 逐笔验证
        errors = []
        for t in trades:
            v = verify_trade(df, t)
            if v != '准确':
                errors.append(f"    {t['buy_date'].strftime('%m-%d')}->{t['sell_date'].strftime('%m-%d')}: {v}")
        
        status = '全对' if not errors else f'{len(errors)}笔有误'
        if errors:
            all_pass = False
        
        print(f"{name:<12} {sname:<14} {total:<6} {total_ret:<+8.2f}% {win_rate:<7} {pl_ratio:<8} {sr:<7} {status}")
        for e in errors:
            print(e)

print()
print('=' * 75)
if all_pass:
    print('✅ 全部验证通过！所有交易数据准确无误')
else:
    print('⚠️ 存在偏差')
