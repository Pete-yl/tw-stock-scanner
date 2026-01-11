import streamlit as st
import pandas as pd
import requests
import io
import urllib3
import yfinance as yf
from datetime import datetime, timedelta
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# 忽略 SSL 警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

st.set_page_config(page_title="台股全能掃描與分析系統", layout="wide")

# --- 1. 功能函數 ---

def get_valid_date():
    now = datetime.now()
    weekday = now.weekday() 
    if weekday == 5: target = now - timedelta(days=1)
    elif weekday == 6: target = now - timedelta(days=2)
    else: target = now
    return target

def fetch_data(date_str):
    url = f"https://www.twse.com.tw/exchangeReport/MI_INDEX?response=csv&date={date_str}&type=ALLBUT0999"
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        res = requests.get(url, headers=headers, verify=False, timeout=15)
        if len(res.text) < 500: return None
        lines = res.text.split('\n')
        cleaned_data = []
        start_parsing = False
        for line in lines:
            if '\"證券代號\"' in line: start_parsing = True
            if start_parsing: cleaned_data.append(line)
        df = pd.read_csv(io.StringIO('\n'.join(cleaned_data)))
        df.columns = [str(c).replace('\"', '').strip() for c in df.columns]
        for col in df.columns:
            df[col] = df[col].astype(str).str.replace('\"', '').str.replace(',', '').str.strip()
        
        cols_to_fix = ['成交金額', '漲跌價差', '收盤價']
        for col in cols_to_fix:
            df[col] = pd.to_numeric(df[col], errors='coerce')
        
        if '漲跌(+/-)' in df.columns:
            df['實際漲跌'] = df.apply(lambda x: x['漲跌價差'] if '+' in x['漲跌(+/-)'] else -x['漲跌價差'] if '-' in x['漲跌(+/-)'] else 0, axis=1)
            df['漲幅(%)'] = (df['實際漲跌'] / (df['收盤價'] - df['實際漲跌'])) * 100
        return df
    except: return None

# --- 2. 介面主體 ---
st.title("🚀 台股強勢股全方位分析儀表板")

default_date = get_valid_date()
selected_date = st.sidebar.date_input("📅 選擇掃描日期", default_date)
date_str = selected_date.strftime("%Y%m%d")

if st.button('🔥 執行大數據全掃描'):
    all_df = fetch_data(date_str)
    if all_df is not None:
        top_30 = all_df.sort_values(by='成交金額', ascending=False).head(30)
        strong_stocks = top_30[top_30['漲幅(%)'] > 3].copy()
        
        if not strong_stocks.empty:
            # 整合新聞連結
            strong_stocks['新聞連結'] = strong_stocks.apply(
                lambda x: f"https://www.google.com/search?q={x['證券代號']}+{x['證券名稱']}+新聞&tbm=nws", axis=1
            )
            st.session_state['strong_stocks'] = strong_stocks
            
            st.subheader(f"✅ 符合條件標的 (共 {len(strong_stocks)} 檔)")
            # 顯示表格 (含新聞連結)
            st.data_editor(
                strong_stocks[['證券代號', '證券名稱', '產業別', '收盤價', '漲幅(%)', '成交金額', '新聞連結']],
                column_config={
                    "新聞連結": st.column_config.LinkColumn("個股新聞", display_text="查看新聞"),
                    "漲幅(%)": st.column_config.NumberColumn(format="%.2f%%"),
                    "成交金額": st.column_config.NumberColumn(format="%d"),
                },
                hide_index=True, use_container_width=True
            )
        else:
            st.warning("查無符合條件標的。")

# --- 3. 進階分析與儀表板 ---
if 'strong_stocks' in st.session_state:
    st.divider()
    options = st.session_state['strong_stocks'].apply(lambda x: f"{x['證券代號']} {x['證券名稱']}", axis=1).tolist()
    target_stock = st.selectbox("🎯 選擇標的進行深度診斷：", options)
    
    if target_stock:
        symbol = target_stock.split(' ')[0] + ".TW"
        df_stock = yf.download(symbol, period="2y", interval="1d", auto_adjust=True)
        
        if not df_stock.empty:
            if isinstance(df_stock.columns, pd.MultiIndex):
                df_stock.columns = df_stock.columns.get_level_values(0)

            # 計算均線
            df_stock['MA5'] = df_stock['Close'].rolling(window=5).mean()
            df_stock['MA20'] = df_stock['Close'].rolling(window=20).mean()
            df_stock['MA60'] = df_stock['Close'].rolling(window=60).mean()
            df_stock['MA120'] = df_stock['Close'].rolling(window=120).mean()
            df_stock['MA240'] = df_stock['Close'].rolling(window=240).mean()
            
            # 計算乖離率 (BIAS)
            df_stock['BIAS_5'] = ((df_stock['Close'] - df_stock['MA5']) / df_stock['MA5']) * 100
            df_stock['BIAS_20'] = ((df_stock['Close'] - df_stock['MA20']) / df_stock['MA20']) * 100

            # 計算 MACD
            exp1 = df_stock['Close'].ewm(span=12, adjust=False).mean()
            exp2 = df_stock['Close'].ewm(span=26, adjust=False).mean()
            df_stock['DIF'] = exp1 - exp2
            df_stock['MACD_L'] = df_stock['DIF'].ewm(span=9, adjust=False).mean()
            df_stock['OSC'] = df_stock['DIF'] - df_stock['MACD_L']

            # --- st.metric 儀表板區塊 ---
            cur_p = df_stock['Close'].iloc[-1]
            b5 = df_stock['BIAS_5'].iloc[-1]
            b20 = df_stock['BIAS_20'].iloc[-1]
            
            m1, m2, m3 = st.columns(3)
            m1.metric("當前股價", f"{cur_p:.2f}")
            m2.metric("5日乖離率", f"{b5:.2f}%", delta="過熱" if b5 > 10 else "正常", delta_color="inverse" if b5 > 10 else "normal")
            m3.metric("20日乖離率", f"{b20:.2f}%", delta="過熱" if b20 > 10 else "正常", delta_color="inverse" if b20 > 10 else "normal")

            # --- 繪製線圖 ---
            plot_df = df_stock.tail(120)
            fig = make_subplots(rows=3, cols=1, shared_xaxes=True, vertical_spacing=0.05, row_heights=[0.5, 0.2, 0.3])

            # (A) K線圖與五大均線
            fig.add_trace(go.Candlestick(x=plot_df.index, open=plot_df['Open'], high=plot_df['High'], low=plot_df['Low'], close=plot_df['Close'], name='K線'), row=1, col=1)
            ma_list = [('MA5','blue','5MA'),('MA20','orange','20MA'),('MA60','green','60MA'),('MA120','purple','120MA'),('MA240','red','240MA')]
            for col, color, name in ma_list:
                fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df[col], line=dict(color=color, width=1), name=name), row=1, col=1)

            # (B) 成交量
            v_colors = ['red' if c >= o else 'green' for c, o in zip(plot_df['Close'], plot_df['Open'])]
            fig.add_trace(go.Bar(x=plot_df.index, y=plot_df['Volume'], name='成交量', marker_color=v_colors), row=2, col=1)

            # (C) MACD
            fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df['DIF'], name='DIF', line=dict(color='black')), row=3, col=1)
            fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df['MACD_L'], name='MACD', line=dict(color='red')), row=3, col=1)
            o_colors = ['red' if x >= 0 else 'green' for x in plot_df['OSC']]
            fig.add_trace(go.Bar(x=plot_df.index, y=plot_df['OSC'], name='OSC', marker_color=o_colors), row=3, col=1)

            fig.update_layout(height=900, xaxis_rangeslider_visible=False, template="plotly_white", hovermode='x unified')
            st.plotly_chart(fig, use_container_width=True)
