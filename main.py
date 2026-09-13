import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# ページ基本設定
st.set_page_config(page_title="高機能・集中投資スクリーナー", layout="centered")

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

# --- テクニカル計算関数 ---
def calculate_rsi(series, period=14):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

# --- メイン分析処理 ---
def analyze_stock(symbol, evaluation_mode):
    try:
        # Tickerデータ取得
        stock = yf.Ticker(symbol)
        hist = stock.history(period="6m")

        # 1. データ存在チェック
        if hist is None or hist.empty:
            return None, f"銘柄コード ({symbol}) の株価データを取得できませんでした。コードを確認してください。"

        # 2. yfinanceのMultiIndex構造を確実に単一層へ平坦化
        if isinstance(hist.columns, pd.MultiIndex):
            hist.columns = [col[0] for col in hist.columns]

        # 3. 列名の標準化と必須列チェック
        hist = hist.loc[:, ~hist.columns.duplicated()] # 重複列の除去
        
        for col in ['Open', 'High', 'Low', 'Close', 'Volume']:
            if col not in hist.columns:
                return None, f"必要な価格データ ({col}) が見つかりませんでした。"

        # テクニカル指標計算
        hist['Close'] = pd.to_numeric(hist['Close'], errors='coerce')
        hist['MA5'] = hist['Close'].rolling(window=5).mean()
        hist['MA25'] = hist['Close'].rolling(window=25).mean()
        hist['MA75'] = hist['Close'].rolling(window=75).mean()
        hist['RSI'] = calculate_rsi(hist['Close'])
        hist['High50'] = hist['Close'].rolling(window=50).max()

        latest_price = float(hist['Close'].iloc[-1])
        ma25 = float(hist['MA25'].dropna().iloc[-1]) if not hist['MA25'].dropna().empty else latest_price
        ma75 = float(hist['MA75'].dropna().iloc[-1]) if not hist['MA75'].dropna().empty else latest_price
        latest_rsi = float(hist['RSI'].dropna().iloc[-1]) if not hist['RSI'].dropna().empty else 50.0
        
        high_50d_series = hist['High50'].dropna()
        high_50d = float(high_50d_series.iloc[-2]) if len(high_50d_series) >= 2 else latest_price

        # 出来高計算
        hist['Volume'] = pd.to_numeric(hist['Volume'], errors='coerce')
        latest_volume = float(hist['Volume'].iloc[-1])
        avg_volume_20d = float(hist['Volume'].tail(20).mean())
        vol_change_pct = ((latest_volume - avg_volume_20d) / avg_volume_20d) * 100 if avg_volume_20d > 0 else 0.0

        # ファンダメンタルズ情報
        info = {}
        try:
            info = stock.info or {}
        except Exception:
            pass

        company_name = info.get('longName') or info.get('shortName') or symbol
        per = float(info.get('forwardPE') or info.get('trailingPE') or 0)
        pbr = float(info.get('priceToBook') or 0)
        roe = float(info.get('returnOnEquity') or 0) * 100
        dividend_yield = float(info.get('dividendYield') or 0) * 100
        revenue_growth = float(info.get('revenueGrowth') or 0) * 100
        operating_margins = float(info.get('operatingMargins') or 0) * 100

        # IR・ニュース情報
        latest_news_date_str = "データなし"
        days_since_last_ir = None
        try:
            news = stock.news
            if news and len(news) > 0:
                pub_time = news[0].get('providerPublishTime')
                if pub_time:
                    latest_date = datetime.fromtimestamp(pub_time)
                    latest_news_date_str = latest_date.strftime('%Y-%m-%d')
                    days_since_last_ir = (datetime.now() - latest_date).days
        except Exception:
            pass

        # スコアリング
        score = 0
        plus_reasons = []
        minus_reasons = []

        if "グロース" in evaluation_mode:
            target_period = "🗓️ 想定投資期間: 3年間（株価3倍・集中投資）"
            if revenue_growth >= 25:
                score += 3
                plus_reasons.append(f"売上高成長率 +{revenue_growth:.1f}% (超高成長: +3点)")
            elif revenue_growth >= 15:
                score += 2
                plus_reasons.append(f"売上高成長率 +{revenue_growth:.1f}% (順調な成長: +2点)")
            elif revenue_growth < 0:
                score -= 2
                minus_reasons.append(f"売上高減収傾向 ({revenue_growth:.1f}%: -2点)")

            if operating_margins >= 15:
                score += 2
                plus_reasons.append(f"高営業利益率 {operating_margins:.1f}% (高収益性: +2点)")

            if roe >= 15:
                score += 2
                plus_reasons.append(f"高ROE {roe:.1f}% (高資本効率: +2点)")

            if 0 < per < revenue_growth and revenue_growth > 15:
                score += 2
                plus_reasons.append(f"PER {per:.1f}倍 < 成長率 {revenue_growth:.1f}% (再評価余地: +2点)")
        else:
            target_period = "🗓️ 想定投資期間: 1〜2年間（割安修正・配当享受）"
            if 0 < per < 15:
                score += 2
                plus_reasons.append(f"PER {per:.1f}倍 (割安水準: +2点)")
            if 0 < pbr < 1.0:
                score += 2
                plus_reasons.append(f"PBR {pbr:.2f}倍 (解散価値以下: +2点)")
            if dividend_yield >= 3.5:
                score += 2
                plus_reasons.append(f"高配当利回り {dividend_yield:.2f}%: +2点")

        if latest_price >= high_50d:
            score += 2
            plus_reasons.append("過去50日高値ブレイクアウト (+2点)")

        if latest_price > ma25 > ma75:
            score += 2
            plus_reasons.append("パーフェクトオーダー上昇トレンド (+2点)")
        elif latest_price < ma25 < ma75:
            score -= 3
            minus_reasons.append("下落トレンド形成 (-3点)")

        if 50 <= latest_rsi <= 65:
            score += 1
            plus_reasons.append(f"RSI {latest_rsi:.1f} (上昇モメンタム適温: +1点)")
        elif latest_rsi >= 75:
            score -= 1
            minus_reasons.append(f"RSI {latest_rsi:.1f} (短期過熱: -1点)")

        if vol_change_pct >= 50:
            score += 2
            plus_reasons.append(f"出来高急増 +{vol_change_pct:.1f}% (+2点)")
        elif vol_change_pct <= -40:
            score -= 1
            minus_reasons.append(f"出来高過疎 {vol_change_pct:.1f}% (-1点)")

        if days_since_last_ir is not None and days_since_last_ir <= 7:
            score += 1
            plus_reasons.append(f"7日以内に開示情報あり ({latest_news_date_str}: +1点)")

        if score >= 6:
            judgment = "🚀 強力買い検討 (BUY)"
            judgment_color = "green"
        elif score >= 3:
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
            "latest_news_date": latest_news_date_str,
            "score": score,
            "judgment": judgment,
            "judgment_color": judgment_color,
            "plus_reasons": plus_reasons,
            "minus_reasons": minus_reasons,
            "hist": hist
        }, None

    except Exception as e:
        return None, f"処理エラーが発生しました: {str(e)}"

# --- 画面レイアウト構築 ---
data, error = analyze_stock(current_symbol, mode)

if error:
    st.error(f"エラー: {error}")
else:
    # 銘柄ヘッダーと想定期間
    st.subheader(f"{data['company_name']} ({current_symbol})")
    st.caption(f"{data['target_period']}")
    
    # 総合判定カード
    if data['judgment_color'] == "green":
        st.success(f"### {data['judgment']} ｜ スコア: {data['score']} 点")
    elif data['judgment_color'] == "orange":
        st.warning(f"### {data['judgment']} ｜ スコア: {data['score']} 点")
    else:
        st.error(f"### {data['judgment']} ｜ スコア: {data['score']} 点")

    # 本格ローソク足チャート (証券アプリ風)
    df_chart = data['hist'].tail(90)
    
    fig = make_subplots(
        rows=2, cols=1, 
        shared_xaxes=True, 
        vertical_spacing=0.03, 
        row_heights=[0.7, 0.3]
    )

    # ローソク足
    fig.add_trace(go.Candlestick(
        x=df_chart.index,
        open=df_chart['Open'],
        high=df_chart['High'],
        low=df_chart['Low'],
        close=df_chart['Close'],
        name="株価",
        increasing_line_color='#ef5350', # 陽線：赤
        decreasing_line_color='#26a69a'  # 陰線：緑
    ), row=1, col=1)

    # 移動平均線
    fig.add_trace(go.Scatter(x=df_chart.index, y=df_chart['MA5'], mode='lines', name='MA5', line=dict(color='#e91e63', width=1.5)), row=1, col=1)
    fig.add_trace(go.Scatter(x=df_chart.index, y=df_chart['MA25'], mode='lines', name='MA25', line=dict(color='#4caf50', width=1.5)), row=1, col=1)
    fig.add_trace(go.Scatter(x=df_chart.index, y=df_chart['MA75'], mode='lines', name='MA75', line=dict(color='#2196f3', width=1.5)), row=1, col=1)

    # 出来高
    fig.add_trace(go.Bar(
        x=df_chart.index, 
        y=df_chart['Volume'], 
        name="出来高", 
        marker_color='#ff9800'
    ), row=2, col=1)

    # チャートデザイン
    fig.update_layout(
        template="plotly_dark",
        height=420,
        margin=dict(l=10, r=10, t=20, b=10),
        showlegend=True,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        xaxis_rangeslider_visible=False
    )
    
    st.plotly_chart(fig, use_container_width=True)

    # タブ切り替え
    tab1, tab2 = st.tabs(["📊 指標データ", "📝 判定根拠・シグナル"])

    with tab1:
        col1, col2 = st.columns(2)
        col1.metric("現在株価", f"¥{data['latest_price']:,.0f}")
        col2.metric("出来高変化率", f"{data['vol_change_pct']:+.1f}%")
        
        col3, col4 = st.columns(2)
        col3.metric("売上成長率 / 営業利益率", f"{data['revenue_growth']:.1f}% / {data['operating_margins']:.1f}%")
        col4.metric("PER / RSI(14日)", f"{data['per']:.1f}倍 / {data['rsi']:.1f}")

    with tab2:
        if data['plus_reasons']:
            st.markdown("**🟢 加点材料 (買いシグナル)**")
            for r in data['plus_reasons']:
                st.write(f"- {r}")
                
        if data['minus_reasons']:
            st.markdown("**🔴 減点材料 (リスクシグナル)**")
            for r in data['minus_reasons']:
                st.write(f"- {r}")
