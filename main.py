import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime

# ページ基本設定
st.set_page_config(page_title="高機能・集中投資スクリーナー", layout="centered")

st.title("📱 集中投資向け・高機能株自動判定アプリ")

# 1. セッション状態の初期化
if "watchlist" not in st.session_state:
    st.session_state.watchlist = ["5132.T", "166A.T", "332A.T", "7203.T"]
if "selected_ticker" not in st.session_state:
    st.session_state.selected_ticker = "5132.T"

# --- サイドバー ---
st.sidebar.header("⚙️ 設定・ウォッチリスト")

mode = st.sidebar.radio(
    "評価モードを選択:",
    ("🚀 グロース（3年3倍・集中投資）モード", "🛡️ バリュー（割安・高配当）モード")
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

# --- テクニカル計算関数 ---
def calculate_rsi(series, period=14):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

# --- メイン判定ロジック ---
def analyze_stock(symbol, evaluation_mode):
    try:
        stock = yf.Ticker(symbol)
        info = stock.info
        
        hist = stock.history(period="1y")
        if hist.empty:
            return None, "データが取得できませんでした。銘柄コードを確認してください。"
        
        # テクニカル指標計算
        hist['SMA25'] = hist['Close'].rolling(window=25).mean()
        hist['SMA75'] = hist['Close'].rolling(window=75).mean()
        hist['RSI'] = calculate_rsi(hist['Close'])
        hist['High50'] = hist['Close'].rolling(window=50).max()
        
        latest_price = hist['Close'].iloc[-1]
        sma25 = hist['SMA25'].iloc[-1]
        sma75 = hist['SMA75'].iloc[-1]
        latest_rsi = hist['RSI'].iloc[-1]
        high_50d = hist['High50'].iloc[-2] if len(hist) > 50 else latest_price
        
        # 出来高増減率
        latest_volume = hist['Volume'].iloc[-1]
        avg_volume_20d = hist['Volume'].tail(20).mean()
        vol_change_pct = ((latest_volume - avg_volume_20d) / avg_volume_20d) * 100 if avg_volume_20d > 0 else 0

        # IR・ニュース日取得
        news = stock.news
        latest_news_date_str = "データなし"
        days_since_last_ir = None
        if news and len(news) > 0:
            pub_time = news[0].get('providerPublishTime')
            if pub_time:
                latest_date = datetime.fromtimestamp(pub_time)
                latest_news_date_str = latest_date.strftime('%Y-%m-%d')
                days_since_last_ir = (datetime.now() - latest_date).days

        # ファンダメンタルズ指標
        per = info.get('forwardPE') or info.get('trailingPE') or 0
        pbr = info.get('priceToBook') or 0
        roe = (info.get('returnOnEquity') or 0) * 100
        dividend_yield = (info.get('dividendYield') or 0) * 100
        revenue_growth = (info.get('revenueGrowth') or 0) * 100
        operating_margins = (info.get('operatingMargins') or 0) * 100
        company_name = info.get('longName') or info.get('shortName') or symbol

        # --- スコアリングロジック ---
        score = 0
        plus_reasons = []
        minus_reasons = []

        # 想定投資期間の定義
        if "グロース" in evaluation_mode:
            target_period = "🗓️ 想定投資期間: 3年間（株価3倍・集中投資を想定）"
            if revenue_growth >= 25:
                score += 3
                plus_reasons.append(f"売上高成長率 +{revenue_growth:.1f}% (超高成長バイアス: +3点)")
            elif revenue_growth >= 15:
                score += 2
                plus_reasons.append(f"売上高成長率 +{revenue_growth:.1f}% (順調な成長: +2点)")
            elif revenue_growth < 0:
                score -= 2
                minus_reasons.append(f"売上高が減収傾向 ({revenue_growth:.1f}%: -2点)")

            if operating_margins >= 15:
                score += 2
                plus_reasons.append(f"高営業利益率 {operating_margins:.1f}% (高い稼ぐ力: +2点)")

            if roe >= 15:
                score += 2
                plus_reasons.append(f"高ROE {roe:.1f}% (資本効率が非常に高い: +2点)")

            if 0 < per < revenue_growth and revenue_growth > 15:
                score += 2
                plus_reasons.append(f"PER {per:.1f}倍 < 成長率 {revenue_growth:.1f}% (PEG1倍割れ・再評価余地大: +2点)")
        else:
            target_period = "🗓️ 想定投資期間: 1〜2年間（見直し買い・配当享受を想定）"
            if 0 < per < 15:
                score += 2
                plus_reasons.append(f"PER {per:.1f}倍 (15倍未満の割安水準: +2点)")
            if 0 < pbr < 1.0:
                score += 2
                plus_reasons.append(f"PBR {pbr:.2f}倍 (1倍割れ解散価値以下: +2点)")
            if dividend_yield >= 3.5:
                score += 2
                plus_reasons.append(f"高配当利回り {dividend_yield:.2f}% (インカムゲイン魅力: +2点)")

        # テクニカル・モメンタム評価
        if latest_price >= high_50d:
            score += 2
            plus_reasons.append("過去50日高値をブレイクアウト (青天井・上昇推進力: +2点)")

        if latest_price > sma25 > sma75:
            score += 2
            plus_reasons.append("パーフェクトオーダー (25日・75日移動平均線が右肩上がり: +2点)")
        elif latest_price < sma25 < sma75:
            score -= 3
            minus_reasons.append("明確な下落トレンド (移動平均線の下抜け: -3点)")

        if 50 <= latest_rsi <= 65:
            score += 1
            plus_reasons.append(f"RSI {latest_rsi:.1f} (理想的な買われ方の強さ: +1点)")
        elif latest_rsi >= 75:
            score -= 1
            minus_reasons.append(f"RSI {latest_rsi:.1f} (短期的な過熱・過度の買われすぎ: -1点)")

        # 出来高＆IR更新頻度
        if vol_change_pct >= 50:
            score += 2
            plus_reasons.append(f"出来高急増 +{vol_change_pct:.1f}% (機関投資家・資金流入の兆候: +2点)")
        elif vol_change_pct <= -40:
            score -= 1
            minus_reasons.append(f"出来高過疎 {vol_change_pct:.1f}% (市場の関心低下: -1点)")

        if days_since_last_ir is not None and days_since_last_ir <= 7:
            score += 1
            plus_reasons.append(f"直近7日以内にIR/適時開示あり ({latest_news_date_str}: +1点)")

        # 総合判定
        if score >= 6:
            judgment = "🚀 強力な買い検討 (BUY)"
            judgment_color = "green"
        elif score >= 3:
            judgment = "👀 打診買い・様子見 (NEUTRAL/ACCUMULATE)"
            judgment_color = "orange"
        else:
            judgment = "⚠️ 見送り・売却検討 (SELL/AVOID)"
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
            "latest_news_date": latest_news_date_str,
            "score": score,
            "judgment": judgment,
            "judgment_color": judgment_color,
            "plus_reasons": plus_reasons,
            "minus_reasons": minus_reasons,
            "hist": hist
        }, None

    except Exception as e:
        return None, str(e)

# --- 画面描画 ---
st.caption(f"現在の選択モード: **{mode}**")
data, error = analyze_stock(current_symbol, mode)

if error:
    st.error(f"エラー: {error}")
else:
    st.subheader(f"{data['company_name']} ({current_symbol})")
    
    # 想定投資期間の表示
    st.info(data['target_period'])
    
    # 総合判定
    if data['judgment_color'] == "green":
        st.success(f"### {data['judgment']}\n**総合投資スコア: {data['score']} 点**")
    elif data['judgment_color'] == "orange":
        st.warning(f"### {data['judgment']}\n**総合投資スコア: {data['score']} 点**")
    else:
        st.error(f"### {data['judgment']}\n**総合投資スコア: {data['score']} 点**")

    # 主要数値指標
    col1, col2 = st.columns(2)
    col1.metric("現在株価", f"¥{data['latest_price']:,.0f}")
    col2.metric("出来高変化(対20日平均)", f"{data['vol_change_pct']:+.1f}%")
    
    col3, col4 = st.columns(2)
    col3.metric("売上高成長率 / 営業利益率", f"{data['revenue_growth']:.1f}% / {data['operating_margins']:.1f}%")
    col4.metric("PER / RSI(14日)", f"{data['per']:.1f}倍 / {data['rsi']:.1f}")

    # スコア算出の根拠解説
    st.write("---")
    st.write("### 📊 投資判定の根拠・内訳")
    
    if data['plus_reasons']:
        st.write("🟢 **加点シグナル (買い材料):**")
        for r in data['plus_reasons']:
            st.write(f"- {r}")
            
    if data['minus_reasons']:
        st.write("🔴 **減点・リスクシグナル (警戒材料):**")
        for r in data['minus_reasons']:
            st.write(f"- {r}")

    # 株価チャート
    st.write("---")
    st.write("#### 株価・移動平均線推移 (1年間)")
    st.line_chart(data['hist'][['Close', 'SMA25', 'SMA75']])
