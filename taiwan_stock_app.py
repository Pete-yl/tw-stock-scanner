import streamlit as st
import pandas as pd
import requests
import io
import urllib3
from datetime import datetime, timedelta
import plotly.express as px

# 1. 忽略 SSL 警告 (避免之前遇到的 SSLError)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# --- 設定網頁環境 ---
st.set_page_config(page_title="台股強勢族群掃描器", layout="wide")

# --- 功能函數定義 ---

def get_valid_date():
    """判斷目標日期：若是週末則回傳上週五"""
    now = datetime.now()
    weekday = now.weekday() 
    if weekday == 5:     # 週六
        target = now - timedelta(days=1)
    elif weekday == 6:   # 週日
        target = now - timedelta(days=2)
    else:
        target = now
    return target

def fetch_data(date_str):
    """向證交所抓取資料並清洗"""
    url = f"https://www.twse.com.tw/exchangeReport/MI_INDEX?response=csv&date={date_str}&type=ALLBUT0999"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    
    try:
        # 1. 執行請求
        res = requests.get(url, headers=headers, verify=False, timeout=15)
        if len(res.text) < 500:
            return None

        # 2. 解析 CSV 內容
        lines = res.text.split('\n')
        cleaned_data = []
        start_parsing = False
        for line in lines:
            if '\"證券代號\"' in line:
                start_parsing = True
            if start_parsing:
                cleaned_data.append(line)
        
        if not cleaned_data:
            return None
            
        df = pd.read_csv(io.StringIO('\n'.join(cleaned_data)))
        
        # 3. 清理欄位與資料格式
        df.columns = [str(c).replace('\"', '').strip() for c in df.columns]
        for col in df.columns:
            df[col] = df[col].astype(str).str.replace('\"', '').str.replace(',', '').str.strip()

        # 檢查必備欄位
        if '產業別' not in df.columns:
            df['產業別'] = '一般股票'

        # 4. 數值轉換
        cols_to_fix = ['成交金額', '漲跌價差', '收盤價']
        for col in cols_to_fix:
            df[col] = pd.to_numeric(df[col], errors='coerce')
        
        # 5. 計算漲幅邏輯
        if '漲跌(+/-)' in df.columns:
            df['漲跌符號'] = df['漲跌(+/-)'].str.extract('([+-])')
            df['實際漲跌'] = df.apply(
                lambda x: x['漲跌價差'] if x['漲跌符號'] == '+' 
                else -x['漲跌價差'] if x['漲跌符號'] == '-' 
                else 0, axis=1
            )
            # 漲幅公式
            df['漲幅(%)'] = (df['實際漲跌'] / (df['收盤價'] - df['實際漲跌'])) * 100
        else:
            df['漲幅(%)'] = 0.0
            
        return df

    except Exception as e:
        # 如果 try 區塊發生任何事，這裡會捕捉並顯示
        st.error(f"資料抓取或處理失敗: {e}")
        return None

# --- 網頁介面佈局 ---
st.title("🚀 台股強勢族群掃描器")
st.markdown("### 篩選條件：成交值前 30 名 ＋ 漲幅 > 3%")

# 側邊欄控制
default_date = get_valid_date()
selected_date = st.sidebar.date_input("📅 選擇掃描日期", default_date)
date_str = selected_date.strftime("%Y%m%d")

if st.button('🔥 開始掃描行情'):
    with st.spinner(f'正在分析 {date_str} 的市場數據...'):
        all_df = fetch_data(date_str)
        
        if all_df is not None:
            # 1. 篩選：成交金額前 30 名
            top_30 = all_df.sort_values(by='成交金額', ascending=False).head(30)
            
            # 2. 過濾：漲幅 > 3%
            strong_stocks = top_30[top_30['漲幅(%)'] > 3].copy()
            
            if not strong_stocks.empty:
                st.subheader(f"✅ 符合條件標的 (共 {len(strong_stocks)} 檔)")
                
                # 選取顯示欄位
                target_cols = ['證券代號', '證券名稱', '產業別', '收盤價', '漲幅(%)', '成交金額']
                available_cols = [c for c in target_cols if c in strong_stocks.columns]
                
                # 表格美化
                st.dataframe(
                    strong_stocks[available_cols].style.format({
                        '漲幅(%)': '{:.2f}%', 
                        '成交金額': '{:,.0f}',
                        '收盤價': '{:.2f}'
                    }), 
                    use_container_width=True
                )
                
                # 3. 繪製族群熱力圖
                st.subheader("📊 產業族群分布圖 (Treemap)")
                fig = px.treemap(
                    strong_stocks, 
                    path=['產業別', '證券名稱'], 
                    values='成交金額',
                    color='漲幅(%)',
                    color_continuous_scale='Reds',
                    hover_data=['收盤價', '證券代號']
                )
                st.plotly_chart(fig, use_container_width=True)
                
            else:
                st.warning(f"在 {date_str} 的前 30 名成交標的中，沒有漲幅 > 3% 的股票。")
        else:
            st.error(f"無法取得 {date_str} 的資料。")

st.divider()
st.caption("資料來源：臺灣證券交易所 (TWSE)。本工具僅供開發學習參考。")