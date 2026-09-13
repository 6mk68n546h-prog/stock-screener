import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime

# ページ基本設定
st.set_page_config(page_title="集中投資向け株判定", layout="centered")

st.title("📱 集中投資向け・株判定＆分析")

# セッション状態の初期化
if "watchlist" not in st.session_state:
    st.session_state.watchlist = ["166A.T", "5132.T", "332A.T", "7203.T"]
if "selected_ticker" not in st.session_state:
    st.session_state.selected_ticker = "166A.T"

# --- サイドバー ---
st.sidebar.header("⚙️ 設定・ウォッチリスト")

mode = st.sidebar.radio(
    "評価モードを選択:",
    ("🚀 グロース（3年3倍・集中投資）", "🛡️ バリュー（割安・高配当）")
)

st.sidebar.subheader("⭐ ウォッチリスト")
selected_from_list = st.sidebar.selectbox(
    "登録銘柄を選択:", 
    st.session_state.watchlist,
    index=st.session_state.watchlist.index(st.session_state.selected_ticker) if st.session_state.selected_ticker in st.session_state.watchlist else 0
)

new_ticker = st.sidebar.text_input("銘柄追加 (例: 9984.T)")
if st.sidebar.button("リストに追加"):
    if new_ticker and new_ticker not in st.session_state.watchlist:
        st.session_state.watchlist.append(new_ticker)
        st.session_state.selected_ticker = new_ticker
        st.rerun()

if st.sidebar.button("選択中の銘柄を削除"):
    if selected_from_list in st.session_state.watchlist:
        st.session_state.watchlist.remove(selected_from_list)
        if st.session_state.watchlist:
            st.session_state.selected_ticker = st.session_state.watchlist[0]
        st.rerun()

current_symbol = selected_from_list

# --- RSI計算 ---
def calculate_rsi(series, period=14):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

# --- データ取得・分析 ---
def analyze_stock(symbol, evaluation_mode):
    try:
        # yfinanceから直接ダウンロード（最もエラーが起きにくい手法）
        df = yf.download(symbol, period="6m", progress=False)
        
        if df.empty:
            return None, f"銘柄コード ({symbol}) のデータ取得に失敗しました。"

        # 多重階層（MultiIndex）カラムの解除
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        # 必須カラムチェック
        if 'Close' not in df.columns:
            return None, "終値データ（Close）が存在しません。"

        # 移動平均線・RSI
        df['Close'] = pd.to_numeric(df['Close'], errors='coerce')
        df['MA5'] = df['Close'].rolling(window=5).mean()
        df['MA25'] = df['Close'].rolling(window=25).mean()
        df['MA75'] = df['Close'].rolling(window=75).mean()
        df['RSI'] = calculate_rsi(df['Close'])

        latest_price = float(df['Close'].iloc[-1])
        ma25 = float(df['MA25'].dropna().iloc[-1]) if not df['MA25'].dropna().empty else latest_price
        ma75 = float(df['MA75'].dropna().iloc[-1]) if not df['MA75'].dropna().empty else latest_price
        latest_rsi = float(df['RSI'].dropna().iloc[-1]) if not df['RSI'].dropna().empty else 50.0

        # 出来高
        vol_change_pct = 0.0
        if 'Volume' in df.columns:
            df['Volume'] = pd.to_numeric(df['Volume'], errors='coerce')
            latest_vol = float(df['Volume'].iloc[-1])
            avg_vol = float(df['Volume'].tail(20).mean())
            if avg_vol > 0:
                vol_change_pct = ((latest_vol - avg_vol) / avg_vol) * 100

        # 銘柄基本情報
        info = {}
        try:
            info = yf.Ticker(symbol).info or {}
        except Exception:
            pass

        company_name = info.get('longName') or info.get('shortName') or symbol
        per = float(info.get('forwardPE') or info.get('trailingPE') or 0)
        pbr = float(info.get('priceToBook') or 0)
        roe = float(info.get('returnOnEquity') or 0) * 100
        revenue_growth = float(info.get('revenueGrowth') or 0) * 100
        operating_margins = float(info.get('operatingMargins') or 0) * 100

        # スコア判定
        score = 0
        plus_reasons = []
        minus_reasons = []

        if "グロース" in evaluation_mode:
            target_period = "🗓️ 想定投資期間: 3年間（株価3倍狙い）"
            if revenue_growth >= 25:
                score += 3
                plus_reasons.append(f"売上成長率 +{revenue_growth:.1f}% (+3点)")
            elif revenue_growth >= 15:
                score += 2
                plus_reasons.append(f"売上成長率 +{revenue_growth:.1f}% (+2点)")

            if operating_margins >= 15:
                score += 2
                plus_reasons.append(f"営業利益率 {operating_margins:.1f}% (+2点)")

            if roe >= 15:
                score += 2
                plus_reasons.append(f"高ROE {roe:.1f}% (+2点)")
        else:
            target_period = "🗓️ 想定投資期間: 1〜2年間（割安修正狙い）"
            if 0 < per < 15:
                score += 2
                plus_reasons.append(f"PER {per:.1f}倍 割安 (+2点)")
            if 0 < pbr < 1.0:
                score += 2
                plus_reasons.append(f"PBR {pbr:.2f}倍 1倍割れ (+2点)")

        if latest_price > ma25 > ma75:
            score += 2
            plus_reasons.append("パーフェクトオーダー上昇気配 (+2点)")
        elif latest_price < ma25 < ma75:
            score -= 2
            minus_reasons.append("下落トレンド傾向 (-2点)")

        if score >= 5:
            judgment = "🚀 強力買い検討 (BUY)"
            judgment_color = "green"
        elif score >= 2:
            judgment = "👀 打診買い・様子見 (NEUTRAL)"
            judgment_color = "orange"
        else:
            judgment = "⚠️ 見送り・売却 (SELL)"
            judgment_color = "red"

        return {
            "company_name": company_name,
            "target_period": target_period,
            "latest_price": latest_price,
            "per": per,
            "pbr": pbr,
            "roe": roe,
            "revenue_growth": revenue_growth,
            "operating_margins": operating_margins,
            "vol_change_pct": vol_change_pct,
            "rsi": latest_rsi,
            "score": score,
            "judgment": judgment,
            "judgment_color": judgment_color,
            "plus_reasons": plus_reasons,
            "minus_reasons": minus_reasons,
            "df": df
        }, None

    except Exception as e:
        return None, str(e)

# --- 画面描画 ---
data, error = analyze_stock(current_symbol, mode)

if error:
    st.error(f"データ取得エラー: {error}")
    st.info("※一時的な通信エラーの可能性があります。画面右下の『Manage app』→『Reboot app』をお試しください。")
else:
    # 銘柄情報
    st.subheader(f"{data['company_name']} ({current_symbol})")
    st.caption(f"{data['target_period']}")

    # 判定
    if data['judgment_color'] == "green":
        st.success(f"### {data['judgment']} ｜ スコア: {data['score']} 点")
    elif data['judgment_color'] == "orange":
        st.warning(f"### {data['judgment']} ｜ スコア: {data['score']} 点")
    else:
        st.error(f"### {data['judgment']} ｜ スコア: {data['score']} 点")

    # チャート（標準の折りたたみ・スッキリ表示）
    st.write("#### 📈 株価・移動平均線推移 (5日・25日・75日)")
    st.line_chart(data['df'][['Close', 'MA5', 'MA25', 'MA75']])

    # 指標タブ表示
    tab1, tab2 = st.tabs(["📊 指標データ", "📝 判定根拠"])

    with tab1:
        c1, c2 = st.columns(2)
        c1.metric("現在株価", f"¥{data['latest_price']:,.0f}")
        c2.metric("出来高変化率", f"{data['vol_change_pct']:+.1f}%")

        c3, c4 = st.columns(2)
        c3.metric("売上成長率 / 営業益率", f"{data['revenue_growth']:.1f}% / {data['operating_margins']:.1f}%")
        c4.metric("PER / RSI(14日)", f"{data['per']:.1f}倍 / {data['rsi']:.1f}")

    with tab2:
        if data['plus_reasons']:
            st.markdown("**🟢 加点材料**")
            for r in data['plus_reasons']:
                st.write(f"- {r}")

        if data['minus_reasons']:
            st.markdown("**🔴 警戒材料**")
            for r in data['minus_reasons']:
                st.write(f"- {r}")
