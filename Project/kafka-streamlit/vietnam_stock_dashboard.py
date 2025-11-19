"""
Advanced Stock Dashboard - Vietnam Market
Design based on frontendv2 with Kafka integration, News and Neo4j Graph
"""
import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
from datetime import datetime, timedelta
import json
import threading
import queue
import time
import traceback
from kafka import KafkaConsumer
from neo4j import GraphDatabase
from vnstock import Quote

# Page configuration - disable animation
st.set_page_config(
    page_title="🚀 Vietnam Stock Dashboard", 
    page_icon="📈",
    layout="wide", 
    initial_sidebar_state="expanded"
)

# Disable animation globally
st.markdown("""
<style>
    .stMetric > div > div > div > div {
        animation: none !important;
    }
    .stSelectbox > div > div > div {
        animation: none !important;
    }
    .stPlotlyChart {
        animation: none !important;
    }
    .element-container {
        animation: none !important;
    }
</style>
""", unsafe_allow_html=True)

# Vietnam stock configuration
VIETNAM_STOCKS = {
    'VCB - Vietcombank': 'VCB', 'VIC - Vingroup': 'VIC', 'VHM - Vinhomes': 'VHM',
    'FPT - FPT Corp': 'FPT', 'HPG - Hoa Phat': 'HPG', 'GAS - PetroVietnam Gas': 'GAS',
    'MSN - Masan Group': 'MSN', 'MWG - Mobile World': 'MWG', 'GVR - Rubber': 'GVR',
    'SSI - SSI Securities': 'SSI', 'VCI - VietCapital': 'VCI', 'TCB - Techcombank': 'TCB',
    'CTG - VietinBank': 'CTG', 'BID - BIDV': 'BID', 'SAB - Sabeco': 'SAB'
}

class VietnamStockAnalyzer:
    def __init__(self):
        self.vnstock_cache = {}
        self.kafka_data = {}
        self.last_update = {}
        
    def fetch_vnstock_data(self, symbol, period_days=30):
        """Fetch Vietnam stock data using vnstock"""
        try:
            quote = Quote(symbol=symbol, source='VCI')
            
            # Calculate date range
            end_date = datetime.now()
            start_date = end_date - timedelta(days=period_days)
            
            # Get historical data
            data = quote.history(
                start=start_date.strftime('%Y-%m-%d'), 
                end=end_date.strftime('%Y-%m-%d'), 
                interval="1D"
            )
            
            if data.empty:
                return None
                
            # Rename columns to match expected format
            data.columns = [col.title() for col in data.columns]
            data = data.rename(columns={'Time': 'Date'})
            
            if 'Date' in data.columns:
                data.set_index('Date', inplace=True)
            
            # Get real-time data for today
            try:
                today = datetime.now().strftime('%Y-%m-%d')
                realtime_data = quote.history(start=today, end=today, interval="1m")
                
                if not realtime_data.empty:
                    latest_price = realtime_data.iloc[-1]['close']
                    # Update today's close price if exists
                    if len(data) > 0:
                        data.iloc[-1, data.columns.get_loc('Close')] = latest_price
            except Exception:
                pass  # Use historical data if real-time fails
                
            return data
            
        except Exception as e:
            st.error(f"Error fetching data for {symbol}: {e}")
            return None
    
    def calculate_technical_indicators(self, data):
        """Calculate comprehensive technical indicators"""
        if data is None or data.empty:
            return data
            
        df = data.copy()
        
        # Simple Moving Averages
        df['SMA_20'] = df['Close'].rolling(window=20).mean()
        df['SMA_50'] = df['Close'].rolling(window=50).mean()
        df['SMA_200'] = df['Close'].rolling(window=200).mean()
        
        # Exponential Moving Averages
        df['EMA_12'] = df['Close'].ewm(span=12).mean()
        df['EMA_26'] = df['Close'].ewm(span=26).mean()
        
        # MACD
        df['MACD'] = df['EMA_12'] - df['EMA_26']
        df['MACD_signal'] = df['MACD'].ewm(span=9).mean()
        df['MACD_histogram'] = df['MACD'] - df['MACD_signal']
        
        # RSI
        delta = df['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        df['RSI'] = 100 - (100 / (1 + rs))
        
        # Bollinger Bands
        df['BB_middle'] = df['Close'].rolling(window=20).mean()
        bb_std = df['Close'].rolling(window=20).std()
        df['BB_upper'] = df['BB_middle'] + (bb_std * 2)
        df['BB_lower'] = df['BB_middle'] - (bb_std * 2)
        
        # Volume indicators
        df['Volume_SMA'] = df['Volume'].rolling(window=20).mean()
        df['Volume_ratio'] = df['Volume'] / df['Volume_SMA']
        
        # Volatility (Average True Range)
        df['High_Low'] = df['High'] - df['Low']
        df['High_Close'] = np.abs(df['High'] - df['Close'].shift())
        df['Low_Close'] = np.abs(df['Low'] - df['Close'].shift())
        df['True_Range'] = df[['High_Low', 'High_Close', 'Low_Close']].max(axis=1)
        df['ATR'] = df['True_Range'].rolling(window=14).mean()
        
        # Stochastic Oscillator
        low_14 = df['Low'].rolling(window=14).min()
        high_14 = df['High'].rolling(window=14).max()
        df['Stoch_K'] = 100 * ((df['Close'] - low_14) / (high_14 - low_14))
        df['Stoch_D'] = df['Stoch_K'].rolling(window=3).mean()
        
        return df

# Initialize session state
def initialize_session_state():
    if 'kafka_data' not in st.session_state:
        st.session_state.kafka_data = {}
    if 'news_data' not in st.session_state:
        st.session_state.news_data = []
    if 'neo4j_data' not in st.session_state:
        st.session_state.neo4j_data = {}
    if 'data_queue' not in st.session_state:
        st.session_state.data_queue = queue.Queue()
    if 'consumer_running' not in st.session_state:
        st.session_state.consumer_running = False

initialize_session_state()

# Kafka Consumer
def kafka_consumer_thread(data_queue, topic='stock-prices'):
    try:
        consumer = KafkaConsumer(
            topic,
            bootstrap_servers='localhost:9092',
            value_deserializer=lambda m: json.loads(m.decode('utf-8')),
            auto_offset_reset='latest',
            consumer_timeout_ms=1000
        )
        
        for message in consumer:
            data_queue.put(message.value)
    except Exception:
        pass  # Silent fail if Kafka not available

def process_kafka_data():
    while not st.session_state.data_queue.empty():
        try:
            data = st.session_state.data_queue.get_nowait()
            symbol = data.get('symbol', '')
            if symbol:
                st.session_state.kafka_data[symbol] = data
        except queue.Empty:
            break

# Import for network graph
import networkx as nx
from plotly.graph_objects import Figure, Scatter
import plotly.graph_objects as go
import math
import random

# Neo4j Connection
class Neo4jConnection:
    def __init__(self, uri="bolt://localhost:7687", user="neo4j", password="password123"): 
        try:
            self.driver = GraphDatabase.driver(uri, auth=(user, password))
        except Exception:
            self.driver = None
    
    def query(self, query, parameters=None):
        if not self.driver:
            return []
        try:
            with self.driver.session() as session:
                result = session.run(query, parameters)
                return [record for record in result]
        except Exception:
            return []
    
    def close(self):
        if self.driver:
            self.driver.close()

def create_neo4j_style_graph(relationships_data, center_symbol):
    """Create Neo4j Browser style interactive network graph"""
    try:
        # Neo4j color palette
        neo4j_colors = {
            'stock': '#FF6B6B',      # Neo4j red
            'person': '#4ECDC4',     # Neo4j teal
            'company': '#45B7D1',    # Neo4j blue
            'sector': '#96CEB4',     # Neo4j green
            'exchange': '#FECA57',   # Neo4j yellow
            'default': '#A8A8A8'     # Neo4j gray
        }
        
        # Create NetworkX graph
        G = nx.Graph()
        
        # Add center node (Stock)
        G.add_node(center_symbol, 
                  node_type='stock', 
                  label='Stock',
                  size=50,
                  color=neo4j_colors['stock'])
        
        # Add relationships and connected nodes
        node_types = {}
        for record in relationships_data:
            relationship = record.get('relationship', 'RELATED')
            entity = record.get('e', {})
            
            # Extract entity info
            entity_name = str(entity.get('name', entity.get('symbol', entity.get('id', 'Unknown'))))
            entity_type = str(entity.get('type', 'default')).lower()
            
            if entity_name and entity_name != center_symbol:
                # Determine node color based on type
                node_color = neo4j_colors.get(entity_type, neo4j_colors['default'])
                node_size = 35 if entity_type == 'stock' else 30
                
                # Add node and edge
                G.add_node(entity_name, 
                          node_type=entity_type,
                          label=entity_type.title(),
                          size=node_size,
                          color=node_color)
                G.add_edge(center_symbol, entity_name, 
                          relationship=relationship,
                          label=relationship)
                
                node_types[entity_type] = node_types.get(entity_type, 0) + 1
        
        # Generate force-directed layout (Neo4j style)
        try:
            # Use spring layout with Neo4j-like parameters
            pos = nx.spring_layout(G, 
                                 k=2.5,        # Optimal distance between nodes
                                 iterations=100, # More iterations for better layout
                                 weight=None,    # Don't use edge weights
                                 scale=2.0)      # Scale the layout
        except:
            pos = nx.circular_layout(G)
        
        # Create curved edges (Neo4j style)
        edge_traces = []
        edge_labels = []
        
        for edge in G.edges(data=True):
            x0, y0 = pos[edge[0]]
            x1, y1 = pos[edge[1]]
            relationship = edge[2].get('relationship', 'RELATED')
            
            # Create curved edge path
            mid_x = (x0 + x1) / 2
            mid_y = (y0 + y1) / 2
            
            # Add slight curve to edges
            curve_offset = 0.1
            ctrl_x = mid_x + curve_offset * (y1 - y0)
            ctrl_y = mid_y - curve_offset * (x1 - x0)
            
            # Create curved edge using multiple points
            num_points = 20
            edge_x, edge_y = [], []
            
            for i in range(num_points + 1):
                t = i / num_points
                # Quadratic Bezier curve
                x = (1-t)**2 * x0 + 2*(1-t)*t * ctrl_x + t**2 * x1
                y = (1-t)**2 * y0 + 2*(1-t)*t * ctrl_y + t**2 * y1
                edge_x.append(x)
                edge_y.append(y)
            
            edge_x.append(None)  # Break for next edge
            edge_y.append(None)
            
            edge_trace = go.Scatter(
                x=edge_x, y=edge_y,
                mode='lines',
                line=dict(width=2, color='#D3D3D3'),
                hoverinfo='none',
                showlegend=False
            )
            edge_traces.append(edge_trace)
            
            # Add relationship label at midpoint
            edge_labels.append({
                'x': mid_x,
                'y': mid_y,
                'text': relationship,
                'font': dict(size=10, color='#666'),
                'bgcolor': 'rgba(255,255,255,0.8)',
                'bordercolor': '#CCC'
            })
        
        # Create nodes with Neo4j styling
        node_traces = []
        
        # Group nodes by type for legend
        nodes_by_type = {}
        for node, data in G.nodes(data=True):
            node_type = data.get('node_type', 'default')
            if node_type not in nodes_by_type:
                nodes_by_type[node_type] = []
            nodes_by_type[node_type].append((node, data))
        
        # Create trace for each node type
        for node_type, nodes in nodes_by_type.items():
            node_x, node_y, node_text, node_size = [], [], [], []
            
            for node, data in nodes:
                x, y = pos[node]
                node_x.append(x)
                node_y.append(y)
                
                # Rich hover text
                connections = len(list(G.neighbors(node)))
                hover_text = f"<b>{node}</b><br>"
                hover_text += f"Type: {data.get('label', 'Unknown')}<br>"
                hover_text += f"Connections: {connections}<br>"
                hover_text += f"Click to explore"
                
                node_text.append(hover_text)
                node_size.append(data.get('size', 30))
            
            # Get color for this node type
            type_color = neo4j_colors.get(node_type, neo4j_colors['default'])
            
            node_trace = go.Scatter(
                x=node_x, y=node_y,
                mode='markers+text',
                marker=dict(
                    size=node_size,
                    color=type_color,
                    line=dict(width=2, color='white'),
                    symbol='circle'
                ),
                text=[node for node, _ in nodes],
                textposition="middle center",
                textfont=dict(size=10, color='white', family='Arial Black'),
                hovertext=node_text,
                hoverinfo='text',
                name=node_type.title(),
                showlegend=True if len(nodes_by_type) > 1 else False
            )
            node_traces.append(node_trace)
        
        # Create figure with Neo4j styling
        all_traces = edge_traces + node_traces
        
        # Create annotations for edge labels
        annotations = []
        for label in edge_labels[:10]:  # Limit labels to avoid clutter
            annotations.append(dict(
                x=label['x'], y=label['y'],
                text=label['text'],
                showarrow=False,
                font=label['font'],
                bgcolor=label['bgcolor'],
                bordercolor=label['bordercolor'],
                borderwidth=1
            ))
        
        # Add title annotation
        annotations.append(dict(
            text=f"<b>🔗 {center_symbol} Knowledge Graph</b><br><i>Neo4j Browser Style Visualization</i>",
            showarrow=False,
            xref="paper", yref="paper",
            x=0.5, y=1.05,
            xanchor="center", yanchor="bottom",
            font=dict(size=16, color="#2C3E50")
        ))
        
        fig = go.Figure(data=all_traces)
        fig.update_layout(
            showlegend=True,
            hovermode='closest',
            margin=dict(b=40,l=40,r=40,t=80),
            annotations=annotations,
            xaxis=dict(
                showgrid=False, 
                zeroline=False, 
                showticklabels=False,
                range=[-2.5, 2.5]
            ),
            yaxis=dict(
                showgrid=False, 
                zeroline=False, 
                showticklabels=False,
                range=[-2.5, 2.5]
            ),
            plot_bgcolor='#F8F9FA',
            paper_bgcolor='white',
            height=600,
            legend=dict(
                x=0.02, y=0.98,
                bgcolor='rgba(255,255,255,0.8)',
                bordercolor='#DDD',
                borderwidth=1
            )
        )
        
        return fig, node_types, len(G.edges())
        
    except Exception as e:
        st.error(f"Error creating Neo4j-style graph: {e}")
        return None, {}, 0

def create_network_graph(relationships_data, center_symbol):
    """Create interactive network graph from Neo4j data - Legacy function"""
    return create_neo4j_style_graph(relationships_data, center_symbol)

def create_mock_neo4j_data(symbol):
    """Create mock Neo4j data for demonstration when database is offline"""
    mock_relationships = [
        {'relationship': 'SECTOR_OF', 'e': {'name': 'Technology', 'type': 'Sector'}},
        {'relationship': 'COMPETES_WITH', 'e': {'name': 'VCB', 'type': 'Stock'}},
        {'relationship': 'SUPPLIER_TO', 'e': {'name': f'{symbol}_Customer_1', 'type': 'Company'}},
        {'relationship': 'PARTNER_WITH', 'e': {'name': f'{symbol}_Partner', 'type': 'Company'}},
        {'relationship': 'LISTED_ON', 'e': {'name': 'HOSE', 'type': 'Exchange'}},
        {'relationship': 'HAS_CEO', 'e': {'name': f'{symbol}_CEO', 'type': 'Person'}},
    ]
    
    return mock_relationships

def load_news_data(symbol):
    """Load news data from CSV files"""
    try:
        # Try to load news data
        news_files = [
            "../../summarized_news_with_stocks_merged.csv",
            "../summarized_news_with_stocks_merged.csv",
            "summarized_news_with_stocks_merged.csv"
        ]
        
        for file_path in news_files:
            try:
                news_df = pd.read_csv(file_path)
                # Filter news containing the symbol
                symbol_news = news_df[news_df['stockCodes'].str.contains(symbol, na=False)]
                return symbol_news.sort_values('date', ascending=False).head(10)
            except FileNotFoundError:
                continue
                
        return pd.DataFrame()  # Return empty if no file found
    except Exception:
        return pd.DataFrame()

def create_advanced_chart(data, symbol):
    """Create advanced candlestick chart with technical indicators"""
    if data is None or data.empty:
        return go.Figure()
        
    fig = make_subplots(
        rows=4, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.03,
        subplot_titles=(
            f'{symbol} Price Action & Moving Averages', 
            'Volume', 
            'MACD', 
            'RSI & Stochastic'
        ),
        row_heights=[0.5, 0.15, 0.2, 0.15]
    )
    
    # Candlestick chart
    fig.add_trace(
        go.Candlestick(
            x=data.index,
            open=data['Open'],
            high=data['High'],
            low=data['Low'],
            close=data['Close'],
            name='Price',
            increasing_line_color='#00ff88',
            decreasing_line_color='#ff4444'
        ),
        row=1, col=1
    )
    
    # Moving averages
    colors = ['#ff9500', '#007aff', '#5856d6']
    mas = [('SMA_20', 'SMA 20'), ('SMA_50', 'SMA 50'), ('SMA_200', 'SMA 200')]
    
    for i, (ma_col, ma_name) in enumerate(mas):
        if ma_col in data.columns and not data[ma_col].isna().all():
            fig.add_trace(
                go.Scatter(
                    x=data.index, 
                    y=data[ma_col], 
                    line=dict(color=colors[i], width=1.5), 
                    name=ma_name
                ),
                row=1, col=1
            )
    
    # Bollinger Bands
    if all(col in data.columns for col in ['BB_upper', 'BB_lower']):
        fig.add_trace(
            go.Scatter(
                x=data.index, 
                y=data['BB_upper'], 
                line=dict(color='rgba(128,128,128,0.5)', width=1), 
                name='BB Upper',
                showlegend=False
            ),
            row=1, col=1
        )
        fig.add_trace(
            go.Scatter(
                x=data.index, 
                y=data['BB_lower'], 
                line=dict(color='rgba(128,128,128,0.5)', width=1), 
                name='BB Lower',
                fill='tonexty', 
                fillcolor='rgba(128,128,128,0.1)',
                showlegend=False
            ),
            row=1, col=1
        )
    
    # Volume
    volume_colors = ['#00ff88' if data['Close'].iloc[i] >= data['Open'].iloc[i] else '#ff4444' 
                    for i in range(len(data))]
    fig.add_trace(
        go.Bar(
            x=data.index, 
            y=data['Volume'], 
            marker_color=volume_colors, 
            name='Volume', 
            opacity=0.7
        ),
        row=2, col=1
    )
    
    # MACD
    if all(col in data.columns for col in ['MACD', 'MACD_signal', 'MACD_histogram']):
        fig.add_trace(
            go.Scatter(
                x=data.index, 
                y=data['MACD'], 
                line=dict(color='#007aff', width=2), 
                name='MACD'
            ),
            row=3, col=1
        )
        fig.add_trace(
            go.Scatter(
                x=data.index, 
                y=data['MACD_signal'], 
                line=dict(color='#ff9500', width=2), 
                name='Signal'
            ),
            row=3, col=1
        )
        
        histogram_colors = ['#00ff88' if val >= 0 else '#ff4444' for val in data['MACD_histogram']]
        fig.add_trace(
            go.Bar(
                x=data.index, 
                y=data['MACD_histogram'], 
                marker_color=histogram_colors, 
                name='Histogram', 
                opacity=0.6
            ),
            row=3, col=1
        )
    
    # RSI and Stochastic
    if 'RSI' in data.columns:
        fig.add_trace(
            go.Scatter(
                x=data.index, 
                y=data['RSI'], 
                line=dict(color='#af52de', width=2), 
                name='RSI'
            ),
            row=4, col=1
        )
        # RSI levels
        fig.add_hline(y=70, line_dash="dash", line_color="red", opacity=0.7, row=4, col=1)
        fig.add_hline(y=30, line_dash="dash", line_color="green", opacity=0.7, row=4, col=1)
        fig.add_hline(y=50, line_dash="dot", line_color="gray", opacity=0.5, row=4, col=1)
    
    if 'Stoch_K' in data.columns:
        fig.add_trace(
            go.Scatter(
                x=data.index, 
                y=data['Stoch_K'], 
                line=dict(color='#ffcc00', width=1.5), 
                name='Stoch %K'
            ),
            row=4, col=1
        )
        fig.add_trace(
            go.Scatter(
                x=data.index, 
                y=data['Stoch_D'], 
                line=dict(color='#ff6600', width=1.5), 
                name='Stoch %D'
            ),
            row=4, col=1
        )
    
    fig.update_layout(
        title=f'{symbol} - Complete Technical Analysis Dashboard',
        xaxis_rangeslider_visible=False,
        height=900,
        showlegend=True,
        template='plotly_dark',
        font=dict(size=10)
    )
    
    # Remove x-axis labels from all but bottom subplot
    for i in range(1, 4):
        fig.update_xaxes(showticklabels=False, row=i, col=1)
    
    return fig

def create_performance_metrics(data, symbol):
    """Create performance metrics visualization"""
    if data is None or data.empty:
        st.warning("No data available for performance calculation")
        return
        
    # Calculate returns
    data = data.copy()
    data['Daily_Returns'] = data['Close'].pct_change()
    data['Cumulative_Returns'] = (1 + data['Daily_Returns']).cumprod() - 1
    
    # Performance metrics
    total_return = data['Cumulative_Returns'].iloc[-1] * 100
    volatility = data['Daily_Returns'].std() * np.sqrt(252) * 100  # Annualized
    
    returns_mean = data['Daily_Returns'].mean() * 252
    returns_std = data['Daily_Returns'].std() * np.sqrt(252)
    sharpe_ratio = returns_mean / returns_std if returns_std != 0 else 0
    
    max_drawdown = ((data['Close'] / data['Close'].expanding().max()) - 1).min() * 100
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("Total Return", f"{total_return:.1f}%")
    with col2:
        st.metric("Volatility (Ann.)", f"{volatility:.1f}%")
    with col3:
        st.metric("Sharpe Ratio", f"{sharpe_ratio:.2f}")
    with col4:
        st.metric("Max Drawdown", f"{max_drawdown:.1f}%")
    
    # Cumulative returns chart
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=data.index,
            y=data['Cumulative_Returns'] * 100,
            mode='lines',
            name='Cumulative Returns',
            line=dict(color='#00ff88', width=2)
        )
    )
    
    fig.update_layout(
        title=f'{symbol} Cumulative Returns (%)',
        xaxis_title='Date',
        yaxis_title='Cumulative Return (%)',
        template='plotly_dark',
        height=400
    )
    
    st.plotly_chart(fig, width='stretch')

# Main Application
def main():
    # Start Kafka consumer if not running
    if not st.session_state.consumer_running:
        try:
            consumer_thread = threading.Thread(
                target=kafka_consumer_thread,
                args=(st.session_state.data_queue,),
                daemon=True
            )
            consumer_thread.start()
            st.session_state.consumer_running = True
        except Exception:
            pass
    
    # Process Kafka data
    process_kafka_data()
    
    # Title
    st.title("🚀 Professional Vietnam Stock Market Dashboard")
    st.markdown("*Advanced technical analysis with real-time data integration*")
    
    # Sidebar
    st.sidebar.header("📊 Dashboard Controls")
    st.sidebar.markdown("---")
    
    # Stock selection
    stock_choice = st.sidebar.selectbox(
        "🏢 Select Stock:",
        options=list(VIETNAM_STOCKS.keys()) + ['Custom'],
        index=0,
        key="stock_selector"
    )
    
    if stock_choice == 'Custom':
        symbol = st.sidebar.text_input("Enter Stock Symbol:", value="VCB", max_chars=10).upper()
    else:
        symbol = VIETNAM_STOCKS[stock_choice]
    
    # Time period
    period = st.sidebar.selectbox(
        "📅 Analysis Period:",
        options=[
            ('1 Month', 30), 
            ('3 Months', 90), 
            ('6 Months', 180), 
            ('1 Year', 365), 
            ('2 Years', 730)
        ],
        format_func=lambda x: x[0],
        index=2,
        key="period_selector"
    )[1]
    
    st.sidebar.markdown("---")
    
    # Analysis options
    st.sidebar.subheader("🔧 Analysis Options")
    show_technical = st.sidebar.checkbox("📈 Technical Charts", value=True, key="show_technical")
    show_performance = st.sidebar.checkbox("📊 Performance Metrics", value=True, key="show_performance")
    show_kafka = st.sidebar.checkbox("📡 Kafka Real-time Data", value=True, key="show_kafka")
    show_news = st.sidebar.checkbox("📰 News Analysis", value=True, key="show_news")
    show_graph = st.sidebar.checkbox("🔗 Knowledge Graph", value=True, key="show_graph")
    
    st.sidebar.markdown("---")
    
    # Kafka status
    st.sidebar.subheader("📡 Data Sources")
    
    kafka_status = "🟢 Connected" if st.session_state.kafka_data else "🟡 Waiting"
    st.sidebar.write(f"**Kafka:** {kafka_status}")
    
    # Neo4j status
    try:
        neo4j_conn = Neo4jConnection()
        neo4j_status = "🟢 Connected" if neo4j_conn.driver else "🔴 Offline"
        neo4j_conn.close()
    except:
        neo4j_status = "🔴 Offline"
    st.sidebar.write(f"**Neo4j:** {neo4j_status}")
    
    if st.sidebar.button("🔄 Refresh Data", type="primary", key="refresh_button"):
        st.cache_data.clear()
        st.rerun()
    
    # Initialize analyzer
    analyzer = VietnamStockAnalyzer()
    
    # Fetch data
    with st.spinner(f"📡 Fetching data for {symbol}..."):
        data = analyzer.fetch_vnstock_data(symbol, period)
    
    if data is None or data.empty:
        st.error(f"❌ Could not fetch data for {symbol}. Please verify the symbol and try again.")
        return
    
    # Calculate technical indicators
    with st.spinner("⚙️ Calculating technical indicators..."):
        data = analyzer.calculate_technical_indicators(data)
    
    # Main dashboard header
    st.markdown("---")
    
    # Key metrics row
    col1, col2, col3, col4, col5 = st.columns(5)
    
    latest_price = data['Close'].iloc[-1]
    prev_price = data['Close'].iloc[-2] if len(data) > 1 else latest_price
    price_change = latest_price - prev_price
    price_change_pct = (price_change / prev_price) * 100 if prev_price != 0 else 0
    
    with col1:
        # Check for Kafka real-time data FIRST
        kafka_data = st.session_state.kafka_data.get(symbol)
        if show_kafka and kafka_data:
            display_price = kafka_data.get('price', latest_price)
            display_change = kafka_data.get('percent_change', price_change_pct)
            st.metric(
                label="💰 Current Price (🔴 Kafka Live)",
                value=f"{display_price:,.0f} VNĐ",
                delta=f"{display_change:+.2f}%"
            )
        else:
            # Fallback to VNStock data
            st.metric(
                label="💰 Current Price (📊 VNStock)",
                value=f"{latest_price:,.0f} VNĐ",
                delta=f"{price_change:.0f} ({price_change_pct:+.2f}%)"
            )
    
    with col2:
        volume = data['Volume'].iloc[-1]
        avg_volume = data['Volume'].rolling(20).mean().iloc[-1]
        volume_change = ((volume - avg_volume) / avg_volume) * 100 if avg_volume > 0 else 0
        st.metric(
            label="📊 Volume",
            value=f"{volume:,.0f}",
            delta=f"{volume_change:+.1f}% vs 20d avg"
        )
    
    with col3:
        if 'RSI' in data.columns and not pd.isna(data['RSI'].iloc[-1]):
            rsi = data['RSI'].iloc[-1]
            rsi_status = "Overbought" if rsi > 70 else "Oversold" if rsi < 30 else "Neutral"
            st.metric(
                label="⚡ RSI (14)",
                value=f"{rsi:.1f}",
                delta=rsi_status
            )
        else:
            st.metric(label="⚡ RSI (14)", value="N/A")
    
    with col4:
        if 'SMA_20' in data.columns and not pd.isna(data['SMA_20'].iloc[-1]):
            sma_20 = data['SMA_20'].iloc[-1]
            sma_distance = ((latest_price - sma_20) / sma_20) * 100
            st.metric(
                label="📈 vs SMA 20",
                value=f"{sma_distance:+.1f}%",
                delta="Above" if sma_distance > 0 else "Below"
            )
        else:
            st.metric(label="📈 vs SMA 20", value="N/A")
    
    with col5:
        # Market cap placeholder for Vietnam stocks
        st.metric(label="🏢 Exchange", value="VN")
    
    st.markdown("---")
    
    # Advanced Chart
    if show_technical:
        st.subheader("📈 Advanced Technical Analysis")
        with st.spinner("Creating advanced charts..."):
            chart = create_advanced_chart(data, symbol)
            st.plotly_chart(chart, width='stretch')
    
    # Performance Metrics
    if show_performance:
        st.subheader("📊 Performance Analysis")
        create_performance_metrics(data, symbol)
    
    # Kafka Real-time Section - PRIORITY DATA SOURCE
    if show_kafka:
        st.subheader("📡 Kafka Real-time Data Stream")
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.write("**📊 Live Data Feed:**")
            if st.session_state.kafka_data:
                for stock_symbol, live_data in st.session_state.kafka_data.items():
                    timestamp = live_data.get('timestamp', 'N/A')
                    price = live_data.get('price', 0)
                    change = live_data.get('percent_change', 0)
                    
                    color = "🟢" if change >= 0 else "🔴"
                    st.write(f"{color} **{stock_symbol}**: {price:,.0f} VNĐ ({change:+.2f}%)")
            else:
                st.info("🟡 Waiting for Kafka data...")
                st.write("Make sure Kafka broker is running on localhost:9092")
                st.write("Topic: 'stock-prices'")
        
        with col2:
            st.write("**⏱️ Kafka Status:**")
            st.write(f"Active symbols: {len(st.session_state.kafka_data)}")
            st.write(f"Consumer running: {'✅' if st.session_state.consumer_running else '❌'}")
            st.write(f"Last update: {datetime.now().strftime('%H:%M:%S')}")
            
            # Manual test button
            if st.button("🔄 Test Kafka Connection", key="test_kafka"):
                try:
                    # Try to create a simple consumer to test connection
                    test_consumer = KafkaConsumer(
                        'stock-prices',
                        bootstrap_servers='localhost:9092',
                        consumer_timeout_ms=1000
                    )
                    test_consumer.close()
                    st.success("✅ Kafka connection successful!")
                except Exception as e:
                    st.error(f"❌ Kafka connection failed: {e}")
        
        st.markdown("---")
    
    # Main content tabs
    st.markdown("---")
    
    # Create tabs based on enabled options
    tab_names = ["📋 Company Info", "📊 Raw Data", "🔧 Technical Indicators"]
    
    if show_news:
        tab_names.append("📰 News")
    if show_graph:
        tab_names.append("🔗 Graph")
    
    tabs = st.tabs(tab_names)
    
    # Company Info Tab
    with tabs[0]:
        st.write("### 🏢 Company Details")
        
        col1, col2 = st.columns(2)
        
        with col1:
            company_info = {
                "Stock Code": symbol,
                "Exchange": "Ho Chi Minh Stock Exchange (HOSE)" if symbol in ['VCB', 'VIC', 'VHM'] else "Vietnam Stock Exchange",
                "Country": "Vietnam",
                "Currency": "VND",
                "Market Type": "Emerging Market"
            }
            
            for key, value in company_info.items():
                st.write(f"**{key}:** {value}")
        
        with col2:
            st.write("### 📈 Key Statistics")
            
            if len(data) > 0:
                high_52w = data['High'].max()
                low_52w = data['Low'].min()
                avg_volume = data['Volume'].mean()
                
                stats_info = {
                    "52W High": f"{high_52w:,.0f} VNĐ",
                    "52W Low": f"{low_52w:,.0f} VNĐ",
                    "Avg Volume": f"{avg_volume:,.0f}",
                    "Price Range": f"{((high_52w - low_52w) / low_52w * 100):.1f}%"
                }
                
                for key, value in stats_info.items():
                    st.write(f"**{key}:** {value}")
    
    # Raw Data Tab
    with tabs[1]:
        st.write("### 📊 Recent Price Data")
        display_data = data[['Open', 'High', 'Low', 'Close', 'Volume']].tail(20)
        display_data.index = display_data.index.strftime('%Y-%m-%d')
        st.dataframe(display_data, width='stretch')
        
        # Download option
        csv = display_data.to_csv()
        st.download_button(
            label="📥 Download Data as CSV",
            data=csv,
            file_name=f'{symbol}_stock_data.csv',
            mime='text/csv'
        )
    
    # Technical Indicators Tab
    with tabs[2]:
        st.write("### 🔧 Technical Indicators (Last 10 Days)")
        
        tech_columns = ['Close', 'SMA_20', 'SMA_50', 'RSI', 'MACD', 'MACD_signal', 'BB_upper', 'BB_lower', 'ATR']
        available_columns = [col for col in tech_columns if col in data.columns]
        
        if available_columns:
            tech_data = data[available_columns].tail(10)
            tech_data.index = tech_data.index.strftime('%Y-%m-%d')
            st.dataframe(tech_data.round(3), width='stretch')
        else:
            st.warning("Technical indicators not available")
    
    # News Tab (if enabled)
    news_tab_idx = 3
    if show_news and len(tabs) > news_tab_idx:
        with tabs[news_tab_idx]:
            st.write("### 📰 Related News")
            
            news_data = load_news_data(symbol)
            
            if not news_data.empty:
                for _, row in news_data.iterrows():
                    with st.expander(f"📄 {row.get('title', 'No title')[:80]}..."):
                        st.write(f"**Date:** {row.get('date', 'N/A')}")
                        st.write(f"**Related Stocks:** {row.get('stockCodes', 'N/A')}")
                        st.write(f"**Summary:** {row.get('description', 'No description available')}")
            else:
                st.info("📰 No recent news available for this stock")
                st.write("News data will be loaded from CSV files when available.")
    
    # Graph Tab (if enabled)
    graph_tab_idx = 4 if show_news else 3
    if show_graph and len(tabs) > graph_tab_idx:
        with tabs[graph_tab_idx]:
            st.write("### 🔗 Knowledge Graph Network")
            
            # Add toggle for demo mode
            col1, col2 = st.columns([3, 1])
            with col2:
                demo_mode = st.toggle("🎯 Demo Mode", value=True, help="Show mock data when Neo4j is offline")
            
            neo4j_conn = Neo4jConnection()
            relationships_data = []
            
            if neo4j_conn.driver:
                # Real Neo4j data - use more generic query
                query = """
                MATCH (n:Stock)-[r]-(e)
                RETURN n, type(r) as relationship, e
                LIMIT 20
                """
                
                results = neo4j_conn.query(query, {"symbol": symbol})
                
                if results:
                    relationships_data = results
                    st.success(f"🟢 Found {len(results)} relationships from Neo4j")
                else:
                    st.info("🔗 No relationships found in Neo4j database")
                    if demo_mode:
                        relationships_data = create_mock_neo4j_data(symbol)
                        st.info("📊 Showing demo data instead")
                        
            else:
                st.warning("⚠️ Neo4j connection not available")
                if demo_mode:
                    relationships_data = create_mock_neo4j_data(symbol)
                    st.info("📊 Showing demo network graph")
                else:
                    st.info("Enable Demo Mode or start Neo4j database")
                    st.code("""
# To start Neo4j:
docker run -p 7474:7474 -p 7687:7687 -e NEO4J_AUTH=neo4j/password123 neo4j
                    """)
            
            # Create and display Neo4j-style network graph
            if relationships_data:
                try:
                    network_fig, node_types, edge_count = create_neo4j_style_graph(relationships_data, symbol)
                    
                    if network_fig:
                        # Graph statistics
                        col1, col2, col3 = st.columns(3)
                        with col1:
                            st.metric("📊 Total Nodes", len(relationships_data) + 1)
                        with col2:
                            st.metric("🔗 Relationships", edge_count)
                        with col3:
                            st.metric("🏷️ Node Types", len(node_types))
                        
                        # Main graph
                        st.plotly_chart(network_fig, use_container_width=True)
                        
                        # Interactive controls and details
                        col1, col2 = st.columns([2, 1])
                        
                        with col1:
                            with st.expander(f"📋 Relationship Details ({len(relationships_data)} total)"):
                                for i, record in enumerate(relationships_data[:15], 1):
                                    relationship = record.get('relationship', 'RELATED')
                                    entity = record.get('e', {})
                                    entity_name = str(entity.get('name', entity.get('symbol', entity.get('id', 'Unknown'))))
                                    entity_type = str(entity.get('type', 'Unknown'))
                                    
                                    # Color-coded relationship display
                                    st.markdown(f"**{i}.** `{symbol}` ➜ **{relationship}** ➜ `{entity_name}` *({entity_type})*")
                                    
                                if len(relationships_data) > 15:
                                    st.write(f"... and {len(relationships_data) - 15} more relationships")
                        
                        with col2:
                            st.write("**🎨 Legend:**")
                            legend_items = {
                                "📈 Stock": "#FF6B6B",
                                "👥 Person": "#4ECDC4", 
                                "🏢 Company": "#45B7D1",
                                "📊 Sector": "#96CEB4",
                                "🏛️ Exchange": "#FECA57",
                                "❓ Other": "#A8A8A8"
                            }
                            
                            for item, color in legend_items.items():
                                st.markdown(f"<span style='color:{color}'>●</span> {item}", unsafe_allow_html=True)
                            
                            # Query info
                            st.markdown("---")
                            st.write("**🔍 Neo4j Query:**")
                            st.code("""
MATCH (n:Stock)-[r]-(e)
RETURN n, type(r) as relationship, e
LIMIT 20
                            """, language="cypher")
                            
                            if node_types:
                                st.write("**📊 Node Distribution:**")
                                for node_type, count in node_types.items():
                                    st.write(f"• {node_type.title()}: {count}")
                    else:
                        st.error("❌ Failed to create network graph")
                        
                except Exception as e:
                    st.error(f"Error creating graph: {e}")
                    st.write("**Fallback - Text Display:**")
                    for i, record in enumerate(relationships_data[:5], 1):
                        relationship = record.get('relationship', 'RELATED')
                        entity = record.get('e', {})
                        st.write(f"**{i}.** {symbol} **{relationship}** {entity}")
            
            neo4j_conn.close()
    
    # Auto-refresh every 30 seconds for real-time data
    time.sleep(30)
    st.rerun()

if __name__ == "__main__":
    main()