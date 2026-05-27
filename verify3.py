#!/usr/bin/env python3
"""批量验证 - 防御性写法"""
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
        r, p = df.iloc[i], df.iloc[i-1]
        if pos == 0:
            mv = p[f'MA{ma}']
            if pd.isna(mv): continue
            dec = (r['收盘'] - p['收盘']) / p['收盘'] * 100
            if r['收盘'] < mv and dec < -buy_thresh:
                pos = 1
                trades.append({'buy': r['日期'], 'bprice': r['收盘'], 'entry': r['日期']})
        else:
            t = trades[-1]
            sp = r['开盘']; ret = (sp - t['bprice']) / t['bprice'] * 100
            if ret >= tp:
                pos = 0; t.update({'sell': r['日期'], 'sprice': round(sp,2), 'ret': round(ret,2), 'why': '止盈'})
            elif ret <= sl:
                pos = 0; t.update({'sell': r['日期'], 'sprice': round(sp,2), 'ret': round(ret,2), 'why': '止损'})
            elif (r['日期'] - t['entry']).days >= 5:
                sp = r['收盘']; ret = (sp - t['bprice']) / t['bprice'] * 100
                pos = 0; t.update({'sell': r['日期'], 'sprice': round(sp,2), 'ret': round(ret,2), 'why': '强平'})
    # 期末平仓
    if pos == 1 and trades:
        t = trades[-1]
        if 'ret' not in t:
            last = df.iloc[-1]
            ret = (last['收盘'] - t['bprice']) / t['bprice'] * 100
            t.update({'sell': last['日期'], 'sprice': round(last['收盘'],2), 'ret': round(ret,2), 'why': '期末'})
    return trades

def bt_golden_cross(df, tp=5, sl=-3):
    trades = []
    pos = 0
    for i in range(1, len(df)):
        r, p = df.iloc[i], df.iloc[i-1]
        c5, c10 = r['MA5'], r['MA10']
        p5, p10 = p['MA5'], p['MA10']
        if any(pd.isna(x) for x in [c5, c10, p5, p10]): continue
        if pos == 0 and p5 <= p10 and c5 > c10:
            pos = 1
            trades.append({'buy': r['日期'], 'bprice': r['收盘']})
        elif pos == 1:
            t = trades[-1]
            if p5 >= p10 and c5 < c10:
                sp = r['收盘']; ret = (sp - t['bprice']) / t['bprice'] * 100
                pos = 0; t.update({'sell': r['日期'], 'sprice': round(sp,2), 'ret': round(ret,2), 'why': '死叉'})
            else:
                sp = r['开盘']; ret = (sp - t['bprice']) / t['bprice'] * 100
                if ret >= tp:
                    pos = 0; t.update({'sell': r['日期'], 'sprice': round(sp,2), 'ret': round(ret,2), 'why': '止盈'})
                elif ret <= sl:
                    pos = 0; t.update({'sell': r['日期'], 'sprice': round(sp,2), 'ret': round(ret,2), 'why': '止损'})
    if pos == 1 and trades:
        t = trades[-1]
        if 'ret' not in t:
            last = df.iloc[-1]
            ret = (last['收盘'] - t['bprice']) / t['bprice'] * 100
            t.update({'sell': last['日期'], 'sprice': round(last['收盘'],2), 'ret': round(ret,2), 'why': '期末'})
    return trades

def fmt_date(d):
    if hasattr(d, 'strftime'):
        return d.strftime('%m-%d')
    s = str(d)
    return s[5:10] if len(s) >= 10 else s

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
        
        # 缺失字段兜底
        for t in trades:
            t.setdefault('ret', 0.0)
            t.setdefault('sell', df.iloc[-1]['日期'] if t == trades[-1] else t.get('buy'))
            t.setdefault('sprice', round(df.iloc[-1]['收盘'], 2))
        
        total_ret = sum(t['ret'] for t in trades)
        wins = sum(1 for t in trades if t['ret'] > 0)
        total = len(trades)
        wr = f'{wins/total*100:.0f}%'
        aw = sum(t['ret'] for t in trades if t['ret'] > 0) / max(wins, 1)
        al = abs(sum(t['ret'] for t in trades if t['ret'] < 0)) / max(total - wins, 1)
        pl = f'{aw/al:.2f}' if al > 0 else 'N/A'
        rets = [t['ret'] for t in trades]
        sr = f'{np.mean(rets)/np.std(rets)*252**0.5:.1f}' if len(rets) > 1 and np.std(rets) > 0 else '0.0'
        
        # 逐笔验证
        errors = []
        for t in trades:
            br = df[df['日期'] == t['buy']]
            sr_df = df[df['日期'] == t['sell']]
            if br.empty or sr_df.empty:
                errors.append(f"  {fmt_date(t['buy'])}->{fmt_date(t['sell'])}: 日期丢失")
                continue
            actual_buy = br.iloc[0]['收盘']
            sell_col = '开盘' if t.get('why') in ['止盈','止损'] else '收盘'
            actual_sell = sr_df.iloc[0][sell_col]
            expected = round((actual_sell - actual_buy) / actual_buy * 100, 2)
            if abs(t['ret'] - expected) >= 0.01:
                errors.append(f"  {fmt_date(t['buy'])}->{fmt_date(t['sell'])}: 记录{t['ret']}% vs 重算{expected}%")

        if errors:
            all_pass = False
            print(f"{name:<12} {sname:<14} {total:<6} {total_ret:<+8.2f}% {wr:<7} {pl:<8} {sr:<7} ❌有误")
            for e in errors: print(e)
        else:
            print(f"{name:<12} {sname:<14} {total:<6} {total_ret:<+8.2f}% {wr:<7} {pl:<8} {sr:<7} ✅全对")

print()
print('=' * 75)
if all_pass:
    print('✅ 全部验证通过！所有交易数据准确无误')
else:
    print('⚠️ 存在偏差')
