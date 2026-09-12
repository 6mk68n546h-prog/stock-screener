import streamlit as st
import yfinance as yf
import pandas as pd
from datetime import datetime

# ページ基本設定（スマホ向けに最適化）
st.set_page_config(page_title="株自動判定アプリ", layout="centered")

st.title("📱 株自動判定＆スクリーナー")

# 1. セッション状態（ウォッチリスト・選択銘柄）の初期化
if "watchlist" not in st.session_state:
    st.session_state.watchlist = ["5132.T", "166A.T", "332A.T", "7203.T"]
if "selected_ticker" not in st.session_state:
    st.session_state.selected_ticker = "5132.T"

# --- サイドバー：ウォッチリスト管理 & モード設定 ---
st.sidebar.header("⚙️ 設定・ウォッチリスト")

# 評価モード切替
mode = st.sidebar.radio(
    "評価モードを選択:",
    ("🚀 グロース（成長株）モード", "🛡️ バリュー（割安・高配当）モード")
)

# ウォッチリストからの選択
st.sidebar.subheader("⭐ ウォッチリスト")
selected_from_list = st.sidebar.selectbox(
    "登録銘柄を選択:", 
    st.session_state.watchlist,
    index=st.session_state.watchlist.index(st.session_state.selected_ticker) if st.session_state.selected_ticker in st.session_state.watchlist else 0
)

# 新規銘柄追加フォーム
new_ticker = st.sidebar.text_input("銘柄追加 (例: 9984.T, AAPL)")
if st.sidebar.button("リストに追加"):
    if new_ticker and new_ticker not in st.session_state.watchlist:
        st.session_state.watchlist.append(new_ticker)
        st.session_state.selected_ticker = new_ticker
        st.rerun()

# 削除ボタン
if st.sidebar.button("選択中の銘柄を削除"):
    if selected_from_list in st.session_state.watchlist:
        st.session_state.watchlist.remove(selected_from_list)
        if st.session_state.watchlist:
            st.session_state.selected_ticker = st.session_state.watchlist[0]
        st.rerun()

# 手動入力または選択された銘柄コードの確定
current_symbol = selected_from_list

# --- 判定メイン処理機能 ---
def analyze_stock(symbol, evaluation_mode):
    try:
        stock = yf.Ticker(symbol)
        info = stock.info
        
        # 過去データ取得（1年分）
        hist = stock.history(period="1y")
        if hist.empty:
            return None, "データが取得できませんでした。銘柄コードを確認してください。"
        
        # 移動平均線
        hist['SMA25'] = hist['Close'].rolling(window=25).mean()
        hist['SMA75'] = hist['Close'].rolling(window=75).mean()
        
        latest_price = hist['Close'].iloc[-1]
        sma25 = hist['SMA25'].iloc[-1]
        sma75 = hist['SMA75'].iloc[-1]
        
        # 出来高増減率の計算（直近出来高 vs 20日平均出来高）
        latest_volume = hist['Volume'].iloc[-1]
        avg_volume_20d = hist['Volume'].tail(20).mean()
        vol_change_pct = ((latest_volume - avg_volume_20d) / avg_volume_20d) * 100 if avg_volume_20d > 0 else 0

        # IR・適時開示更新日情報の取得
        news = stock.news
        latest_news_date_str = "データなし"
        days_since_last_ir = None
        
        if news and len(news) > 0:
            # 最も新しいニュース/適時開示のタイムスタンプ
            pub_time = news[0].get('providerPublishTime')
            if pub_time:
                latest_date = datetime.fromtimestamp(pub_time)
                latest_news_date_str = latest_date.strftime('%Y-%m-%d')
                days_since_last_ir = (datetime.now() - latest_date).days

        # 指標抽出
        per = info.get('forwardPE') or info.get('trailingPE') or 0
        pbr = info.get('priceToBook') or 0
        roe = (info.get('returnOnEquity') or 0) * 100
        dividend_yield = (info.get('dividendYield') or 0) * 100
        revenue_growth = (info.get('revenueGrowth') or 0) * 100
        company_name = info.get('longName') or info.get('shortName') or symbol

        # --- スコアリングロジック ---
        score = 0
        reasons = []

        # ① 出来高判定（共通）
        if vol_change_pct >= 50:
            score += 2
            reasons.append(f"🔥 【出来高急増】直近出来高が20日平均比 +{vol_change_pct:.1f}% （関心・資金流入大）")
        elif vol_change_pct <= -50:
            score -= 1
            reasons.append(f"🧊 【出来高過疎】直近出来高が20日平均比 {vol_change_pct:.1f}% （関心薄）")

        # ② IR更新頻度判定（共通）
        if days_since_last_ir is not None:
            if days_since_last_ir <= 7:
                score += 1
                reasons.append(f"📢 【IR活発】7日以内に最新の開示/ニュースあり ({latest_news_date_str})")
            elif days_since_last_ir > 60:
                reasons.append(f"💤 【IR停滞】直近の開示から60日以上経過 ({latest_news_date_str})")

        # ③ テクニカル判定（共通）
        if latest_price > sma25 > sma75:
            score += 2
            reasons.append("📈 【好チャート】25日・75日移動平均線を上回るきれいな上昇トレンド")
        elif latest_price < sma25 < sma75:
            score -= 2
            reasons.append("📉 【弱気チャート】25日・75日移動平均線を下回る下落トレンド")

        # ④ モード別評価ロジック
        if "グロース" in evaluation_mode:
            # グロースモード：売上成長率・ROE・出来高重視（PERが高くても許容）
            if revenue_growth >= 20:
                score += 2
                reasons.append(f"🚀 【高成長】売上高成長率が前年比 +{revenue_growth:.1f}%")
            if roe >= 15:
                score += 2
                reasons.append(f"高効率性: ROE {roe:.1f}% (資本効率が非常に高い)")
            if per > 50:
                reasons.append(f"⚠️ 留意: PER {per:.1f}倍 (期待先行の割高ゾーン)")
        else:
            # バリューモード：PER・PBR・配当利回り重視
            if 0 < per < 15:
                score += 2
                reasons.append(f"💎 【割安】PERが15倍未満 (実測: {per:.1f}倍)")
            if 0 < pbr < 1.0:
                score += 2
                reasons.append(f"🛡️ 【PBR1倍割れ】資産面で割安 (実測: {pbr:.2f}倍)")
            if dividend_yield >= 3.5:
                score += 1
                reasons.append(f"💰 【高配当】配当利回り {dividend_yield:.2f}%")

        # 総合判別
        if score >= 4:
            judgment = "BUY（強気・買い検討）"
            judgment_color = "green"
        elif score <= -2:
            judgment = "SELL（弱気・売り検討）"
            judgment_color = "red"
        else:
            judgment = "HOLD / NEUTRAL（様子見）"
            judgment_color = "orange"

        return {
            "company_name": company_name,
            "latest_price": latest_price,
            "per": per,
            "pbr": pbr,
            "roe": roe,
            "vol_change_pct": vol_change_pct,
            "latest_news_date": latest_news_date_str,
            "score": score,
            "judgment": judgment,
            "judgment_color": judgment_color,
            "reasons": reasons,
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
    
    # 総合判定ハイライト
    if data['judgment_color'] == "green":
        st.success(f"### 総合判定: {data['judgment']}\n**スコア: {data['score']} 点**")
    elif data['judgment_color'] == "red":
        st.error(f"### 総合判定: {data['judgment']}\n**スコア: {data['score']} 点**")
    else:
        st.warning(f"### 総合判定: {data['judgment']}\n**スコア: {data['score']} 点**")

    # 主要指標グリッド（スマホで見やすい2列表示）
    col1, col2 = st.columns(2)
    col1.metric("現在株価", f"¥{data['latest_price']:,.0f}")
    col2.metric("出来高変化(対20日平均)", f"{data['vol_change_pct']:+.1f}%")
    
    col3, col4 = st.columns(2)
    col3.metric("PER / PBR", f"{data['per']:.1f}倍 / {data['pbr']:.2f}倍")
    col4.metric("直近IR/ニュース日", data['latest_news_date'])

    # 判定根拠
    st.write("#### 判定の根拠・シグナル:")
    for reason in data['reasons']:
        st.write(f"- {reason}")

    # 株価推移チャート
    st.write("#### 株価・移動平均線推移")
    st.line_chart(data['hist'][['Close', 'SMA25', 'SMA75']])
