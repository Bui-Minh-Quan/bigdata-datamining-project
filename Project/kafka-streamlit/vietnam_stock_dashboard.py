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
import random
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
    
    def fetch_intraday_data(self, symbol, interval='1m'):
        """
        Optimized intraday data for live chart
        - Trading hours: 9:30→now (1m) + current intraday price  
        - Non-trading: full history (5m)
        """
        from datetime import datetime, time
        import pandas as pd
        
        try:
            now = datetime.now()
            current_time = now.time()
            is_weekday = now.weekday() < 5
            
            # Trading hours: 9:30-11:30, 13:00-15:00
            morning_start = time(9, 30)
            morning_end = time(11, 30)
            afternoon_start = time(13, 0)
            afternoon_end = time(15, 0)
            
            is_trading_hours = is_weekday and (
                (morning_start <= current_time <= morning_end) or 
                (afternoon_start <= current_time <= afternoon_end)
            )
            
            quote = Quote(symbol=symbol, source='VCI')
            today = now.strftime('%Y-%m-%d')
            
            if is_trading_hours:
                # TRADING HOURS: History + Current
                st.info(f"🔥 Live Trading Mode - {symbol}")
                
                try:
                    # 1. Get 1-minute history from 9:30
                    history_data = quote.history(start=today, end=today, interval='1m')
                    
                    if not history_data.empty:
                        # Filter from 9:30
                        history_data.index = pd.to_datetime(history_data.index)
                        # Ensure timezone-naive for consistent comparison
                        if hasattr(history_data.index, 'tz') and history_data.index.tz is not None:
                            history_data.index = history_data.index.tz_localize(None)
                        
                        morning_start_dt = now.replace(hour=9, minute=30, second=0, microsecond=0)
                        filtered_data = history_data[history_data.index >= morning_start_dt]
                        
                        # Normalize column names
                        if 'open' in filtered_data.columns:
                            filtered_data.columns = [col.capitalize() for col in filtered_data.columns]
                        
                        # 2. Get current price
                        try:
                            current_data = quote.intraday(date=today, page_size=1)
                            if not current_data.empty:
                                # intraday() returns different structure: time, price, volume, match_type
                                current_price = current_data.iloc[0]['price']
                                current_time_str = current_data.iloc[0]['time']
                                
                                # Parse time properly and remove timezone for consistent comparison
                                if isinstance(current_time_str, str):
                                    current_dt = pd.to_datetime(current_time_str)
                                else:
                                    current_dt = current_time_str
                                
                                # Remove timezone info to make it consistent
                                if current_dt.tz is not None:
                                    current_dt = current_dt.tz_localize(None)
                                
                                # Compare with timezone-naive index
                                last_time = filtered_data.index[-1] if len(filtered_data) > 0 else None
                                if len(filtered_data) == 0 or (last_time is not None and current_dt > last_time):
                                    # Create current point with proper OHLC structure
                                    current_point = pd.DataFrame({
                                        'Open': [current_price],
                                        'High': [current_price], 
                                        'Low': [current_price],
                                        'Close': [current_price],
                                        'Volume': [current_data.iloc[0].get('volume', 0)]
                                    }, index=[current_dt])
                                    
                                    # Append to data
                                    combined_data = pd.concat([filtered_data, current_point])
                                    return combined_data
                                
                        except Exception:
                            pass  # Use history only
                            
                        return filtered_data if not filtered_data.empty else None
                        
                except Exception as e:
                    st.warning(f"Trading hours error: {e}")
            
            else:
                # NON-TRADING: Full history
                st.info(f"🌙 After Hours Mode - {symbol}")
                
                try:
                    # Use 1-minute interval for non-trading
                    history_data = quote.history(start=today, end=today, interval='1m')
                    
                    if not history_data.empty:
                        # Ensure proper column names
                        if 'open' in history_data.columns:
                            history_data.columns = [col.capitalize() for col in history_data.columns]
                        
                        # Fix timezone issues
                        history_data.index = pd.to_datetime(history_data.index)
                        if hasattr(history_data.index, 'tz') and history_data.index.tz is not None:
                            history_data.index = history_data.index.tz_localize(None)
                        
                        # Validate required columns exist
                        required_cols = ['Open', 'High', 'Low', 'Close', 'Volume']
                        if all(col in history_data.columns for col in required_cols):
                            return history_data
                        else:
                            st.warning(f"Data missing required columns: {[col for col in required_cols if col not in history_data.columns]}")
                        
                except Exception as e:
                    st.warning(f"After hours error: {e}")
            
            # Fallback: Recent days
            try:
                from datetime import timedelta
                yesterday = (now - timedelta(days=2)).strftime('%Y-%m-%d')
                fallback_data = quote.history(start=yesterday, end=today, interval='1H')
                
                if not fallback_data.empty:
                    # Ensure proper column names
                    if 'open' in fallback_data.columns:
                        fallback_data.columns = [col.capitalize() for col in fallback_data.columns]
                    
                    # Fix timezone issues
                    fallback_data.index = pd.to_datetime(fallback_data.index)
                    if hasattr(fallback_data.index, 'tz') and fallback_data.index.tz is not None:
                        fallback_data.index = fallback_data.index.tz_localize(None)
                    
                    # Validate required columns
                    required_cols = ['Open', 'High', 'Low', 'Close', 'Volume']
                    if all(col in fallback_data.columns for col in required_cols):
                        st.info(f"📊 Using recent data (fallback)")
                        return fallback_data
                    
            except Exception:
                pass
                
            return None
            
        except Exception as e:
            st.warning(f"Intraday data unavailable: {e}")
            return None

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
    # CSV Mode state
    if 'csv_mode_enabled' not in st.session_state:
        st.session_state.csv_mode_enabled = False
    if 'csv_data_cache' not in st.session_state:
        st.session_state.csv_data_cache = None
    if 'csv_current_index' not in st.session_state:
        st.session_state.csv_current_index = 0
    if 'csv_auto_load_running' not in st.session_state:
        st.session_state.csv_auto_load_running = False
    if 'secret_click_count' not in st.session_state:
        st.session_state.secret_click_count = 0

initialize_session_state()

# CSV Live Feed Loader (for testing without Kafka)
def csv_live_feed_loader(csv_file_path, symbol='VCB'):
    """Load CSV data progressively until current time (simulating real-time feed)"""
    try:
        # Read CSV file
        csv_data = pd.read_csv(csv_file_path)
        
        # Parse datetime
        if 'datetime' not in csv_data.columns and 'time' in csv_data.columns:
            csv_data['datetime'] = pd.to_datetime(csv_data['time'])
        elif 'datetime' in csv_data.columns:
            csv_data['datetime'] = pd.to_datetime(csv_data['datetime'])
        else:
            st.error("CSV must have 'time' or 'datetime' column")
            return None
        
        # Sort by time
        csv_data = csv_data.sort_values('datetime').reset_index(drop=True)
        
        # Store in session state
        st.session_state.csv_data_cache = csv_data
        st.session_state.csv_current_index = 0
        
        st.success(f"✅ Loaded {len(csv_data)} records from CSV")
        st.info(f"🕐 Time range: {csv_data['datetime'].iloc[0]} → {csv_data['datetime'].iloc[-1]}")
        
        return csv_data
        
    except Exception as e:
        st.error(f"❌ Error loading CSV: {e}")
        return None

def process_csv_live_feed():
    """Process CSV data progressively (only up to current time)"""
    if st.session_state.csv_data_cache is None:
        return
    
    csv_data = st.session_state.csv_data_cache
    current_time = datetime.now()
    
    # Load all data up to current time
    while st.session_state.csv_current_index < len(csv_data):
        row = csv_data.iloc[st.session_state.csv_current_index]
        row_time = row['datetime']
        
        # Only load if time <= current time
        if pd.Timestamp(row_time).tz_localize(None) <= pd.Timestamp(current_time).tz_localize(None):
            # Convert to Kafka-like format
            kafka_format = {
                'symbol': row.get('symbol', 'VCB'),
                'price': float(row.get('close', row.get('Close', 0))),
                'volume': int(row.get('volume', row.get('Volume', 0))),
                'timestamp': row_time.strftime('%Y-%m-%d %H:%M:%S'),
                'open': float(row.get('open', row.get('Open', 0))),
                'high': float(row.get('high', row.get('High', 0))),
                'low': float(row.get('low', row.get('Low', 0))),
                'percent_change': 0  # Calculate if needed
            }
            
            # Update session state (same as Kafka)
            symbol = kafka_format['symbol']
            st.session_state.kafka_data[symbol] = kafka_format
            
            st.session_state.csv_current_index += 1
        else:
            # Stop if we reach future data
            break

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
    """Process data from Kafka or CSV based on mode"""
    if st.session_state.csv_mode_enabled:
        # CSV mode: load from CSV file
        process_csv_live_feed()
    else:
        # Normal Kafka mode
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

def create_ai_prediction(last_price, last_time, future_minutes=30):
    """Create AI prediction as straight line to market close (15:00)"""
    future_times = []
    future_prices = []
    
    now = datetime.now()
    market_close = now.replace(hour=15, minute=0, second=0)
    
    # Ensure last_time is timezone-naive for consistent comparison
    if hasattr(last_time, 'tz') and last_time.tz is not None:
        last_time = last_time.tz_localize(None)
    
    # Only predict if market is still open
    if now.hour >= 15:
        return [], []
    
    # Create straight line from current price to predicted close price
    # Simple prediction: slight upward trend toward close
    predicted_close_price = last_price * (1 + random.uniform(-0.001, 0.002))  # -0.1% to +0.2%
    
    # Generate time points from last_time to market close
    current_time = last_time
    while current_time < market_close:
        current_time += timedelta(minutes=1)
        if current_time > market_close:
            current_time = market_close
            
        # Calculate progress from current to close (linear interpolation)
        total_minutes = (market_close - last_time).total_seconds() / 60
        elapsed_minutes = (current_time - last_time).total_seconds() / 60
        progress = elapsed_minutes / total_minutes if total_minutes > 0 else 1
        
        # Linear interpolation between current price and predicted close price
        interpolated_price = last_price + (predicted_close_price - last_price) * progress
        
        future_times.append(current_time)
        future_prices.append(interpolated_price)
        
        if current_time >= market_close:
            break
    
    return future_times, future_prices

def create_animated_price_display(symbol, current_price, percent_change):
    """Create animated price display like MoMo/ZaloPay"""
    import time
    import random
    
    # Generate random fluctuations within current minute (±0.1%)
    base_price = current_price
    fluctuation_range = base_price * 0.001  # 0.1% fluctuation
    
    # Create container for animated price
    price_container = st.empty()
    
    # Animate price for 3 seconds with fluctuations
    for i in range(6):  # 6 frames, 0.5s each
        if i < 5:  # First 5 frames: fluctuate
            fluctuation = random.uniform(-fluctuation_range, fluctuation_range)
            display_price = base_price + fluctuation
            color = "🟢" if percent_change >= 0 else "🔴"
            
            with price_container.container():
                st.markdown(f"""
                <div style="
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    padding: 15px;
                    border-radius: 10px;
                    text-align: center;
                    color: white;
                    animation: pulse 0.5s ease-in-out;
                ">
                    <h3 style="margin: 0; font-size: 1.5em;">{color} {symbol}</h3>
                    <h2 style="margin: 5px 0; font-size: 2em; font-weight: bold;">{display_price:,.0f} VNĐ</h2>
                    <p style="margin: 0; font-size: 1.2em;">({percent_change:+.2f}%)</p>
                </div>
                """, unsafe_allow_html=True)
        else:  # Last frame: settle to actual price
            color = "🟢" if percent_change >= 0 else "🔴"
            with price_container.container():
                st.markdown(f"""
                <div style="
                    background: linear-gradient(135deg, #11998e 0%, #38ef7d 100%);
                    padding: 15px;
                    border-radius: 10px;
                    text-align: center;
                    color: white;
                    box-shadow: 0 4px 8px rgba(0,0,0,0.2);
                ">
                    <h3 style="margin: 0; font-size: 1.5em;">{color} {symbol}</h3>
                    <h2 style="margin: 5px 0; font-size: 2em; font-weight: bold;">{current_price:,.0f} VNĐ</h2>
                    <p style="margin: 0; font-size: 1.2em;">({percent_change:+.2f}%)</p>
                </div>
                """, unsafe_allow_html=True)
        
        if i < 5:  # Don't sleep on last frame
            time.sleep(0.5)
    
    return price_container

def create_live_intraday_chart(symbol, analyzer):
    """
    Create professional live candlestick chart with volume histogram
    Features: OHLC candlesticks, volume histogram, detailed tooltips, market session markers
    Supports CSV mode for testing
    """
    try:
        from vnstock import Quote
        
        today = datetime.now().strftime('%Y-%m-%d')
        
        # 🔥 CHECK CSV MODE FIRST
        if st.session_state.csv_mode_enabled and st.session_state.csv_data_cache is not None:
            
            # Use CSV data
            csv_data = st.session_state.csv_data_cache.copy()
            
            # Ensure datetime column exists
            if 'datetime' not in csv_data.columns and 'time' in csv_data.columns:
                csv_data['datetime'] = pd.to_datetime(csv_data['time'])
            
            # Filter up to current time only
            current_time = datetime.now()
            csv_data['datetime'] = pd.to_datetime(csv_data['datetime'])
            
            # Ensure timezone-naive
            if hasattr(csv_data['datetime'].iloc[0], 'tz') and csv_data['datetime'].iloc[0].tz is not None:
                csv_data['datetime'] = csv_data['datetime'].dt.tz_localize(None)
            
            # Filter data up to now
            csv_data = csv_data[csv_data['datetime'] <= current_time].copy()
            
            if csv_data.empty:
                st.warning(f"⚠️ No CSV data available up to current time")
                return None
            
            # Ensure column names
            if 'time' not in csv_data.columns:
                csv_data['time'] = csv_data['datetime']
            
            today_data = csv_data
            
        else:
            
            # Fetch today's full intraday data using vnstock
            quote = Quote(symbol=symbol, source='VCI')
            
            # Get intraday data with 1-minute interval
            intraday_data = quote.history(start=today, end=today, interval='1m')
            
            if intraday_data.empty:
                st.warning(f"⚠️ No intraday data available for {symbol}")
                return None
            
            # Convert to datetime and filter for today only
            intraday_data['datetime'] = pd.to_datetime(intraday_data['time'])
            
            # Ensure timezone-naive for consistent comparison
            if hasattr(intraday_data['datetime'].iloc[0], 'tz') and intraday_data['datetime'].iloc[0].tz is not None:
                intraday_data['datetime'] = intraday_data['datetime'].dt.tz_localize(None)
                
            today_date = pd.to_datetime(today).date()
            today_mask = intraday_data['datetime'].dt.date == today_date
            today_data = intraday_data[today_mask].copy()
            
            if today_data.empty:
                st.warning(f"⚠️ No data for today {today}")
                return None
                
            # 🔥 REALTIME PRICE UPDATE - Get latest live price
            try:
                latest_price_data = quote.intraday(date=today, page_size=1)
                if not latest_price_data.empty:
                    latest_price = latest_price_data['price'].iloc[0]
                    latest_time_str = latest_price_data['time'].iloc[0]
                    latest_time = pd.to_datetime(latest_time_str)
                    
                    # Normalize timezone to avoid comparison issues
                    if latest_time.tz is not None:
                        latest_time = latest_time.tz_localize(None)  # Remove timezone
                    
                    # Update the last close price with real-time data
                    if len(today_data) > 0:
                        # Get last historical time and ensure it's timezone-naive
                        last_historical_time = today_data['datetime'].iloc[-1]
                        if hasattr(last_historical_time, 'tz') and last_historical_time.tz is not None:
                            last_historical_time = last_historical_time.tz_localize(None)
                        
                        # Compare timezone-naive timestamps
                        if latest_time > last_historical_time:
                            # Create new realtime point
                            realtime_point = pd.DataFrame({
                                'time': [latest_time_str],
                                'open': [latest_price],
                                'high': [latest_price],
                                'low': [latest_price], 
                                'close': [latest_price],
                                'volume': [latest_price_data.get('volume', [0]).iloc[0] if 'volume' in latest_price_data.columns else 0],
                                'datetime': [latest_time]  # timezone-naive
                            })
                            
                            # Append realtime point to data
                            today_data = pd.concat([today_data, realtime_point], ignore_index=True)
                            st.success(f"🔥 **LIVE UPDATE**: {latest_price:,.1f} VND at {latest_time.strftime('%H:%M:%S')}")
                        else:
                            # Update existing last point with realtime price
                            today_data.iloc[-1, today_data.columns.get_loc('close')] = latest_price
                            st.info(f"📈 **PRICE UPDATE**: {latest_price:,.1f} VND")
                else:
                    st.warning("⚠️ No realtime price data available")
            except Exception as e:
                st.warning(f"⚠️ Could not fetch realtime price: {e}")
            
        # Animation window calculation for default zoom
        now = datetime.now()
        animation_start = now - timedelta(hours=1)      # 1 hour back
        animation_end = now + timedelta(minutes=30)     # 30 minutes future
        
        # Prepare OHLC data with proper column mapping
        ohlc_data = today_data.copy()
        
        # Ensure proper column names for candlestick
        column_mapping = {
            'open': 'Open',
            'high': 'High', 
            'low': 'Low',
            'close': 'Close',
            'volume': 'Volume'
        }
        
        for old_col, new_col in column_mapping.items():
            if old_col in ohlc_data.columns and new_col not in ohlc_data.columns:
                ohlc_data[new_col] = ohlc_data[old_col]
        
        # Calculate price changes for coloring
        ohlc_data['Price_Change'] = ohlc_data['Close'] - ohlc_data['Open']
        ohlc_data['Price_Change_Pct'] = (ohlc_data['Price_Change'] / ohlc_data['Open']) * 100
        
        # Create subplot with secondary y-axis for volume
        from plotly.subplots import make_subplots
        
        fig = make_subplots(
            rows=2, cols=1,
            shared_xaxes=True,
            vertical_spacing=0.02,
            row_heights=[0.7, 0.3],  # Price chart 70%, Volume 30%
        )
        
        # === MAIN CANDLESTICK CHART ===
        candlestick = go.Candlestick(
            x=ohlc_data['datetime'],
            open=ohlc_data['Open'],
            high=ohlc_data['High'],
            low=ohlc_data['Low'],
            close=ohlc_data['Close'],
            name=f'{symbol} OHLC',
            increasing_line_color='#26C281',  # Green for bullish candles
            decreasing_line_color='#E74C3C',  # Red for bearish candles
            increasing_fillcolor='#26C281',
            decreasing_fillcolor='#E74C3C',
            line=dict(width=1),
            hovertemplate=(
                '<b>🕐 Time:</b> %{x|%H:%M:%S}<br>'
                '<b>📈 Open:</b> %{open:,.1f} VND<br>'
                '<b>🔝 High:</b> %{high:,.1f} VND<br>'
                '<b>🔻 Low:</b> %{low:,.1f} VND<br>'
                '<b>💰 Close:</b> %{close:,.1f} VND<br>'
                '<b>📊 Change:</b> %{customdata[0]:+.1f} VND (%{customdata[1]:+.2f}%)<br>'
                '<extra></extra>'
            ),
            customdata=np.column_stack((ohlc_data['Price_Change'], ohlc_data['Price_Change_Pct']))
        )
        
        fig.add_trace(candlestick, row=1, col=1)
        
        # === VOLUME HISTOGRAM ===
        # Color volume bars based on price change
        volume_colors = ['#26C281' if change >= 0 else '#E74C3C' for change in ohlc_data['Price_Change']]
        
        volume_bar = go.Bar(
            x=ohlc_data['datetime'],
            y=ohlc_data['Volume'],
            name='Volume',
            marker_color=volume_colors,
            opacity=0.7,
            hovertemplate=(
                '<b>🕐 Time:</b> %{x|%H:%M:%S}<br>'
                '<b>📊 Volume:</b> %{y:,.0f}<br>'
                '<b>💰 Price:</b> %{customdata:,.1f} VND<br>'
                '<extra></extra>'
            ),
            customdata=ohlc_data['Close']
        )
        
        fig.add_trace(volume_bar, row=2, col=1)
        
        # === MOVING AVERAGES ===
        # Calculate moving averages
        ohlc_data['MA_20'] = ohlc_data['Close'].rolling(window=20, min_periods=1).mean()
        ohlc_data['MA_50'] = ohlc_data['Close'].rolling(window=50, min_periods=1).mean()
        
        # Add moving averages if enough data
        if len(ohlc_data) >= 20:
            fig.add_trace(go.Scatter(
                x=ohlc_data['datetime'],
                y=ohlc_data['MA_20'],
                mode='lines',
                name='MA20',
                line=dict(color='#F39C12', width=2),
                hovertemplate='<b>MA20:</b> %{y:,.1f} VND<extra></extra>'
            ), row=1, col=1)
        
        if len(ohlc_data) >= 50:
            fig.add_trace(go.Scatter(
                x=ohlc_data['datetime'],
                y=ohlc_data['MA_50'],
                mode='lines',
                name='MA50',
                line=dict(color='#9B59B6', width=2),
                hovertemplate='<b>MA50:</b> %{y:,.1f} VND<extra></extra>'
            ), row=1, col=1)
        
        # === MARKET SESSION MARKERS ===
        # NOW marker using add_shape instead of add_vline
        fig.add_shape(
            type="line",
            x0=now, x1=now,
            y0=0, y1=0,
            yref="paper",
            line=dict(color='#FFD700', width=1, dash='solid'),
        )
        fig.add_annotation(
            x=now, y=0.98, yref="paper",
            text="NOW", showarrow=False,
            font=dict(color='#FFD700', size=8, family='Arial Black'),  # giảm size
            bgcolor='rgba(255,215,0,0.2)',
            bordercolor='#FFD700',
            borderwidth=1
        )
        
        # Market sessions
        morning_start = now.replace(hour=9, minute=0, second=0, microsecond=0)
        morning_end = now.replace(hour=11, minute=30, second=0, microsecond=0) 
        lunch_start = morning_end
        lunch_end = now.replace(hour=13, minute=0, second=0, microsecond=0)
        afternoon_start = lunch_end
        afternoon_end = now.replace(hour=15, minute=0, second=0, microsecond=0)
        
        # Add session markers with subtle styling
        sessions = [
            (morning_start, morning_end, "Morning Session\n9:00-11:30", '#28B463', 0.1),
            (lunch_start, lunch_end, "Lunch Break\n11:30-13:00", '#95A5A6', 0.05),
            (afternoon_start, afternoon_end, "Afternoon Session\n13:00-15:00", '#3498DB', 0.1)
        ]
        
        for start, end, label, color, opacity in sessions:
            # Add vertical lines for session boundaries using add_shape
            fig.add_shape(
                type="line",
                x0=start, x1=start,
                y0=0, y1=1,
                yref="paper",
                line=dict(color=color, width=1, dash='dot'),
            )
            fig.add_shape(
                type="line", 
                x0=end, x1=end,
                y0=0, y1=1,
                yref="paper",
                line=dict(color=color, width=1, dash='dot'),
            )
            
            # Add session boundary time labels
            fig.add_annotation(
                x=start, y=0.02, yref="paper",
                text=start.strftime('%H:%M'), showarrow=False,
                font=dict(size=10, color=color),
                bgcolor=f"rgba{(*[int(color[i:i+2], 16) for i in (1, 3, 5)], 0.3)}",
                bordercolor=color,
                borderwidth=1
            )
            fig.add_annotation(
                x=end, y=0.02, yref="paper",
                text=end.strftime('%H:%M'), showarrow=False,
                font=dict(size=10, color=color),
                bgcolor=f"rgba{(*[int(color[i:i+2], 16) for i in (1, 3, 5)], 0.3)}",
                bordercolor=color,
                borderwidth=1
            )
            
            # Add session label at midpoint
            mid_time = start + (end - start) / 2
            fig.add_annotation(
                x=mid_time,
                y=1.02,
                yref="paper",
                text=label,
                showarrow=False,
                font=dict(size=9, color=color),
                bgcolor=f"rgba{(*[int(color[i:i+2], 16) for i in (1, 3, 5)], 0.3)}",
                bordercolor=color,
                borderwidth=1
            )
        
        # === LAYOUT CONFIGURATION ===
        fig.update_layout(
            title=dict(
                text=f"🎯 {symbol} Live Candlestick Chart - {today}<br>",
                x=0.5,
                xanchor='center',
                font=dict(size=16, color='white', family='Arial')
            ),
            
            # Main price chart formatting
            xaxis=dict(
                title='',
                range=[animation_start, animation_end],  # Default 2h zoom window
                type='date',
                showgrid=True,
                gridcolor='#2C3E50',
                tickangle=0,
                tickfont=dict(color='white'),
                rangeslider=dict(visible=False),  # Disable range slider for cleaner look
                rangeselector=dict(
                    buttons=[
                        dict(count=30, label="30m", step="minute", stepmode="backward"),
                        dict(count=1, label="1h", step="hour", stepmode="backward"),
                        dict(count=2, label="2h", step="hour", stepmode="backward")
                    ],
                    x=0, y=1.02, xanchor='left',
                    bgcolor='#34495E',
                    bordercolor='#5D6D7E',
                    font=dict(color='white')
                )
            ),
            
            # Volume chart formatting  
            xaxis2=dict(
                title='🕐 Time',
                type='date',
                showgrid=True,
                gridcolor='#2C3E50',
                tickformat='%H:%M',
                title_font=dict(color='white'),
                tickfont=dict(color='white')
            ),
            
            yaxis=dict(
                title='💰 Price (VND)',
                showgrid=True,
                gridcolor='#2C3E50',
                tickformat=',.0f',
                side='right',
                title_font=dict(color='white'),
                tickfont=dict(color='white')
            ),
            
            yaxis2=dict(
                title='📊 Volume',
                showgrid=True,
                gridcolor='#2C3E50',
                tickformat=',.0f',
                title_font=dict(color='white'),
                tickfont=dict(color='white')
            ),
            
            plot_bgcolor='#1C1C1C',
            paper_bgcolor='#0E0E0E',
            height=700,
            showlegend=True,
            legend=dict(
                orientation="h",
                yanchor="bottom",
                y=1.02,
                xanchor="right", 
                x=1,
                bgcolor='rgba(52,73,94,0.8)',
                bordercolor='#5D6D7E',
                font=dict(color='white')
            ),
            margin=dict(l=80, r=80, t=120, b=80),
            
            # Remove watermark and improve hover
            hovermode='x unified',
            hoverlabel=dict(
                bgcolor='#34495E',
                bordercolor='#5D6D7E', 
                font=dict(color='white')
            )
        )
        
        # === STATUS INFO ===
        latest_price = ohlc_data['Close'].iloc[-1]
        latest_volume = ohlc_data['Volume'].iloc[-1]
        total_volume = ohlc_data['Volume'].sum()
        avg_price = ohlc_data['Close'].mean()
        price_range = f"{ohlc_data['Low'].min():,.0f} - {ohlc_data['High'].max():,.0f}"
        
        fig.add_annotation(
            text=(
                f"📈 Current: {latest_price:,.0f} VND | "
                f"📊 Volume: {latest_volume:,.0f} | " 
                f"🔄 Total Vol: {total_volume:,.0f}<br>"
                f"📉 Day Range: {price_range} VND | "
                f"⚖️ Average: {avg_price:,.0f} VND | "
                f"🎯 Data Points: {len(ohlc_data)}"
            ),
            xref="paper", yref="paper",
            x=1, y=-0.15,
            showarrow=False,
            font=dict(size=11, color='white'),
            bgcolor='rgba(52,73,94,0.8)',
            bordercolor='#5D6D7E',
            borderwidth=1
        )
        
        return fig
        
    except Exception as e:
        st.error(f"Error creating candlestick chart: {e}")
        st.exception(e)
        return None


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
    
    # Secret button activation: click "show_kafka" checkbox 5 times
    if st.sidebar.checkbox("📡 Kafka Real-time Data", value=True, key="show_kafka"):
        show_kafka = True
        st.session_state.secret_click_count += 1
        
        # Unlock CSV mode after 5 clicks
        if st.session_state.secret_click_count >= 5:
            st.session_state.csv_mode_enabled = True
    else:
        show_kafka = True
    
    # Show CSV controls if unlocked
    if st.session_state.csv_mode_enabled:
        st.sidebar.markdown("---")
        st.sidebar.subheader("🔓 CSV Test Mode (Unlocked!)")
        st.sidebar.info(f"🎉 Secret unlocked! ({st.session_state.secret_click_count} clicks)")
        
        # Auto-detect CSV file in workspace
        import os
        csv_file_path = os.path.join(os.getcwd(), "VCB_intraday_data_20251121.csv")
        
        if os.path.exists(csv_file_path):
            st.sidebar.success(f"✅ Found: VCB_intraday_data_20251121.csv")
            
            # Auto load CSV if not loaded yet
            if st.session_state.csv_data_cache is None:
                with st.spinner("Loading CSV data..."):
                    csv_live_feed_loader(csv_file_path, symbol)
            
            # Show CSV status
            if st.session_state.csv_data_cache is not None:
                total_records = len(st.session_state.csv_data_cache)
                current_index = st.session_state.csv_current_index
                st.sidebar.success(f"📊 CSV: {current_index}/{total_records} records loaded")
                
                progress = current_index / total_records if total_records > 0 else 0
                st.sidebar.progress(progress)
                
                # Show time info
                if total_records > 0:
                    csv_data = st.session_state.csv_data_cache
                    st.sidebar.info(f"🕐 {csv_data['datetime'].iloc[0].strftime('%H:%M')} → {csv_data['datetime'].iloc[-1].strftime('%H:%M')}")
        else:
            st.sidebar.warning(f"⚠️ CSV file not found: {csv_file_path}")
            st.sidebar.info("Expected: VCB_intraday_data_20251121.csv in project root")
        
        st.sidebar.markdown("---")
    
    show_news = st.sidebar.checkbox("📰 News Analysis", value=True, key="show_news")
    show_graph = st.sidebar.checkbox("🔗 Knowledge Graph", value=True, key="show_graph")
    
    st.sidebar.markdown("---")
    
    # Kafka status
    st.sidebar.subheader("📡 Data Sources")
    
    # Show different status based on mode
    if st.session_state.csv_mode_enabled and st.session_state.csv_data_cache is not None:
        kafka_status = "🟠 CSV Mode (Testing)"
    else:
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
        data_with_indicators = analyzer.calculate_technical_indicators(data)
        # Ensure data is still valid after calculating indicators
        if data_with_indicators is None or data_with_indicators.empty:
            st.warning("⚠️ Could not calculate technical indicators, using original data")
            data_with_indicators = data
        data = data_with_indicators
    
    # Verify data is still valid
    if data is None or data.empty:
        st.error(f"❌ Data processing failed for {symbol}")
        return
    
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
        
        # Create tabs for Kafka section
        kafka_tab1, kafka_tab2 = st.tabs(["📊 Live Feed", "📈 Live Chart"])
        
        with kafka_tab1:
            st.write("### 📊 Live Data Feed (Animated)")
            
            if st.session_state.kafka_data:
                # Create animated displays for each stock
                cols = st.columns(len(st.session_state.kafka_data))
                
                for idx, (stock_symbol, live_data) in enumerate(st.session_state.kafka_data.items()):
                    timestamp = live_data.get('timestamp', 'N/A')
                    price = live_data.get('price', 0)
                    change = live_data.get('percent_change', 0)
                    
                    with cols[idx % len(cols)]:
                        color = "🟢" if change >= 0 else "🔴"
                        
                        # Clean animated price display
                        st.markdown(f"""
                        <div style="
                            background: {'linear-gradient(135deg, #11998e 0%, #38ef7d 100%)' if change >= 0 else 'linear-gradient(135deg, #ff416c 0%, #ff4757 100%)'};
                            padding: 12px;
                            border-radius: 8px;
                            text-align: center;
                            color: white;
                            margin: 5px 0;
                            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
                        ">
                            <div style="font-size: 0.9em; font-weight: bold;">{color} {stock_symbol}</div>
                            <div style="font-size: 1.4em; font-weight: bold; margin: 3px 0;">{price:,.0f}</div>
                            <div style="font-size: 0.8em;">({change:+.2f}%)</div>
                        </div>
                        """, unsafe_allow_html=True)
                
                # Status info below
                st.markdown("---")
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("📊 Active Symbols", len(st.session_state.kafka_data))
                with col2:
                    st.metric("⏱️ Status", "🟢 Live" if st.session_state.consumer_running else "🔴 Offline")
                with col3:
                    st.metric("🕐 Updated", datetime.now().strftime('%H:%M:%S'))
                    
            else:
                st.info("🟡 Waiting for Kafka data...")
                st.markdown("""
                **Setup Instructions:**
                1. Start Kafka: `kafka-server-start.sh config/server.properties`
                2. Start Producer: `python kafka_producer.py`
                3. Data will stream on topic: `stock-prices`
                """)
                
            # Clean test button
            if st.button("🔄 Test Kafka Connection", key="test_kafka", type="secondary"):
                try:
                    test_consumer = KafkaConsumer(
                        'stock-prices',
                        bootstrap_servers='localhost:9092',
                        consumer_timeout_ms=1000
                    )
                    test_consumer.close()
                    st.success("✅ Kafka connection successful!")
                except Exception as e:
                    st.error(f"❌ Connection failed: {str(e)[:50]}...")  # Clean error message
        
        with kafka_tab2:
            # Live animation chart
            st.write("### 🎬 Live Animation Chart")
            
            # Chart controls
            col1, col2, col3 = st.columns(3)
            with col1:
                auto_refresh = st.checkbox("🔄 Auto Animation", value=True, key="auto_refresh_animation")
            with col2:
                st.metric("⏰ Current Time", datetime.now().strftime('%H:%M:%S'))
            
            # Create and display live chart
            with st.spinner("🕰️ Loading live intraday data..."):
                import time
                live_chart = create_live_intraday_chart(symbol, analyzer)
                if live_chart:
                    st.plotly_chart(live_chart, width='stretch')
                else:
                    st.warning("⚠️ Unable to load live chart. Try again during market hours (9:00-15:00)")
            
            # 🔥 AUTO-REFRESH LOGIC for realtime updates
            if auto_refresh:
                time.sleep(10)
                st.rerun()
            else:
                # Manual refresh button for static mode
                if st.button("🔄 Manual Refresh", key="manual_refresh_button", type="primary"):
                    st.rerun()
        
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
    if show_graph:
        # Calculate correct tab index
        graph_tab_idx = len(tab_names) - 1  # Graph is always the last tab when enabled
        
        with tabs[graph_tab_idx]:
            st.write("### 🔗 Knowledge Graph Network")
            
            # Add toggle for demo mode
            col1, col2 = st.columns([3, 1])
            with col2:
                demo_mode = st.toggle("🎯 Demo Mode", value=True, help="Show mock data when Neo4j is offline")
            
            try:
                neo4j_conn = Neo4jConnection()
                relationships_data = []
                
                if neo4j_conn.driver:
                    # Real Neo4j data - use more generic query
                    query = """
                    MATCH (n:Stock)-[r]-(e)
                    RETURN n, type(r) as relationship, e
                    LIMIT 25
                    """
                    
                    results = neo4j_conn.query(query, {"symbol": symbol})
                    
                    if results:
                        relationships_data = results
                        st.success(f"🟢 Found {len(results)} relationships from Neo4j")
                    else:
                        st.info("🔗 No relationships found in Neo4j database")
                        if demo_mode:
                            relationships_data = []
                            st.info("📊 No demo data available")
                            
                else:
                    st.warning("⚠️ Neo4j connection not available")
                    if demo_mode:
                        relationships_data = []
                        st.info("📊 No demo data available")
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
                            st.plotly_chart(network_fig, width='stretch')
                            
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
LIMIT 25
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
                
            except Exception as e:
                st.error(f"❌ Graph section error: {e}")
                st.info("Graph feature temporarily unavailable")

if __name__ == "__main__":
    main()