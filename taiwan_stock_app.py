import streamlit as st
import pandas as pd
import requests
import io
import urllib3
from datetime import datetime, timedelta
import plotly.express as px

# 1. 忽略 SSL 警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

st.set_page_config(page_title="台股強勢族群掃描器", layout="wide")

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
        if '產業別' not in df.columns: df['產業別'] = '一般股票'
        
        cols_to_fix = ['成交金額', '漲跌價差', '收盤價']
        for col in cols_to_fix:
            df[col] = pd.to_numeric(df[col], errors='coerce')
        
        if '漲跌(+/-)' in df.columns:
            df['漲跌符號'] = df['漲跌(+/-)'].str.extract('([+-])')
            df['實際漲跌'] = df.apply(lambda x: x['漲跌價差'] if x['漲跌符號'] == '+' else -x['漲跌價差'] if x['漲跌符號'] == '-' else 0, axis=1)
            df['漲幅(%)'] = (df['實際漲跌'] / (df['收盤價'] - df['實際漲跌'])) * 100
        else:
            df['漲幅(%)'] = 0.0
        return df
    except Exception as e:
        st.error(f"錯誤: {e}")
        return None

# --- UI 介面 ---
st.title("🚀 台股強勢族群掃描器 (含個股新聞)")

default_date = get_valid_date()
selected_date = st.sidebar.date_input("📅 選擇掃描日期", default_date)
date_str = selected_date.strftime("%Y%m%d")

if st.button('🔥 開始掃描行情'):
    with st.spinner(f'正在分析數據...'):
        all_df = fetch_data(date_str)
        if all_df is not None:
            top_30 = all_df.sort_values(by='成交金額', ascending=False).head(30)
            strong_stocks = top_30[top_30['漲幅(%)'] > 3].copy()
            
            if not strong_stocks.empty:
                # --- 新增：產生新聞搜尋連結 ---
                # 連結格式：Google 新聞搜尋
                strong_stocks['新聞連結'] = strong_stocks.apply(
                    lambda x: f"https://www.google.com/search?q={x['證券代號']}+{x['證券名稱']}+新聞&tbm=nws", axis=1
                )
                
                st.subheader(f"✅ 符合條件標的 (共 {len(strong_stocks)} 檔)")
                st.info("💡 提示：點擊下表中的「查看新聞」連結，會自動跳轉至該股搜尋結果。")

                # 使用 st.column_config 將 URL 轉換為可點擊的按鈕或連結
                st.data_editor(
                    strong_stocks[['證券代號', '證券名稱', '產業別', '收盤價', '漲幅(%)', '成交金額', '新聞連結']],
                    column_config={
                        "新聞連結": st.column_config.LinkColumn(
                            "個股新聞",
                            help="點擊跳轉至 Google 新聞搜尋",
                            validate="^http://.*",
                            display_text="查看新聞" # 表格中顯示的文字
                        ),
                        "漲幅(%)": st.column_config.NumberColumn(format="%.2f%%"),
                        "成交金額": st.column_config.NumberColumn(format="%d"),
                    },
                    hide_index=True,
                    use_container_width=True
                )
                
                st.subheader("📊 產業族群分布圖")
                fig = px.treemap(
                    strong_stocks, path=['產業別', '證券名稱'], values='成交金額',
                    color='漲幅(%)', color_continuous_scale='Reds',
                    hover_data=['收盤價']
                )
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.warning("沒有符合條件的股票。")
        else:
            st.error("無法取得資料。")

st.divider()
st.caption("資料來源：臺灣證券交易所。")
