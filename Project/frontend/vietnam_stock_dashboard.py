"""
Unified Dashboard: Kafka (Realtime) + MongoDB (AI/News/Price) + Neo4j (Graph)
Visualization: 
- Advanced Directed Graph with Arrowheads.
- Impact Coloring (Red/Green).
- Node Labels (Title for Articles).
- 2-Hop Neighbor Search.
"""
from pyvis.network import Network
import streamlit.components.v1 as components
import streamlit as st
import threading
import pandas as pd
import plotly.graph_objects as go
import networkx as nx
from plotly.subplots import make_subplots
from datetime import datetime, timedelta
import importlib
import warnings
from streamlit.runtime.scriptrunner import add_script_run_ctx

import json
import threading
import queue
import time
import sys
import os
import math

from dotenv import load_dotenv
load_dotenv()

KAFKA_SERVER = os.getenv('KAFKA_SERVER', 'localhost:9092')
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USERNAME", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "password123")

os.environ["PYTHONWARNINGS"] = "ignore"

# 2. Tắt warning ở mức Python
warnings.filterwarnings("ignore")
warnings.simplefilter(action='ignore', category=FutureWarning)
warnings.simplefilter(action='ignore', category=UserWarning)
warnings.simplefilter(action='ignore', category=DeprecationWarning)

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

# Load external CSS file
def load_css():
    css_file = os.path.join(os.path.dirname(__file__), "styles.css")
    if os.path.exists(css_file):
        with open(css_file, "r", encoding="utf-8") as f:
            return f"<style>{f.read()}</style>"
    return ""

st.markdown(load_css(), unsafe_allow_html=True)

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

def get_news(symbol, limit=30, skip=0):
    db = init_mongo()
    if db is None: return []
    return list(db['news'].find({"taggedSymbols": symbol, "date": {"$exists": True}}).sort("date", -1).skip(skip).limit(limit))

def get_neo4j_data(symbol):
    try:
        driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
        with driver.session() as session:
            q = """
            MATCH (s:Stock {name: $sym})

            // 1. Tìm TẤT CẢ đường dẫn (1..2 hops)
            MATCH path = (source)-[*1..2]->(s)

            // 2. Blacklist (Giữ nguyên logic của bạn)
            WHERE source <> s 
            AND NONE(n IN nodes(path) WHERE n.name IN [
                'Thị trường chứng khoán', 'Thị trường', 'Việt Nam', 'Kinh tế', 
                'Tài chính', 'Ngành ngân hàng', "Ngân hàng", 'Bất động sản',
                'Doanh nghiệp', 'Nhà đầu tư', 'Cổ phiếu', 'Tin tức', 'Chính phủ',
                'Ngân sách nhà nước', 'Thị trường bất động sản'
            ])

            // 3. Chuẩn bị dữ liệu để phân loại
            WITH path, length(path) as hops, relationships(path)[-1] as direct_rel
            WHERE direct_rel.date IS NOT NULL
            
            // Sắp xếp chung toàn bộ theo thời gian giảm dần trước
            ORDER BY direct_rel.date DESC

            // 4. [LOGIC MỚI] GOM NHÓM VÀ CẮT RIÊNG (QUOTA)
            // Gom tất cả lại thành một danh sách
            WITH collect({path: path, hops: hops}) as all_paths
            
            // Lọc ra danh sách trực tiếp và lấy Top 70
            WITH [x IN all_paths WHERE x.hops = 1][0..70] as direct_paths,
                 
            // Lọc ra danh sách gián tiếp và lấy Top 30
                 [x IN all_paths WHERE x.hops = 2][0..30] as indirect_paths

            // Gộp 2 danh sách lại (Tổng cộng tối đa 100, nhưng đảm bảo luôn có cả 2 loại)
            UNWIND (direct_paths + indirect_paths) as item
            WITH item.path as path

            // 5. Bung ra để trả về (Giữ nguyên)
            UNWIND relationships(path) as r
            WITH startNode(r) as src, endNode(r) as tgt, r
            
            RETURN DISTINCT
                COALESCE(src.name, src.title, toString(src.id), head(labels(src))) as src_name, 
                labels(src) as src_labels,
                COALESCE(tgt.name, tgt.title, toString(tgt.id), head(labels(tgt))) as tgt_name, 
                labels(tgt) as tgt_labels,
                type(r) as rel_type, 
                r.impact as impact, 
                r.description as description, 
                r.date as date
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

def create_interactive_graph(data, center_node_id):
    if not data: return None

    net = Network(height='600px', width='100%', bgcolor='#ffffff', font_color='black')
    
    # Cấu hình vật lý
    net.force_atlas_2based(
        gravity=-80,           
        central_gravity=0.01,  
        spring_length=120,     
        spring_strength=0.08,  
        damping=0.4,           
        overlap=0      
    )

    color_map = {'Stock': '#FF4B4B', 'Article': '#1E90FF', 'Entity': '#2E8B57'}
    shape_map = {'Stock': 'star', 'Article': 'square', 'Entity': 'dot'} 
    added_nodes = set()

    for item in data:
        # --- Node Nguồn ---
        src_labels = item.get('src_labels', [])
        src_type = 'Stock' if 'Stock' in src_labels else ('Article' if 'Article' in src_labels else 'Entity')
        src_name = item.get('src_name', 'Unknown') 
        
        # --- Node Đích ---
        tgt_labels = item.get('tgt_labels', [])
        tgt_type = 'Stock' if 'Stock' in tgt_labels else ('Article' if 'Article' in tgt_labels else 'Entity')
        tgt_name = item.get('tgt_name', 'Unknown')

        # Thêm Node
        if src_name not in added_nodes:
            label_display = shorten_text(src_name, 20)
            net.add_node(src_name, label=label_display, title=f"Tên thực thể: {src_name} \nLoại thực thể: {src_type}", 
                         color=color_map.get(src_type, '#97c2fc'), 
                         shape=shape_map.get(src_type, 'dot'),
                         size=30 if src_type == 'Stock' else (25 if src_type == 'Article' else 15))
            added_nodes.add(src_name)
            
        if tgt_name not in added_nodes:
            label_display = shorten_text(tgt_name, 20)
            net.add_node(tgt_name, label=label_display, title=f"Tên thực thể: {tgt_name} \nLoại thực thể: {tgt_type}", 
                         color=color_map.get(tgt_type, '#97c2fc'), 
                         shape=shape_map.get(tgt_type, 'dot'),
                         size=30 if tgt_type == 'Stock' else (25 if tgt_type == 'Article' else 15))
            added_nodes.add(tgt_name)

        # --- Thêm Cạnh (Xử lý Hover Description) ---
        impact = item.get('impact', 'RELATED')
        
        # Lấy description và xử lý nếu nó là list
        raw_desc = item.get('description', '')
        if isinstance(raw_desc, list):
            description = ", ".join(raw_desc)
        else:
            description = str(raw_desc)
            
        # Tạo nội dung HTML cho Tooltip
        # Khi hover vào dây, nó sẽ hiện ra cái bảng nhỏ này
        impact_vietsub = "TÍCH CỰC" if impact == 'POSITIVE' else ("TIÊU CỰC" if impact == 'NEGATIVE' else "LIÊN QUAN")
        hover_content = f"""
        Ảnh hưởng: {impact_vietsub}
        Thông tin chi tiết: {description}
        """
        
        edge_color = '#00CC00' if impact == 'POSITIVE' else ('#FF0000' if impact == 'NEGATIVE' else '#cccccc')
        
        net.add_edge(
            src_name, 
            tgt_name, 
            title=hover_content,  # <--- THAY ĐỔI Ở ĐÂY (Nội dung hover)
            color=edge_color, 
            width=1.5,
            arrows='to'
        )

    return net
# ==========================================
# 4. KAFKA WORKER
# ==========================================
if 'data_queue' not in st.session_state: st.session_state.data_queue = queue.Queue()
if 'kafka_data' not in st.session_state: st.session_state.kafka_data = {}

def kafka_worker():
    if not KAFKA_AVAILABLE: return
    try:
        consumer = KafkaConsumer('stock-prices', bootstrap_servers=KAFKA_SERVER, value_deserializer=lambda m: json.loads(m.decode('utf-8')), consumer_timeout_ms=1000)
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
    
    # Filter out rows with missing data
    df = df.dropna(subset=['Open', 'High', 'Low', 'Close'])
    
    df['SMA20'] = df['Close'].rolling(window=20).mean()
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.03, row_heights=[0.7, 0.3])
    fig.add_trace(go.Candlestick(x=df['Date'], open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'], name='Giá'), row=1, col=1)
    fig.add_trace(go.Scatter(x=df['Date'], y=df['SMA20'], line=dict(color='orange', width=1), name='SMA 20'), row=1, col=1)
    colors = ['green' if o < c else 'red' for o, c in zip(df['Open'], df['Close'])]
    fig.add_trace(go.Bar(x=df['Date'], y=df['Volume'], marker_color=colors, name='Vol'), row=2, col=1)
    
    # Remove gaps for weekends and holidays by using rangebreaks
    fig.update_xaxes(
        rangebreaks=[
            dict(bounds=["sat", "mon"]),  # Hide weekends (Saturday to Monday)
        ]
    )
    
    fig.update_layout(
        height=500, 
        title=f"Biểu đồ giá {symbol}", 
        xaxis_rangeslider_visible=False
    )
    return fig

def main():
    # --- SIDEBAR SETUP ---
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    try: 
        import main as pipeline_module
        importlib.reload(pipeline_module)
        run_full_pipeline = pipeline_module.run_full_pipeline
    except ImportError: run_full_pipeline = None
    
    # Initialize session state for AI progress tracking
    if "ai_is_running" not in st.session_state: st.session_state.ai_is_running = False
    if "ai_log" not in st.session_state: st.session_state.ai_log = ""
    if "ai_progress" not in st.session_state: st.session_state.ai_progress = 0
    
    def run_ai_background():
        try:
            def thread_callback(msg, pct):
                st.session_state.ai_log = msg 
                st.session_state.ai_progress = pct 
            run_full_pipeline(datetime.now().strftime("%Y-%m-%d"), progress_callback=thread_callback)
            st.session_state.ai_log = "✅ Hoàn tất! Vui lòng đợi làm mới..."
            st.session_state.ai_progress = 100
            time.sleep(1)
            st.session_state.ai_is_running = False
        except Exception as e:
            st.session_state.ai_log = f"❌ Lỗi: {str(e)}"
            st.session_state.ai_is_running = False
    
    # Sidebar content
    st.sidebar.header("⚙️ Cấu hình")
    st.sidebar.page_link("vietnam_stock_dashboard.py", label="Trang chủ Dashboard", icon="🏠")
    st.sidebar.page_link("pages/history_view.py", label="Xem Lịch sử & Đánh giá", icon="📜")
    st.sidebar.divider()
    
    stock_choice = st.sidebar.selectbox("📌 Mã cổ phiếu", list(VIETNAM_STOCKS.keys()))
    symbol = VIETNAM_STOCKS[stock_choice]
    
    st.sidebar.divider()
    st.sidebar.subheader("🤖 Phân tích AI")
    
    if st.session_state.ai_is_running:
        st.sidebar.progress(st.session_state.ai_progress)
        st.sidebar.caption(f"{st.session_state.ai_log}")
    else:
        if st.sidebar.button("⚡ Dự đoán xu hướng", type="primary", key="btn_predict", use_container_width=True):
            if run_full_pipeline is None:
                st.sidebar.error("Không tìm thấy file main.py!")
            else:
                st.session_state.ai_is_running = True
                st.session_state.ai_progress = 0
                st.session_state.ai_log = "Đang chạy dự đoán"
                t = threading.Thread(target=run_ai_background)
                add_script_run_ctx(t)
                t.start()
                st.rerun()

    st.sidebar.divider()
    k_status = "🟢 Kết nối tốt" if st.session_state.kafka_data else "🟢 Sẵn sàng"
    if not KAFKA_AVAILABLE: k_status = "🔴 Lỗi Kafka"
    st.sidebar.caption(f"Real-time: {k_status}")
    
    if st.sidebar.button("🔄 Làm mới dữ liệu", key="btn_refresh", use_container_width=True): 
        st.rerun()

    # --- FETCH DATA ---
    history_df, data_source = get_stock_history_hybrid(symbol)
    kafka_info = st.session_state.kafka_data.get(symbol, {})
    ai_pred = get_ai_prediction(symbol)
    news_list = get_news(symbol)

    if kafka_info:
        price = kafka_info.get('price', 0)
        pct = kafka_info.get('percent_change', 0)
        vol = kafka_info.get('volume', 0)
        src_lbl = "⚡ Live"
    elif not history_df.empty:
        price = history_df.iloc[-1]['Close']
        prev = history_df.iloc[-2]['Close'] if len(history_df) > 1 else price
        pct = ((price - prev) / prev) * 100
        vol = history_df.iloc[-1]['Volume']
        src_lbl = f"📊 {data_source}"
    else:
        price = 0; pct = 0; vol = 0; src_lbl = "N/A"

    trend = ai_pred.get('trend', 'UNKNOWN') if ai_pred else "UNKNOWN"
    trend_map = {
        "INCREASE": "🟢 TĂNG", 
        "DECREASE": "🔴 GIẢM", 
        "SIDEWAYS": "🟡 ĐI NGANG", 
        "UNKNOWN": "⚪ CHƯA RÕ"
    }
    t_text = trend_map.get(trend, trend_map["UNKNOWN"])
    
    # Calculate RSI
    rsi = "N/A"
    if not history_df.empty and len(history_df) > 14:
        delta = history_df['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rs = gain / loss
        rsi = f"{100 - (100 / (1 + rs)).iloc[-1]:.1f}"

    # Get AI confidence
    confidence = ai_pred.get('confidence', 'N/A') if ai_pred else 'N/A'
    
    # Format delta color
    delta_class = "positive" if pct >= 0 else "negative"
    delta_sign = "+" if pct >= 0 else ""
    
    # Format volume
    vol_display = f"{vol/1e6:.1f}M" if vol >= 1e6 else f"{vol/1e3:.1f}K" if vol >= 1e3 else f"{vol:,.0f}"
    
    # Get stock full name
    stock_full_name = stock_choice  # This includes both symbol and company name

    # --- FIXED HEADER (HTML) ---
    # We render the Title and the first 3 metrics in HTML.
    # The 4th metric (AI) will be injected via st.popover and positioned via CSS to sit next to them.
    
    header_html = f"""
    <div class="fixed-header">
        <div class="header-left">
            <div class="header-title">📊 Dashboard Phân tích Chứng khoán Việt Nam</div>
            <div class="header-subtitle">📌 {stock_full_name}</div>
        </div>
        <div class="header-metrics">
            <div class="metric-card">
                <div class="metric-label">💰 Giá CP</div>
                <div class="metric-value">{price:,.0f}₫</div>
                <div class="metric-sub {delta_class}">{delta_sign}{pct:.2f}%</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">📊 KLGD</div>
                <div class="metric-value">{vol_display}</div>
                <div class="metric-sub neutral">cổ phiếu</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">⚡ RSI</div>
                <div class="metric-value">{rsi}</div>
                <div class="metric-sub neutral">14 ngày</div>
            </div>
        </div>
    </div>
    """
    st.markdown(header_html, unsafe_allow_html=True)
    
    # --- AI Popover Button ---
    
    ai_btn_label = f"{t_text}"
    ai_confidence_str = f"Tự tin: {confidence}"
    
    # Inject dynamic CSS for AI confidence text (only the dynamic part)
    st.markdown(f"""
    <style>
        /* Subtext (Bottom) - Dynamic content */
        div[data-testid="stPopover"] button::after {{
            content: "{ai_confidence_str}";
            font-size: 0.75rem;
            font-weight: 600;
            color: #cbd5e1;
            margin-top: 2px;
            font-family: "Source Sans Pro", sans-serif;
        }}
    </style>
    """, unsafe_allow_html=True)
    
    with st.popover(ai_btn_label):
            if ai_pred:
                st.markdown(f"### 🤖 Phân tích AI cho {symbol}")
                st.caption(f"📅 Ngày: {ai_pred.get('date')} | 🎯 Độ tin cậy: {confidence}")
                st.divider()
                
                reason = ai_pred.get('reasoning', 'Không có dữ liệu').replace("- ", "\n- ")
                
                if trend == "INCREASE":
                    st.success(f"**Xu hướng: TĂNG**")
                    st.markdown(reason)
                elif trend == "DECREASE":
                    st.error(f"**Xu hướng: GIẢM**")
                    st.markdown(reason)
                else:
                    st.warning(f"**Xu hướng: {t_text}**")
                    st.markdown(reason)
                
                with st.expander("📄 Dữ liệu thô"):
                    st.code(ai_pred.get('full_analysis', 'N/A'))
            else:
                st.info("Chưa có dữ liệu phân tích AI.\n\nBấm '⚡ Dự đoán xu hướng' ở sidebar để chạy.")

    t2, t3 = st.tabs(["📊 Thị trường & Tin tức", "🔗 Đồ thị"])

    with t2:
        # Create 70-30 split: Chart on left, News feed on right
        col_chart, col_news = st.columns([7, 3])
        
        with col_chart:
            st.subheader("📉 Biểu đồ giá")
            if not history_df.empty:
                # Update chart height to be taller
                fig = create_chart(history_df, symbol)
                fig.update_layout(height=800)
                st.plotly_chart(fig, width="stretch")
                st.caption(f"Nguồn: {data_source}")
            else: 
                st.warning("Chưa có dữ liệu giá.")
        
        with col_news:
            st.subheader("📰 Tin tức")
            
            # Initialize news pagination in session state
            if f"news_count_{symbol}" not in st.session_state:
                st.session_state[f"news_count_{symbol}"] = 30
            
            # Fetch news with current limit
            news_list = get_news(symbol, limit=st.session_state[f"news_count_{symbol}"])
            
            if news_list:
                
                # Make news section scrollable with fixed height matching chart
                with st.container(height=750):
                    for i, n in enumerate(news_list):
                        # Format date
                        date_raw = n.get('date', '')
                        try:
                            if isinstance(date_raw, str):
                                if " " in date_raw:
                                    news_dt = datetime.strptime(date_raw, "%Y-%m-%d %H:%M:%S")
                                else:
                                    news_dt = datetime.strptime(date_raw, "%Y-%m-%d")
                                date_formatted = news_dt.strftime("%d/%m/%Y")
                            else:
                                date_formatted = date_raw.strftime("%d/%m/%Y")
                        except:
                            date_formatted = str(date_raw)[:16] if date_raw else "N/A"
                        
                        title = n.get('title', 'Bản tin')
                        
                        # Create formatted label with title (2 lines max) and date
                        # Truncate title for display in header
                        title_display = title[:100] + "..." if len(title) > 100 else title
                        expander_label = f"{title_display}\n\n📅 *{date_formatted}*"
                        
                        # Use expander with custom styling
                        with st.expander(expander_label, expanded=False):
                            # Show full content without truncation
                            if n.get('originalContent'): 
                                st.text(n.get('originalContent'))
                    
                    # Load more button at the end
                    st.divider()
                    if st.button("📥 Tải thêm tin tức", key=f"load_more_{symbol}", use_container_width=True):
                        st.session_state[f"news_count_{symbol}"] += 30
                        st.rerun()
            else: 
                st.info(f"📭 Chưa có tin tức cho {symbol}")

    with t3:
        rels = get_neo4j_data(symbol)
        if rels:
            st.caption("💡 Bạn có thể kéo thả các node, lăn chuột để zoom.")
            
            # Tạo graph
            net = create_interactive_graph(rels, symbol)
            
            if net:
                # Lưu vào file html tạm
                path = "/tmp" if os.path.exists("/tmp") else "."
                file_name = f"{path}/network_{symbol}.html"
                net.save_graph(file_name)
                
                # Đọc file html và hiển thị bằng Streamlit Component
                with open(file_name, 'r', encoding='utf-8') as f:
                    html_content = f.read()
                
                # Render HTML
                components.html(html_content, height=610, scrolling=False)
                
                # Chú thích thủ công bên dưới (Vì PyVis legend hơi khó chỉnh)
                st.markdown("""
                <div class="graph-legend">
                    <span class="stock">★ Stock</span> &nbsp;|&nbsp; 
                    <span class="article">■ Article</span> &nbsp;|&nbsp; 
                    <span class="entity">● Entity</span> <br>
                    <span class="positive">── Positive Impact</span> &nbsp;|&nbsp; 
                    <span class="negative">── Negative Impact</span>
                </div>
                """, unsafe_allow_html=True)
            
        else: 
            st.warning("Không có dữ liệu đồ thị.")

    # Auto-refresh removed to prevent constant reloading/fading
    # time.sleep(2)
    # st.rerun()

if __name__ == "__main__":
    warnings.filterwarnings("ignore")
    os.environ["PYTHONWARNINGS"] = "ignore"
    main()