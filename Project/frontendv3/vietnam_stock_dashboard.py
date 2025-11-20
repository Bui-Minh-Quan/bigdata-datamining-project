"""
Unified Dashboard: Kafka (Realtime) + MongoDB (AI/News/Price) + Neo4j (Graph)
Architecture: Hybrid Data Source (Online -> Database -> Realtime Stream)
Visualization: Advanced Interactive Network Graph
"""
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import networkx as nx # Thư viện xử lý đồ thị
from plotly.subplots import make_subplots
from datetime import datetime, timedelta
import json
import threading
import queue
import time
import sys
import os
import random

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

st.set_page_config(
    page_title="🚀 Vietnam Stock AI Dashboard", 
    layout="wide", 
    page_icon="📈",
    initial_sidebar_state="expanded"
)

st.markdown("""
<style>
    .stMetric {animation: none !important;} 
    div[data-testid='stMetricValue'] {font-size: 22px; color: #333;}
    .css-1d391kg {padding-top: 1rem;}
</style>""", unsafe_allow_html=True)

VIETNAM_STOCKS = {
    'FPT - Công nghệ FPT': 'FPT', 
    'SSI - Chứng khoán SSI': 'SSI', 
    'VCB - Vietcombank': 'VCB', 
    'VHM - Vinhomes': 'VHM', 
    'HPG - Hòa Phát': 'HPG', 
    'GAS - PV Gas': 'GAS',
    'MSN - Masan Group': 'MSN', 
    'MWG - Thế Giới Di Động': 'MWG', 
    'GVR - Tập đoàn Cao su': 'GVR', 
    'VIC - Vingroup': 'VIC'
}

# ==========================================
# 2. DATA ACCESS LAYER
# ==========================================

@st.cache_resource
def init_mongo():
    try:
        return MongoClient("mongodb://localhost:27017/")['bigdata_trr']
    except: return None

def get_stock_history_hybrid(symbol, days=90):
    try:
        end_date = datetime.now().strftime('%Y-%m-%d')
        start_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
        
        quote = Quote(symbol.upper(), 'tcbs')
        df = quote.history(start=start_date, end=end_date, interval='1D')
        
        if df is not None and not df.empty:
            df = df.rename(columns={'time': 'Date', 'open': 'Open', 'high': 'High', 'low': 'Low', 'close': 'Close', 'volume': 'Volume'})
            if df['Close'].iloc[-1] < 500: 
                for col in ['Open', 'High', 'Low', 'Close']: df[col] = df[col] * 1000
            return df, "☁️ Online (TCBS)"
    except Exception as e:
        print(f"⚠️ VnStock Error: {e}")

    try:
        db = init_mongo()
        if db is not None:
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
    except Exception as e:
        print(f"❌ MongoDB Error: {e}")

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
    """Lấy dữ liệu đồ thị tri thức (2 chiều tác động)"""
    try:
        driver = GraphDatabase.driver("bolt://localhost:7687", auth=("neo4j", "password123"))
        with driver.session() as session:
            # SỬA QUERY: Lấy rõ ràng startNode và endNode để biết chiều
            # Dùng COALESCE để xử lý trường hợp labels bị null
            q = """
            MATCH (s:Stock {name: $sym})-[r]-(t)
            RETURN 
                startNode(r).name as src, 
                type(r) as rel, 
                COALESCE(endNode(r).name, endNode(r).title, endNode(r).id) as tgt,
                COALESCE(labels(startNode(r)), ['Unknown']) as src_type,
                COALESCE(labels(endNode(r)), ['Unknown']) as tgt_type
            LIMIT 30
            """
            return session.run(q, sym=symbol).data()
    except Exception as e:
        print(f"Neo4j Error: {e}") 
        return []

# ==========================================
# 3. GRAPH VISUALIZATION (FIX LỖI KEYERROR)
# ==========================================

def create_network_graph(data, center_node):
    if not data: return None

    G = nx.Graph() # Dùng Graph vô hướng cho dễ vẽ layout
    
    colors = {
        'Stock': '#FF6B6B',      
        'Article': '#4ECDC4',    
        'Entity': '#45B7D1',     
        'Person': '#96CEB4',     
        'Organization': '#FFEEAD', 
        'Location': '#D4A5A5',   
        'Unknown': '#D3D3D3'     
    }
    
    # Thêm node trung tâm
    G.add_node(center_node, type='Stock', size=40, color=colors['Stock'])
    
    node_types_count = {'Stock': 1}
    edge_labels_dict = {} # Lưu nhãn cạnh để hiển thị tooltip
    
    for item in data:
        # Sử dụng .get() để tránh KeyError
        source = item.get('src') or "Unknown"
        target = item.get('tgt') or "Unknown"
        relation = item.get('rel', 'RELATED')
        
        # Xác định node vệ tinh (node không phải center_node)
        if source == center_node:
            satellite = target
            # Lấy danh sách type an toàn
            sat_labels = item.get('tgt_type', ['Unknown'])
            direction = "out" # center -> satellite
        else:
            satellite = source
            sat_labels = item.get('src_type', ['Unknown'])
            direction = "in" # satellite -> center
            
        # Xử lý loại node an toàn
        if not sat_labels: sat_labels = ['Unknown']
        node_type = sat_labels[0]
        if 'Article' in sat_labels: node_type = 'Article'
        
        node_types_count[node_type] = node_types_count.get(node_type, 0) + 1
        node_color = colors.get(node_type, colors.get('Entity', colors['Unknown']))
        
        # Thêm node vệ tinh
        G.add_node(satellite, type=node_type, size=25, color=node_color)
        
        # Thêm cạnh và lưu thông tin chiều
        G.add_edge(center_node, satellite)
        
        # Tạo nhãn cạnh (Tooltip)
        if direction == "out":
            edge_labels_dict[(center_node, satellite)] = f"{center_node} --[{relation}]--> {satellite}"
            edge_labels_dict[(satellite, center_node)] = f"{center_node} --[{relation}]--> {satellite}"
        else:
            edge_labels_dict[(center_node, satellite)] = f"{satellite} --[{relation}]--> {center_node}"
            edge_labels_dict[(satellite, center_node)] = f"{satellite} --[{relation}]--> {center_node}"

    # --- LAYOUT & VẼ ---
    pos = nx.spring_layout(G, k=0.5, iterations=50, seed=42)
    
    edge_x, edge_y, edge_text = [], [], []
    
    for edge in G.edges():
        x0, y0 = pos[edge[0]]
        x1, y1 = pos[edge[1]]
        edge_x.extend([x0, x1, None])
        edge_y.extend([y0, y1, None])
        # Lấy tooltip đã lưu
        edge_text.append(edge_labels_dict.get(edge, ""))

    edge_trace = go.Scatter(
        x=edge_x, y=edge_y,
        line=dict(width=1, color='#888'),
        hoverinfo='text',
        text=edge_text, # Hiển thị tooltip trên cạnh
        mode='lines'
    )
    
    node_x, node_y, node_text, node_colors, node_sizes = [], [], [], [], []
    for node in G.nodes(data=True):
        if node[0] not in pos: continue
        x, y = pos[node[0]]
        node_x.append(x); node_y.append(y)
        
        n_type = node[1].get('type', 'Unknown')
        # Tooltip node: Hiện tên và loại
        node_text.append(f"<b>{node[0]}</b><br>Type: {n_type}")
        node_colors.append(node[1].get('color', '#888'))
        node_sizes.append(node[1].get('size', 20))

    node_trace = go.Scatter(
        x=node_x, y=node_y,
        mode='markers', # Chỉ hiện chấm tròn, hover mới hiện tên
        hoverinfo='text',
        hovertext=node_text,
        marker=dict(showscale=False, color=node_colors, size=node_sizes, line_width=2, line_color='white')
    )
    
    # Fix lỗi title layout
    layout_title = {
        'text': f"Mạng lưới tác động 2 chiều của {center_node}",
        'font': {'size': 16}
    }
    
    fig = go.Figure(data=[edge_trace, node_trace],
             layout=go.Layout(
                title=layout_title,
                showlegend=False, hovermode='closest',
                margin=dict(b=20,l=5,r=5,t=40),
                xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
                yaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
                height=600, plot_bgcolor='white'
             ))
    return fig, node_types_count

# ==========================================
# 4. KAFKA WORKER
# ==========================================
if 'data_queue' not in st.session_state: st.session_state.data_queue = queue.Queue()
if 'kafka_data' not in st.session_state: st.session_state.kafka_data = {}

def kafka_worker():
    if not KAFKA_AVAILABLE: return
    try:
        consumer = KafkaConsumer(
            'stock-prices', 
            bootstrap_servers='localhost:9092', 
            value_deserializer=lambda m: json.loads(m.decode('utf-8')), 
            consumer_timeout_ms=1000
        )
        for msg in consumer: 
            st.session_state.data_queue.put(msg.value)
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
    st.sidebar.header("Cấu hình")
    stock_choice = st.sidebar.selectbox("Mã Cổ Phiếu", list(VIETNAM_STOCKS.keys()))
    symbol = VIETNAM_STOCKS[stock_choice]
    
    k_status = "🟢 Kết nối tốt" if st.session_state.kafka_data else "🟡 Đang đợi..."
    if not KAFKA_AVAILABLE: k_status = "🔴 Lỗi thư viện Kafka"
    st.sidebar.info(f"Real-time Stream: {k_status}")
    
    if st.sidebar.button("Làm mới"): st.rerun()

    # Lấy dữ liệu
    history_df, data_source = get_stock_history_hybrid(symbol)
    kafka_info = st.session_state.kafka_data.get(symbol, {})
    ai_pred = get_ai_prediction(symbol)
    news_list = get_news(symbol)

    # Metrics
    if kafka_info:
        price = kafka_info.get('price', 0)
        pct = kafka_info.get('percent_change', 0)
        vol = kafka_info.get('volume', 0)
        src_lbl = "⚡ Live (Kafka)"
    elif not history_df.empty:
        price = history_df.iloc[-1]['Close']
        prev = history_df.iloc[-2]['Close'] if len(history_df) > 1 else price
        pct = ((price - prev) / prev) * 100
        vol = history_df.iloc[-1]['Volume']
        src_lbl = f"📊 Đóng cửa ({data_source})"
    else:
        price = 0; pct = 0; vol = 0; src_lbl = "N/A"

    trend = ai_pred.get('trend', 'UNKNOWN') if ai_pred else "UNKNOWN"
    trend_map = {"INCREASE": ("🟢 TĂNG TRƯỞNG", "normal"), "DECREASE": ("🔴 GIẢM GIÁ", "inverse"), "SIDEWAYS": ("🟡 ĐI NGANG", "off"), "UNKNOWN": ("⚪ CHƯA RÕ", "off")}
    t_text, t_color = trend_map.get(trend, trend_map["UNKNOWN"])

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("💰 Giá", f"{price:,.0f} ₫", f"{pct:.2f}%")
    c1.caption(src_lbl)
    c2.metric("📊 Volume", f"{vol:,.0f}")
    
    rsi = "N/A"
    if not history_df.empty and len(history_df) > 14:
        delta = history_df['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rs = gain / loss
        val = 100 - (100 / (1 + rs)).iloc[-1]
        rsi = f"{val:.1f}"
    c3.metric("⚡ RSI", rsi)
    c4.metric("🤖 AI Dự báo", t_text)

    # Tabs
    t1, t2, t3, t4 = st.tabs(["🧠 Phân tích AI", "📉 Biểu đồ", "📰 Tin tức", "🔗 Đồ thị"])

    with t1:
        if ai_pred:
            st.subheader(f"Nhận định cho {symbol}")
            st.caption(f"Ngày: {ai_pred.get('date')} | Tin cậy: {ai_pred.get('confidence')}")
            reason = ai_pred.get('reasoning', '').replace("- ", "\n- ")
            if trend == "INCREASE": st.success(reason)
            elif trend == "DECREASE": st.error(reason)
            else: st.warning(reason)
            with st.expander("Dữ liệu thô"): st.code(ai_pred.get('full_analysis'))
        else: st.info("Chưa có dữ liệu phân tích.")

    with t2:
        if not history_df.empty:
            st.plotly_chart(create_chart(history_df, symbol), width="stretch")
            st.caption(f"Nguồn: {data_source}")
        else: st.warning("Chưa có dữ liệu giá.")

    with t3:
        if news_list:
            for n in news_list:
                with st.container():
                    st.markdown(f"**{n.get('date')} | {n.get('title')}**")
                    st.write(n.get('description'))
                    st.divider()
        else: st.write("Không có tin tức.")

    with t4:
        rels = get_neo4j_data(symbol)
        if rels:
            g_col1, g_col2 = st.columns([3, 1])
            fig_net, stats = create_network_graph(rels, symbol)
            
            with g_col1:
                st.plotly_chart(fig_net, width="stretch")
            
            with g_col2:
                st.write("**Thống kê Node:**")
                for k, v in stats.items():
                    st.write(f"- {k}: {v}")
                st.write("---")
                st.caption("💡 **Mẹo:** Dùng chuột để zoom, pan và hover vào các điểm tròn để xem chi tiết.")
        else: 
            st.warning("Không có dữ liệu đồ thị.")

    time.sleep(2)
    st.rerun()

if __name__ == "__main__":
    main()