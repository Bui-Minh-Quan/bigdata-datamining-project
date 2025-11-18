"""
Streamlit Dashboard - Realtime Stock Price Visualization
Hiển thị giá cổ phiếu realtime từ Kafka, tin tức và Neo4j graph
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from kafka import KafkaConsumer
import json
from datetime import datetime, timedelta
import threading
import queue
from neo4j import GraphDatabase
import time

# Page config
st.set_page_config(
    page_title="📈 Vietnam Stock Dashboard",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Portfolio stocks
PORTFOLIO_STOCKS = ["FPT", "SSI", "VCB", "VHM", "HPG", "GAS", "MSN", "MWG", "GVR", "VIC"]

STOCK_NAMES = {
    "FPT": "FPT - Công nghệ",
    "SSI": "SSI - Chứng khoán", 
    "VCB": "VCB - Ngân hàng",
    "VHM": "VHM - Bất động sản",
    "HPG": "HPG - Thép",
    "GAS": "GAS - Khí đốt",
    "MSN": "MSN - Thủy sản",
    "MWG": "MWG - Bán lẻ",
    "GVR": "GVR - Cao su",
    "VIC": "VIC - Bất động sản"
}

# Initialize session state
if 'stock_data' not in st.session_state:
    st.session_state.stock_data = {symbol: [] for symbol in PORTFOLIO_STOCKS}

if 'news_data' not in st.session_state:
    st.session_state.news_data = []

if 'consumer_running' not in st.session_state:
    st.session_state.consumer_running = False

if 'data_queue' not in st.session_state:
    st.session_state.data_queue = queue.Queue()

# Kafka Consumer Thread
def kafka_consumer_thread(data_queue, bootstrap_servers='localhost:9092', topic='stock-prices'):
    """Background thread để consume Kafka messages"""
    try:
        consumer = KafkaConsumer(
            topic,
            bootstrap_servers=bootstrap_servers,
            value_deserializer=lambda m: json.loads(m.decode('utf-8')),
            auto_offset_reset='latest',
            enable_auto_commit=True,
            consumer_timeout_ms=1000
        )
        
        for message in consumer:
            data_queue.put(message.value)
            
    except Exception as e:
        st.error(f"Kafka consumer error: {e}")

# Start Kafka consumer if not running
if not st.session_state.consumer_running:
    consumer_thread = threading.Thread(
        target=kafka_consumer_thread,
        args=(st.session_state.data_queue,),
        daemon=True
    )
    consumer_thread.start()
    st.session_state.consumer_running = True

# Process queue data
def process_queue_data():
    """Xử lý data từ Kafka queue"""
    while not st.session_state.data_queue.empty():
        try:
            data = st.session_state.data_queue.get_nowait()
            symbol = data.get('symbol')
            
            if symbol in st.session_state.stock_data:
                # Giữ tối đa 100 data points
                if len(st.session_state.stock_data[symbol]) >= 100:
                    st.session_state.stock_data[symbol].pop(0)
                
                st.session_state.stock_data[symbol].append(data)
                
        except queue.Empty:
            break
        except Exception as e:
            st.error(f"Error processing data: {e}")

# Neo4j connection
class Neo4jConnection:
    def __init__(self, uri="bolt://localhost:7687", user="neo4j", password="password123"):
        self.driver = GraphDatabase.driver(uri, auth=(user, password))
    
    def close(self):
        self.driver.close()
    
    def query(self, query, parameters=None):
        with self.driver.session() as session:
            result = session.run(query, parameters)
            return [record for record in result]

# Sidebar
with st.sidebar:
    st.title("⚙️ Settings")
    
    # Stock selector
    selected_stock = st.selectbox(
        "📊 Select Stock",
        options=PORTFOLIO_STOCKS,
        format_func=lambda x: STOCK_NAMES.get(x, x)
    )
    
    st.markdown("---")
    
    # Time range
    time_range = st.selectbox(
        "⏱️ Time Range",
        ["Last 5 min", "Last 15 min", "Last 30 min", "Last 1 hour"]
    )
    
    st.markdown("---")
    
    # Refresh rate
    refresh_rate = st.slider(
        "🔄 Refresh Rate (seconds)",
        min_value=1,
        max_value=10,
        value=2
    )
    
    st.markdown("---")
    
    # Kafka status
    st.subheader("📡 Kafka Status")
    if st.session_state.consumer_running:
        st.success("🟢 Connected")
    else:
        st.error("🔴 Disconnected")
    
    total_messages = sum(len(data) for data in st.session_state.stock_data.values())
    st.metric("Total Messages", total_messages)
    
    st.markdown("---")
    
    # Neo4j status
    st.subheader("🔗 Neo4j Status")
    try:
        neo4j_conn = Neo4jConnection()
        neo4j_conn.close()
        st.success("🟢 Connected")
    except:
        st.error("🔴 Disconnected")

# Main content
st.title("📈 Vietnam Stock Market Dashboard")
st.markdown(f"**Selected:** {STOCK_NAMES.get(selected_stock, selected_stock)}")

# Process new data
process_queue_data()

# Get data for selected stock
stock_history = st.session_state.stock_data.get(selected_stock, [])

# Layout
col1, col2, col3, col4 = st.columns(4)

if stock_history:
    latest_data = stock_history[-1]
    
    with col1:
        st.metric(
            "💰 Current Price",
            f"{latest_data['price']:,.0f} VNĐ",
            f"{latest_data['percent_change']:.2f}%"
        )
    
    with col2:
        st.metric(
            "📊 Volume",
            f"{latest_data['volume']:,}"
        )
    
    with col3:
        st.metric(
            "📈 High",
            f"{latest_data['high']:,.0f} VNĐ"
        )
    
    with col4:
        st.metric(
            "📉 Low",
            f"{latest_data['low']:,.0f} VNĐ"
        )
else:
    st.info("⏳ Waiting for data...")

st.markdown("---")

# Charts section
chart_col1, chart_col2 = st.columns([2, 1])

with chart_col1:
    st.subheader(f"📊 {selected_stock} Price Chart")
    
    if stock_history and len(stock_history) > 1:
        df = pd.DataFrame(stock_history)
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        
        # Create candlestick-like chart
        fig = make_subplots(
            rows=2, cols=1,
            shared_xaxes=True,
            vertical_spacing=0.03,
            subplot_titles=('Price', 'Volume'),
            row_heights=[0.7, 0.3]
        )
        
        # Price line
        fig.add_trace(
            go.Scatter(
                x=df['timestamp'],
                y=df['price'],
                mode='lines+markers',
                name='Price',
                line=dict(color='#1f77b4', width=2),
                marker=dict(size=4)
            ),
            row=1, col=1
        )
        
        # Add high/low bands
        fig.add_trace(
            go.Scatter(
                x=df['timestamp'],
                y=df['high'],
                mode='lines',
                name='High',
                line=dict(color='rgba(0,255,0,0.3)', width=1, dash='dash'),
                showlegend=False
            ),
            row=1, col=1
        )
        
        fig.add_trace(
            go.Scatter(
                x=df['timestamp'],
                y=df['low'],
                mode='lines',
                name='Low',
                line=dict(color='rgba(255,0,0,0.3)', width=1, dash='dash'),
                fill='tonexty',
                showlegend=False
            ),
            row=1, col=1
        )
        
        # Volume bars
        colors = ['red' if row['change'] < 0 else 'green' for _, row in df.iterrows()]
        fig.add_trace(
            go.Bar(
                x=df['timestamp'],
                y=df['volume'],
                name='Volume',
                marker_color=colors,
                showlegend=False
            ),
            row=2, col=1
        )
        
        fig.update_layout(
            height=500,
            template='plotly_dark',
            hovermode='x unified',
            xaxis2_title='Time',
            yaxis_title='Price (VNĐ)',
            yaxis2_title='Volume',
            showlegend=True,
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
        )
        
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("📊 Chart will appear when data is available...")

with chart_col2:
    st.subheader("📊 All Stocks")
    
    # Create mini charts for all stocks
    for symbol in PORTFOLIO_STOCKS:
        data = st.session_state.stock_data.get(symbol, [])
        
        if data:
            latest = data[-1]
            change_color = "🟢" if latest['percent_change'] >= 0 else "🔴"
            
            with st.container():
                col_a, col_b = st.columns([3, 1])
                with col_a:
                    st.write(f"**{symbol}** - {latest['price']:,.0f} VNĐ")
                with col_b:
                    st.write(f"{change_color} {latest['percent_change']:.2f}%")
                
                # Mini sparkline
                if len(data) > 1:
                    prices = [d['price'] for d in data[-20:]]
                    timestamps = [d['timestamp'] for d in data[-20:]]
                    
                    fig_mini = go.Figure()
                    fig_mini.add_trace(go.Scatter(
                        x=list(range(len(prices))),
                        y=prices,
                        mode='lines',
                        line=dict(color='green' if latest['percent_change'] >= 0 else 'red', width=1),
                        showlegend=False
                    ))
                    fig_mini.update_layout(
                        height=50,
                        margin=dict(l=0, r=0, t=0, b=0),
                        xaxis=dict(visible=False),
                        yaxis=dict(visible=False),
                        plot_bgcolor='rgba(0,0,0,0)',
                        paper_bgcolor='rgba(0,0,0,0)'
                    )
                    st.plotly_chart(fig_mini, use_container_width=True, key=f"mini_{symbol}")
                
                st.markdown("---")

st.markdown("---")

# News and Graph section
news_col, graph_col = st.columns([1, 1])

with news_col:
    st.subheader("📰 Latest News")
    
    # Load news from CSV (mock data for now)
    try:
        news_df = pd.read_csv("../../summarized_news_with_stocks_merged.csv")
        news_df = news_df[news_df['stockCodes'].str.contains(selected_stock, na=False)]
        news_df = news_df.sort_values('date', ascending=False).head(10)
        
        for _, row in news_df.iterrows():
            with st.expander(f"📄 {row['title'][:80]}..."):
                st.write(f"**Date:** {row['date']}")
                st.write(f"**Stocks:** {row['stockCodes']}")
                st.write(f"**Summary:** {row['description']}")
    except Exception as e:
        st.info("📰 No news data available")

with graph_col:
    st.subheader("🔗 Knowledge Graph")
    
    try:
        neo4j_conn = Neo4jConnection()
        
        # Query Neo4j for related entities
        query = """
        MATCH (s:Stock {symbol: $symbol})-[r]-(e)
        RETURN s, r, e
        LIMIT 20
        """
        
        results = neo4j_conn.query(query, {"symbol": selected_stock})
        neo4j_conn.close()
        
        if results:
            st.success(f"Found {len(results)} relationships")
            
            # Display relationships
            for record in results[:5]:
                st.write(f"• {record}")
        else:
            st.info("🔗 Build knowledge graph by running entity extraction")
            st.code("""
# To build Neo4j graph:
1. Run entity_extractor.ipynb
2. Export entities to Neo4j
3. Relationships will appear here
            """)
    except Exception as e:
        st.warning(f"⚠️ Neo4j connection failed: {e}")
        st.info("Start Neo4j with: docker-compose up -d neo4j")

# Auto-refresh
time.sleep(refresh_rate)
st.rerun()
