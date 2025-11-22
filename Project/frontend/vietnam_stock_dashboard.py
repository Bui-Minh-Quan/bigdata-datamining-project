"""
Unified Dashboard: Kafka (Realtime) + MongoDB (AI/News/Price) + Neo4j (Graph)
Visualization: 
- Advanced Directed Graph with Arrowheads.
- Impact Coloring (Red/Green).
- Node Labels (Title for Articles).
- 2-Hop Neighbor Search.
"""
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import networkx as nx
from plotly.subplots import make_subplots
from datetime import datetime, timedelta

import json
import threading
import queue
import time
import sys
import os
import math

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(ROOT_DIR)
from database.db import get_database

# --- 1. CẤU HÌNH HỆ THỐNG ---
os.environ["PYTHONIOENCODING"] = "utf-8"
try:
    from kafka import KafkaConsumer
    KAFKA_AVAILABLE = True
except ImportError:
    KAFKA_AVAILABLE = False

from neo4j import GraphDatabase
from vnstock import Quote 
from pymongo import MongoClient

st.set_page_config(page_title="🚀 Vietnam Stock AI Dashboard", layout="wide", page_icon="📈")
st.markdown("""<style>.stMetric {animation: none !important;} div[data-testid='stMetricValue'] {font-size: 22px; color: #333;} .css-1d391kg {padding-top: 1rem;}</style>""", unsafe_allow_html=True)

VIETNAM_STOCKS = {
    'FPT - Công nghệ FPT': 'FPT', 'SSI - Chứng khoán SSI': 'SSI', 'VCB - Vietcombank': 'VCB', 
    'VHM - Vinhomes': 'VHM', 'HPG - Hòa Phát': 'HPG', 'GAS - PV Gas': 'GAS',
    'MSN - Masan Group': 'MSN', 'MWG - Thế Giới Di Động': 'MWG', 'GVR - Tập đoàn Cao su': 'GVR', 'VIC - Vingroup': 'VIC'
}

# ==========================================
# 2. DATA ACCESS LAYER
# ==========================================
@st.cache_resource
def init_mongo():
    return get_database()

def get_stock_history_hybrid(symbol, days=90):
    try:
        end_date = datetime.now().strftime('%Y-%m-%d')
        start_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
        quote = Quote(symbol=symbol.upper(),  source='vci')
        df = quote.history(start=start_date, end=end_date, interval='1D')
        if df is not None and not df.empty:
            df = df.rename(columns={'time': 'Date', 'open': 'Open', 'high': 'High', 'low': 'Low', 'close': 'Close', 'volume': 'Volume'})
            if df['Close'].iloc[-1] < 500: 
                for col in ['Open', 'High', 'Low', 'Close']: df[col] = df[col] * 1000
            return df, "☁️ Online (TCBS)"
    except: pass

    try:
        db = init_mongo()
        if db:
            col = db['stock_price_data']
            cursor = col.find({"symbol": symbol}).sort("time", 1)
            data = list(cursor)
            if data:
                df = pd.DataFrame(data)
                df = df.rename(columns={'time': 'Date', 'open': 'Open', 'high': 'High', 'low': 'Low', 'close': 'Close', 'volume': 'Volume'})
                df['Date'] = pd.to_datetime(df['Date'])
                cutoff_date = datetime.now() - timedelta(days=days)
                df = df[df['Date'] >= cutoff_date]
                if not df.empty:
                    if df['Close'].iloc[-1] < 500: 
                        for col in ['Open', 'High', 'Low', 'Close']: df[col] = df[col] * 1000
                    return df, "💾 Database (MongoDB)"
    except: pass
    return pd.DataFrame(), "❌ Không có dữ liệu"

def get_ai_prediction(symbol):
    db = init_mongo()
    if db is None: return None
    return db['stock_predictions'].find_one({"symbol": symbol}, sort=[("date", -1), ("created_at", -1)])

def get_news(symbol):
    db = init_mongo()
    if db is None: return []
    return list(db['summarized_news'].find({"stockCodes": symbol}).sort("date", -1).limit(10))

def get_neo4j_data(symbol):
    """
    Query lấy dữ liệu đồ thị mở rộng (1-2 hops) để thấy tác động gián tiếp.
    Lấy đầy đủ thuộc tính impact, description, title, name.
    """
    try:
        driver = GraphDatabase.driver("bolt://localhost:7687", auth=("neo4j", "password123"))
        with driver.session() as session:
            # Query tìm đường đi độ dài 1 đến 2 từ/đến Stock
            # UNWIND để làm phẳng danh sách các cạnh
            q = """
            MATCH (s:Stock {name: $sym})
            MATCH path = (s)-[*1..2]-(n)
            UNWIND relationships(path) as r
            WITH startNode(r) as source, endNode(r) as target, r
            RETURN DISTINCT
                source.name as src_name, labels(source) as src_labels, source.title as src_title,
                target.name as tgt_name, labels(target) as tgt_labels, target.title as tgt_title,
                type(r) as rel_type, 
                r.impact as impact, 
                r.description as description, 
                r.date as date
            LIMIT 50
            """
            return session.run(q, sym=symbol).data()
    except Exception as e:
        print(f"Neo4j Error: {e}")
        return []

# ==========================================
# 3. ADVANCED GRAPH VISUALIZATION
# ==========================================

def shorten_text(text, max_len=20):
    if not text: return "Unknown"
    return text[:max_len] + "..." if len(text) > max_len else text

def create_network_graph(data, center_node_id):
    if not data: return None

    G = nx.DiGraph() # Đồ thị có hướng
    
    # Màu sắc Node
    node_colors_map = {
        'Stock': '#FF4B4B',      # Đỏ đậm
        'Article': '#1E90FF',    # Xanh dương
        'Entity': '#2E8B57',     # Xanh lá
        'Unknown': '#808080'
    }
    
    # Màu sắc Edge (Impact)
    edge_colors_map = {
        'POSITIVE': '#00CC00',   # Xanh lá tươi
        'NEGATIVE': '#FF0000',   # Đỏ tươi
        'RELATED': '#AAAAAA'     # Xám
    }

    # 1. Xây dựng Graph từ Data
    for item in data:
        # Xử lý Source Node
        src_labels = item.get('src_labels', [])
        src_type = 'Article' if 'Article' in src_labels else ('Stock' if 'Stock' in src_labels else 'Entity')
        src_name = item.get('src_title') if src_type == 'Article' else item.get('src_name')
        if not src_name: src_name = "Unknown"
        
        # Xử lý Target Node
        tgt_labels = item.get('tgt_labels', [])
        tgt_type = 'Article' if 'Article' in tgt_labels else ('Stock' if 'Stock' in tgt_labels else 'Entity')
        tgt_name = item.get('tgt_title') if tgt_type == 'Article' else item.get('tgt_name')
        if not tgt_name: tgt_name = "Unknown"
        
        # Xử lý Edge
        impact = item.get('impact', 'RELATED')
        if not impact: impact = 'RELATED'
        desc = item.get('description', '')
        date = item.get('date', '')
        
        # Add Nodes
        G.add_node(src_name, type=src_type, color=node_colors_map.get(src_type, '#888'), full_name=src_name)
        G.add_node(tgt_name, type=tgt_type, color=node_colors_map.get(tgt_type, '#888'), full_name=tgt_name)
        
        # Add Edge (có hướng)
        G.add_edge(src_name, tgt_name, 
                   color=edge_colors_map.get(impact, '#888'),
                   desc=f"[{impact}] {desc} ({date})")

    # 2. Tính toán Layout
    pos = nx.spring_layout(G, k=0.7, iterations=60, seed=42)

    # 3. Vẽ Edges (Tách thành 3 nhóm màu để vẽ Legend nếu cần, ở đây vẽ gộp nhưng chỉnh màu từng line)
    # Plotly không hỗ trợ màu từng dòng trong 1 trace tối ưu, nên ta vẽ mũi tên bằng Annotations
    
    edge_traces = []
    # Vẽ đường thẳng (Edge lines) - mờ hơn để làm nền cho mũi tên
    for edge in G.edges(data=True):
        x0, y0 = pos[edge[0]]
        x1, y1 = pos[edge[1]]
        color = edge[2]['color']
        desc = edge[2]['desc']
        
        trace = go.Scatter(
            x=[x0, x1, None], y=[y0, y1, None],
            line=dict(width=1.5, color=color),
            hoverinfo='text',
            text=[desc, desc, ""],
            mode='lines',
            opacity=0.8,
            showlegend=False
        )
        edge_traces.append(trace)

    # 4. Vẽ Nodes
    node_x, node_y, node_text, node_colors, node_sizes, node_labels = [], [], [], [], [], []
    
    for node in G.nodes(data=True):
        x, y = pos[node[0]]
        node_x.append(x); node_y.append(y)
        
        n_type = node[1].get('type', 'Unknown')
        full_name = node[1].get('full_name', '')
        
        # Label hiển thị trên đồ thị (ngắn gọn)
        label_show = shorten_text(full_name, 25) if n_type == 'Article' else full_name
        node_labels.append(label_show)
        
        # Tooltip (chi tiết)
        hover_str = f"<b>{full_name}</b><br>Type: {n_type}"
        node_text.append(hover_str)
        
        node_colors.append(node[1].get('color', '#888'))
        # Node trung tâm (Stock) to hơn
        size = 40 if n_type == 'Stock' else (25 if n_type == 'Entity' else 20)
        node_sizes.append(size)

    node_trace = go.Scatter(
        x=node_x, y=node_y,
        mode='markers+text', # Hiển thị cả chấm và tên
        text=node_labels,
        textposition="bottom center",
        hoverinfo='text',
        hovertext=node_text,
        marker=dict(
            showscale=False, 
            color=node_colors, 
            size=node_sizes, 
            line_width=2, 
            line_color='white'
        ),
        textfont=dict(size=10, color='#333')
    )

    # 5. Tạo Mũi tên (Annotations) để chỉ hướng
    annotations = []
    for edge in G.edges(data=True):
        x0, y0 = pos[edge[0]]
        x1, y1 = pos[edge[1]]
        color = edge[2]['color']
        
        # Tính toán điểm để mũi tên không bị node che khuất (lùi lại một chút từ đích)
        # Vector chỉ hướng
        dx = x1 - x0
        dy = y1 - y0
        length = math.sqrt(dx*dx + dy*dy)
        if length == 0: length = 1
        
        # Khoảng cách lùi lại (tùy chỉnh theo size node đích)
        # Giả sử node size ~ 0.05 đơn vị toạ độ
        offset = 0.04 
        new_x1 = x1 - (dx / length) * offset
        new_y1 = y1 - (dy / length) * offset
        
        annotations.append(dict(
            ax=x0, ay=y0, axref='x', ayref='y',
            x=new_x1, y=new_y1, xref='x', yref='y',
            showarrow=True,
            arrowhead=2, # Kiểu mũi tên nhọn
            arrowsize=1.5,
            arrowwidth=1.5,
            arrowcolor=color,
            opacity=0.9
        ))

    # 6. Tạo Layout
    fig = go.Figure(data=edge_traces + [node_trace],
             layout=go.Layout(
                title=dict(text=f"Mạng lưới tác động của {center_node_id}", font=dict(size=16)),
                showlegend=False,
                hovermode='closest',
                margin=dict(b=20,l=5,r=5,t=40),
                annotations=annotations, # Thêm mũi tên
                xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
                yaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
                height=700, 
                plot_bgcolor='white'
             ))
    
    # Legend giả (vẽ bằng HTML ở ngoài hoặc annotation, ở đây dùng annotation góc)
    fig.add_annotation(text="🔴: Stock | 🔵: Article | 🟢: Entity<br>Lines: 🟢 Positive | 🔴 Negative", 
                       align='left', showarrow=False, xref='paper', yref='paper', x=0, y=1, 
                       bordercolor='black', borderwidth=1, bgcolor='white', opacity=0.8)

    return fig

# ==========================================
# 4. KAFKA WORKER
# ==========================================
if 'data_queue' not in st.session_state: st.session_state.data_queue = queue.Queue()
if 'kafka_data' not in st.session_state: st.session_state.kafka_data = {}

def kafka_worker():
    if not KAFKA_AVAILABLE: return
    try:
        consumer = KafkaConsumer('stock-prices', bootstrap_servers='localhost:9092', value_deserializer=lambda m: json.loads(m.decode('utf-8')), consumer_timeout_ms=1000)
        for msg in consumer: st.session_state.data_queue.put(msg.value)
    except: pass

if KAFKA_AVAILABLE and not getattr(st.session_state, 'thread_started', False):
    threading.Thread(target=kafka_worker, daemon=True).start()
    st.session_state.thread_started = True

while not st.session_state.data_queue.empty():
    d = st.session_state.data_queue.get()
    if 'symbol' in d: 
        if d.get('price', 0) < 500 and d.get('price', 0) > 0: d['price'] *= 1000
        st.session_state.kafka_data[d['symbol']] = d

# ==========================================
# 5. GIAO DIỆN CHÍNH
# ==========================================
def create_chart(df, symbol):
    if df.empty: return go.Figure()
    df['SMA20'] = df['Close'].rolling(window=20).mean()
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.03, row_heights=[0.7, 0.3])
    fig.add_trace(go.Candlestick(x=df['Date'], open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'], name='Giá'), row=1, col=1)
    fig.add_trace(go.Scatter(x=df['Date'], y=df['SMA20'], line=dict(color='orange', width=1), name='SMA 20'), row=1, col=1)
    colors = ['green' if o < c else 'red' for o, c in zip(df['Open'], df['Close'])]
    fig.add_trace(go.Bar(x=df['Date'], y=df['Volume'], marker_color=colors, name='Vol'), row=2, col=1)
    fig.update_layout(height=500, title=f"Biểu đồ giá {symbol}", xaxis_rangeslider_visible=False)
    return fig

def main():
    st.title("📈 Vietnam Stock AI Dashboard")
    
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    try: from main import run_full_pipeline
    except ImportError: run_full_pipeline = None

    st.sidebar.header("Cấu hình")
    st.sidebar.subheader("🤖 AI Analyst")
    if st.sidebar.button("⚡ Dự đoán xu hướng", type="primary", key="btn_predict"):
        if run_full_pipeline is None: st.sidebar.error("Không tìm thấy file main.py!")
        else:
            progress_bar = st.sidebar.progress(0)
            status_text = st.sidebar.empty()
            def update_ui(msg, pct): progress_bar.progress(pct); status_text.text(msg)
            try:
                with st.spinner("Đang phân tích..."):
                    run_full_pipeline(datetime.now().strftime("%Y-%m-%d"), progress_callback=update_ui)
                st.sidebar.success("Hoàn tất!"); time.sleep(1); st.rerun()
            except Exception as e: st.sidebar.error(f"Lỗi: {e}")

    st.sidebar.divider()
    stock_choice = st.sidebar.selectbox("Mã Cổ Phiếu", list(VIETNAM_STOCKS.keys()))
    symbol = VIETNAM_STOCKS[stock_choice]
    
    k_status = "🟢 Kết nối tốt" if st.session_state.kafka_data else "🟡 Đang đợi..."
    if not KAFKA_AVAILABLE: k_status = "🔴 Lỗi thư viện Kafka"
    st.sidebar.info(f"Real-time Stream: {k_status}")
    
    if st.sidebar.button("Làm mới dữ liệu", key="btn_refresh"): st.rerun()

    history_df, data_source = get_stock_history_hybrid(symbol)
    kafka_info = st.session_state.kafka_data.get(symbol, {})
    ai_pred = get_ai_prediction(symbol)
    news_list = get_news(symbol)

    if kafka_info:
        price = kafka_info.get('price', 0); pct = kafka_info.get('percent_change', 0); vol = kafka_info.get('volume', 0); src_lbl = "⚡ Live (Kafka)"
    elif not history_df.empty:
        price = history_df.iloc[-1]['Close']; prev = history_df.iloc[-2]['Close'] if len(history_df)>1 else price
        pct = ((price - prev) / prev) * 100; vol = history_df.iloc[-1]['Volume']; src_lbl = f"📊 Đóng cửa ({data_source})"
    else: price = 0; pct = 0; vol = 0; src_lbl = "N/A"

    trend = ai_pred.get('trend', 'UNKNOWN') if ai_pred else "UNKNOWN"
    trend_map = {"INCREASE": ("🟢 TĂNG TRƯỞNG", "normal"), "DECREASE": ("🔴 GIẢM GIÁ", "inverse"), "SIDEWAYS": ("🟡 ĐI NGANG", "off"), "UNKNOWN": ("⚪ CHƯA RÕ", "off")}
    t_text, t_color = trend_map.get(trend, trend_map["UNKNOWN"])

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("💰 Giá", f"{price:,.0f} ₫", f"{pct:.2f}%"); c1.caption(src_lbl)
    c2.metric("📊 Volume", f"{vol:,.0f}")
    
    rsi = "N/A"
    if not history_df.empty and len(history_df) > 14:
        delta = history_df['Close'].diff(); gain = (delta.where(delta > 0, 0)).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean(); rs = gain / loss
        rsi = f"{100 - (100 / (1 + rs)).iloc[-1]:.1f}"
    c3.metric("⚡ RSI", rsi)
    c4.metric("🤖 AI Dự báo", t_text)

    t1, t2, t3, t4 = st.tabs(["🧠 Phân tích AI", "📉 Biểu đồ", "📰 Tin tức", "🔗 Đồ thị"])

    with t1:
        ai_cont = st.container()
        if ai_pred:
            with ai_cont:
                st.subheader(f"Nhận định cho {symbol}"); st.caption(f"Ngày: {ai_pred.get('date')} | Tin cậy: {ai_pred.get('confidence')}")
                reason = ai_pred.get('reasoning', '').replace("- ", "\n- ")
                if trend == "INCREASE": st.success(reason)
                elif trend == "DECREASE": st.error(reason)
                else: st.warning(reason)
                with st.expander("Dữ liệu thô"): st.code(ai_pred.get('full_analysis'))
        else: ai_cont.info("Chưa có dữ liệu phân tích. Bấm nút 'Dự đoán xu hướng' bên trái để chạy.")

    with t2:
        if not history_df.empty: st.plotly_chart(create_chart(history_df, symbol), width="stretch"); st.caption(f"Nguồn: {data_source}")
        else: st.warning("Chưa có dữ liệu giá.")

    with t3:
        news_cont = st.container()
        if news_list:
            with news_cont:
                st.write(f"Tìm thấy {len(news_list)} tin mới nhất:")
                for i, n in enumerate(news_list):
                    key = f"news_{symbol}_{i}_{n.get('postID', 'no_id')}"
                    with st.expander(f"**{n.get('date')} | {n.get('title', 'Bản tin')}**", expanded=False):
                        st.write(n.get('description') or n.get('summary'))
                        if n.get('originalContent'): st.caption("Nội dung gốc:"); st.text(n.get('originalContent')[:500] + "...")
                        st.divider()
        else: news_cont.info(f"📭 Hiện chưa có tin tức nào cho {symbol}.")

    with t4:
        rels = get_neo4j_data(symbol)
        if rels:
            g_col1, g_col2 = st.columns([4, 1])
            fig_net = create_network_graph(rels, symbol)
            with g_col1: st.plotly_chart(fig_net, width="stretch", height=700)
            with g_col2:
                st.info("💡 **Chú thích:**")
                st.markdown("🔴 **Stock**: Cổ phiếu")
                st.markdown("🔵 **Article**: Tin tức")
                st.markdown("🟢 **Entity**: Thực thể")
                st.divider()
                st.markdown("**Đường nối:**")
                st.markdown("<span style='color:#00CC00'>━━</span> Tích cực", unsafe_allow_html=True)
                st.markdown("<span style='color:#FF0000'>━━</span> Tiêu cực", unsafe_allow_html=True)
        else: st.warning("Không có dữ liệu đồ thị.")

    time.sleep(2)
    st.rerun()

if __name__ == "__main__":
    main()