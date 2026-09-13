import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup

st.set_page_config(page_title="集中投資向け株判定", layout="centered")
st.title("📱 集中投資向け・株判定＆分析")

# セッション状態
if "watchlist" not in st.session_state:
    st.session_state.watchlist = ["166A", "5132", "332A", "7203"]

selected_code = st.sidebar.selectbox("銘柄選択", st.session_state.watchlist)

@st.cache_data(ttl=300)
def get_kabutan_data(code):
    url = f"https://kabutan.jp/stock/?code={code}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    try:
        res = requests.get(url, headers=headers, timeout=5)
        if res.status_code != 200:
            return None
        
        soup = BeautifulSoup(res.text, "html.parser")
        
        # 株価
        price_tag = soup.find("span", class_="kabuka")
        price = price_tag.text.strip().replace("円", "").replace(",", "") if price_tag else "---"
        
        # 会社名
        name_tag = soup.find("div", class_="company_block")
        name = name_tag.find("h3").text.strip() if name_tag and name_tag.find("h3") else f"銘柄コード {code}"
        
        # 前日比
        change_tag = soup.find("dd", class_="column2")
        change = change_tag.text.strip() if change_tag else "---"

        return {
            "name": name,
            "price": price,
            "change": change,
            "url": url
        }
    except Exception as e:
        return None

data = get_kabutan_data(selected_code)

if not data:
    st.error(f"銘柄 『{selected_code}』 の株探データの取得に失敗しました。")
else:
    st.subheader(f"{data['name']} ({selected_code})")
    
    c1, c2 = st.columns(2)
    c1.metric("現在株価", f"¥{data['price']}")
    c2.metric("前日比", data['change'])

    st.success("✅ データ取得成功（株探Webアクセス）")
    st.markdown(f"[株探で詳細・チャートを確認する]({data['url']})")
