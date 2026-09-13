import streamlit as st
import pandas as pd
import pandas_datareader.data as web
import yfinance as yf
from datetime import datetime, timedelta

st.set_page_config(page_title="集中投資向け株判定", layout="centered")
st.title("📱 集中投資向け・株判定＆分析")

# セッション状態
if "watchlist" not in st.session_state:
    st.session_state.watchlist = ["166A", "5132", "332A", "7203"]
if "selected_ticker" not in st.session_state:
    st.session_state.selected_ticker = "166A"

# サイドバー
st.sidebar.header("⚙️ 設定・ウォッチリスト")
mode = st.sidebar.radio("評価モードを選択:", ("🚀 グロース（3年3倍・集中投資）", "🛡️ バリュー（割安・高配当）"))

clean_watchlist = [t.replace(".T", "") for t in st.session_state.watchlist]
selected_code = st.sidebar.selectbox("登録銘柄を選択:", clean_watchlist)

new_ticker = st.sidebar.text_input("銘柄追加 (例: 9984)").strip().replace(".T", "")
if st.sidebar.button("リストに追加"):
    if new_ticker and new_ticker not in clean_watchlist:
        st.session_state.watchlist.append(new_ticker)
        st.session_state.selected_ticker = new_ticker
        st.rerun()

# データ取得処理 (Stooq経由)
@st.cache_data(ttl=300)
def fetch_stock_data_stooq(code):
    end_date = datetime.now()
    start_date = end_date - timedelta(days=180)
    
    # 日本株コードフォーマット (例: 7203.JP)
    symbol = f"{code}.JP"
    try:
        df = web.DataReader(symbol, 'stooq', start_date, end_date)
        if df.empty:
            return pd.DataFrame()
        df = df.sort_index() # 日付昇順にソート
        return df
    except Exception:
        return pd.DataFrame()

# メイン処理
df = fetch_stock_data_stooq(selected_code)

if df.empty or 'Close' not in df.columns:
    st.error(f"銘柄コード 『{selected_code}』 のデータ取得に失敗しました。")
    st.info("※コードが正しいか確認してください（例: 166A, 7203）。")
else:
    # 移動平均線
    df['MA5'] = df['Close'].rolling(window=5).mean()
    df['MA25'] = df['Close'].rolling(window=25).mean()
    df['MA75'] = df['Close'].rolling(window=75).mean()

    latest_price = float(df['Close'].iloc[-1])
    ma25 = float(df['MA25'].dropna().iloc[-1]) if not df['MA25'].dropna().empty else latest_price
    ma75 = float(df['MA75'].dropna().iloc[-1]) if not df['MA75'].dropna().empty else latest_price

    # 簡易スコアリング
    score = 0
    reasons = []
    
    if latest_price > ma25 > ma75:
        score += 3
        reasons.append("パーフェクトオーダー（強い上昇トレンド）: +3点")
    elif latest_price > ma25:
        score += 1
        reasons.append("25日移動平均線の上で推移: +1点")
    else:
        score -= 1
        reasons.append("移動平均線の下で推移（下落傾向）: -1点")

    # 表示
    st.subheader(f"銘柄コード: {selected_code}")
    
    if score >= 3:
        st.success(f"### 🚀 トレンド良好 (Score: {score})")
    else:
        st.warning(f"### 👀 様子見・慎重 (Score: {score})")

    st.write("#### 📈 株価推移（5日・25日・75日移動平均）")
    st.line_chart(df[['Close', 'MA5', 'MA25', 'MA75']])

    c1, c2 = st.columns(2)
    c1.metric("現在株価", f"¥{latest_price:,.0f}")
    c2.metric("前日比", f"¥{latest_price - float(df['Close'].iloc[-2]):+,.0f}")

    if reasons:
        st.markdown("**📊 判定内訳**")
        for r in reasons:
            st.write(f"- {r}")
