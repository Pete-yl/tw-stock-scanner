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

st.set_page_config(page_title="台股強勢股全方位分析", layout="wide")

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

# --- 介面設計 ---
st.title("🚀 台股全能分析：多天期均線與指標系統")

default_date = get_valid_date()
selected_date = st.sidebar.date_input("📅 選擇掃描日期", default_date)
date_str = selected_date.strftime("%Y%m%d")

if st.button('🔥 執行大數據掃描'):
    all_df = fetch_data(date_str)
    if all_df is not None:
        top_30 = all_df.sort_values(by='成交金額', ascending=False).head(30)
        strong_stocks = top_30[top_30['漲幅(%)'] > 3].copy()
        if not strong_stocks.empty:
            st.session_state['strong_stocks'] = strong_stocks
            st.success(f"成功篩選出 {len(strong_stocks)} 檔強勢股")
            st.dataframe(strong_stocks[['證券代號', '證券名稱', '收盤價', '漲幅(%)', '成交金額']], use_container_width=True)
        else:
            st.warning("查無符合條件標的。")

# --- 進階分析區塊 ---
if 'strong_stocks' in st.session_state:
    st.divider()
    options = st.session_state['strong_stocks'].apply(lambda x: f"{x['證券代號']} {x['證券名稱']}", axis=1).tolist()
    target_stock = st.selectbox("🎯 選擇標的進行多天期線型診斷：", options)
    
    if target_stock:
        symbol = target_stock.split(' ')[0] + ".TW"
        # 抓取 2 年資料以確保年線 (240MA) 計算正確
        df_stock = yf.download(symbol, period="2y", interval="1d", auto_adjust=True)
        
        if not df_stock.empty:
            if isinstance(df_stock.columns, pd.MultiIndex):
                df_stock.columns = df_stock.columns.get_level_values(0)

            # 1. 計算所有均線
            df_stock['MA5'] = df_stock['Close'].rolling(window=5).mean()
            df_stock['MA20'] = df_stock['Close'].rolling(window=20).mean()
            df_stock['MA60'] = df_stock['Close'].rolling(window=60).mean()
            df_stock['MA120'] = df_stock['Close'].rolling(window=120).mean()
            df_stock['MA240'] = df_stock['Close'].rolling(window=240).mean()
            
            # 2. 乖離率與 MACD (同前)
            df_stock['BIAS_20'] = ((df_stock['Close'] - df_stock['MA20']) / df_stock['MA20']) * 100
            exp1 = df_stock['Close'].ewm(span=12, adjust=False).mean()
            exp2 = df_stock['Close'].ewm(span=26, adjust=False).mean()
            df_stock['DIF'] = exp1 - exp2
            df_stock['MACD_L'] = df_stock['DIF'].ewm(span=9, adjust=False).mean()
            df_stock['OSC'] = df_stock['DIF'] - df_stock['MACD_L']

            # 只取最近 6 個月顯示，避免圖表太長，但 MA 計算已經完成
            plot_df = df_stock.tail(120)

            # 3. 建立子圖
            fig = make_subplots(rows=3, cols=1, shared_xaxes=True, vertical_spacing=0.05, row_heights=[0.5, 0.2, 0.3])

            # (A) K線圖
            fig.add_trace(go.Candlestick(x=plot_df.index, open=plot_df['Open'], high=plot_df['High'], low=plot_df['Low'], close=plot_df['Close'], name='K線'), row=1, col=1)
            
            # 加入多天期均線
            ma_configs = [
                ('MA5', 'LightSkyBlue', '5MA(週)'),
                ('MA20', 'orange', '20MA(月)'),
                ('MA60', 'green', '60MA(季)'),
                ('MA120', 'purple', '120MA(半年)'),
                ('MA240', 'red', '240MA(年)')
            ]
            for col, color, name in ma_configs:
                fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df[col], line=dict(color=color, width=1), name=name), row=1, col=1)

            # (B) 成交量
            bar_colors = ['#EF5350' if c >= o else '#26A69A' for c, o in zip(plot_df['Close'], plot_df['Open'])]
            fig.add_trace(go.Bar(x=plot_df.index, y=plot_df['Volume'], name='成交量', marker_color=bar_colors), row=2, col=1)

            # (C) MACD
            fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df['DIF'], name='DIF', line=dict(color='black')), row=3, col=1)
            fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df['MACD_L'], name='MACD', line=dict(color='red')), row=3, col=1)
            osc_colors = ['#EF5350' if x >= 0 else '#26A69A' for x in plot_df['OSC']]
            fig.add_trace(go.Bar(x=plot_df.index, y=plot_df['OSC'], name='OSC', marker_color=osc_colors), row=3, col=1)

            fig.update_layout(height=900, xaxis_rangeslider_visible=False, template="plotly_white", hovermode='x unified')
            st.plotly_chart(fig, use_container_width=True)
            
            st.write("📖 **技術教室**：當短天期均線(5, 20)在長天期均線(60, 240)之上且全部向上延伸，即為『多頭排列』。")
