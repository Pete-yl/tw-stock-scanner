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

st.set_page_config(page_title="台股強勢股分析系統", layout="wide")

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
        # 清理欄位名稱中的空格與引號
        df.columns = [str(c).replace('\"', '').strip() for c in df.columns]
        # 清理儲存格內容
        for col in df.columns:
            df[col] = df[col].astype(str).str.replace('\"', '').str.replace(',', '').str.strip()
        
        # 轉為數值
        cols_to_fix = ['成交金額', '漲跌價差', '收盤價']
        for col in cols_to_fix:
            df[col] = pd.to_numeric(df[col], errors='coerce')
        
        # 產業別保險機制
        if '產業別' not in df.columns:
            df['產業別'] = '一般股票'
            
        if '漲跌(+/-)' in df.columns:
            df['實際漲跌'] = df.apply(lambda x: x['漲跌價差'] if '+' in x['漲跌(+/-)'] else -x['漲跌價差'] if '-' in x['漲跌(+/-)'] else 0, axis=1)
            df['漲幅(%)'] = (df['實際漲跌'] / (df['收盤價'] - df['實際漲跌'])) * 100
        return df
    except:
        return None

# --- 2. 介面主體 ---
st.title("📈 台股強勢股全方位分析")

default_date = get_valid_date()
selected_date = st.sidebar.date_input("📅 選擇掃描日期", default_date)
date_str = selected_date.strftime("%Y%m%d")

if st.button('🔥 執行大數據掃描'):
    with st.spinner('數據處理中...'):
        all_df = fetch_data(date_str)
        if all_df is not None:
            # 篩選條件：成交金額前 30 名 且 漲幅 > 3%
            top_30 = all_df.sort_values(by='成交金額', ascending=False).head(30)
            strong_stocks = top_30[top_30['漲幅(%)'] > 3].copy()
            
            if not strong_stocks.empty:
                # 產生新聞連結
                strong_stocks['新聞連結'] = strong_stocks.apply(
                    lambda x: f"https://www.google.com/search?q={x['證券代號']}+{x['證券名稱']}+新聞&tbm=nws", axis=1
                )
                st.session_state['strong_stocks'] = strong_stocks
                
                st.subheader(f"✅ 符合條件標的 (共 {len(strong_stocks)} 檔)")
                
                # 欄位安全檢查：確保要顯示的欄位都存在
                target_cols = ['證券代號', '證券名稱', '產業別', '收盤價', '漲幅(%)', '成交金額', '新聞連結']
                available_cols = [c for c in target_cols if c in strong_stocks.columns]
                
                st.data_editor(
                    strong_stocks[available_cols],
                    column_config={
                        "新聞連結": st.column_config.LinkColumn("個股新聞", display_text="查看新聞"),
                        "漲幅(%)": st.column_config.NumberColumn(format="%.2f%%"),
                        "成交金額": st.column_config.NumberColumn(format="%d"),
                    },
                    hide_index=True, use_container_width=True
                )
            else:
                st.warning("查無符合條件標的。")
        else:
            st.error("無法取得該日期資料，請檢查是否為開盤日。")

# --- 3. 技術分析與儀表板 ---
if 'strong_stocks' in st.session_state:
    st.divider()
    stocks = st.session_state['strong_stocks']
    options = stocks.apply(lambda x: f"{x['證券代號']} {x['證券名稱']}", axis=1).tolist()
    target_stock = st.selectbox("🎯 選擇標的診斷型態：", options)
    
    if target_stock:
        symbol = target_stock.split(' ')[0] + ".TW"
        # 抓取 2 年資料以支援年線計算
        df_stock = yf.download(symbol, period="2y", interval="1d", auto_adjust=True)
        
        if not df_stock.empty:
            # 解決 Multi-Index 造成的 ValueError
            if isinstance(df_stock.columns, pd.MultiIndex):
                df_stock.columns = df_stock.columns.get_level_values(0)

            # 計算指標
            df_stock['MA5'] = df_stock['Close'].rolling(5).mean()
            df_stock['MA20'] = df_stock['Close'].rolling(20).mean()
            df_stock['MA60'] = df_stock['Close'].rolling(60).mean()
            df_stock['MA120'] = df_stock['Close'].rolling(120).mean()
            df_stock['MA240'] = df_stock['Close'].rolling(240).mean()
            
            df_stock['BIAS_5'] = ((df_stock['Close'] - df_stock['MA5']) / df_stock['MA5']) * 100
            df_stock['BIAS_20'] = ((df_stock['Close'] - df_stock['MA20']) / df_stock['MA20']) * 100

            exp1 = df_stock['Close'].ewm(span=12, adjust=False).mean()
            exp2 = df_stock['Close'].ewm(span=26, adjust=False).mean()
            df_stock['DIF'] = exp1 - exp2
            df_stock['MACD_L'] = df_stock['DIF'].ewm(9, adjust=False).mean()
            df_stock['OSC'] = df_stock['DIF'] - df_stock['MACD_L']

            # 儀表板
            cur_p = float(df_stock['Close'].iloc[-1])
            b5 = float(df_stock['BIAS_5'].iloc[-1])
            b20 = float(df_stock['BIAS_20'].iloc[-1])
            
            m1, m2, m3 = st.columns(3)
            m1.metric("當前股價", f"{cur_p:.2f}")
            m2.metric("5日乖離率", f"{b5:.2f}%", delta="過熱" if b5 > 10 else "正常", delta_color="inverse" if b5 > 10 else "normal")
            m3.metric("20日乖離率", f"{b20:.2f}%", delta="過熱" if b20 > 10 else "正常", delta_color="inverse" if b20 > 10 else "normal")

            # 繪圖
            plot_df = df_stock.tail(100)
            fig = make_subplots(rows=3, cols=1, shared_xaxes=True, vertical_spacing=0.05, row_heights=[0.5, 0.2, 0.3])
            
            fig.add_trace(go.Candlestick(x=plot_df.index, open=plot_df['Open'], high=plot_df['High'], low=plot_df['Low'], close=plot_df['Close'], name='K線'), row=1, col=1)
            
            ma_cfg = [('MA5','blue','5MA'),('MA20','orange','20MA'),('MA60','green','60MA'),('MA120','purple','120MA'),('MA240','red','240MA')]
            for col, color, name in ma_cfg:
                fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df[col], line=dict(color=color, width=1), name=name), row=1, col=1)

            v_colors = ['red' if c >= o else 'green' for c, o in zip(plot_df['Close'], plot_df['Open'])]
            fig.add_trace(go.Bar(x=plot_df.index, y=plot_df['Volume'], name='成交量', marker_color=v_colors), row=2, col=1)

            fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df['DIF'], name='DIF', line=dict(color='black')), row=3, col=1)
            fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df['MACD_L'], name='MACD', line=dict(color='red')), row=3, col=1)
            o_colors = ['red' if x >= 0 else 'green' for x in plot_df['OSC']]
            fig.add_trace(go.Bar(x=plot_df.index, y=plot_df['OSC'], name='OSC', marker_color=o_colors), row=3, col=1)

            fig.update_layout(height=850, xaxis_rangeslider_visible=False, template="plotly_white", hovermode='x unified')
            st.plotly_chart(fig, use_container_width=True)
