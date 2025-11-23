import os 
import networkx as nx
import numpy as np
from datetime import datetime, timedelta
from neo4j import GraphDatabase
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

class TRRMemoryAttention:
    def __init__(self, uri=None, user=None, password=None):
        # Ưu tiên lấy từ tham số truyền vào, nếu không thì lấy từ biến môi trường
        uri = uri or os.getenv("NEO4J_URI", "bolt://localhost:7687")
        user = user or os.getenv("NEO4J_USER", "neo4j")
        password = password or os.getenv("NEO4J_PASSWORD", "password123")
        
        try:
            self.driver = GraphDatabase.driver(uri, auth=(user, password))
            print("✓ Kết nối Neo4j thành công!")
        except Exception as e:
            print(f"❌ Lỗi kết nối Neo4j: {e}")
            self.driver = None
        
        # --- CẤU HÌNH ATTENTION ---
        # Lambda Decay: Hệ số suy giảm theo thời gian.
        self.LAMBDA_DECAY = 1.0
        
        # Số lượng thực thể (Entity) liên quan nhất cần lấy
        self.TOP_Q = 10
        
        # Khoảng thời gian nhìn lại quá khứ (ngày)
        self.LOOKBACK_DAYS = 30 
        
    def close(self):
        if self.driver:
            self.driver.close()
    
    def fetch_historical_graph(self, target_date_str=None):
        """ 
        Step 2: Memory - Lấy đồ thị lịch sử từ Neo4j và tính toán trọng số thời gian (Time Decay)
        """
        if target_date_str is None:
            target_date_str = datetime.now().strftime("%Y-%m-%d")
        try:
            target_date = datetime.strptime(target_date_str, "%Y-%m-%d")
        except ValueError:
            print(f"❌ Định dạng ngày không hợp lệ: {target_date_str}. Sử dụng ngày hiện tại.")
            target_date = datetime.now()

        start_date = target_date - timedelta(days=self.LOOKBACK_DAYS)
        start_date_str = start_date.strftime("%Y-%m-%d")
        
        # --- [FIX LỖI 1]: Mở rộng target_date để lấy hết dữ liệu trong ngày ---
        # giả sử target_date là "2025-11-23", ta cần lấy đến "2025-11-24 00:00:00"
        target_date_query = (target_date + timedelta(days=1)).strftime("%Y-%m-%d")

        print(f"Fetching historical graph from {start_date_str} to {target_date_query}...")
        
        # Query lấy dữ liệu trong khoảng thời gian
        query = """ 
            MATCH (s)-[r:AFFECTS]->(t)
            WHERE r.date >= $start_date AND r.date <= $target_date 
            RETURN 
                COALESCE(s.name, s.title, toString(s.id), head(labels(s))) as source,
                COALESCE(t.name, t.title, toString(t.id), head(labels(t))) as target, 
                r.impact as impact, 
                toString(r.date) as date, 
                r.description as description
        """        
    
        G = nx.DiGraph()
        
        if not self.driver:
            print("❌ Chưa kết nối Neo4j.")
            return G

        with self.driver.session() as session:
            # --- [FIX LỖI 2]: Truyền target_date_query (có giờ) vào tham số ---
            result = session.run(query, start_date=start_date_str, target_date=target_date_query)
            
            for record in result:
                source = record["source"]
                target = record["target"]
                edge_date_str = record["date"] 
                impact = record["impact"]
                raw_desc = record["description"]
                
                description = ", ".join(raw_desc) if isinstance(raw_desc, list) else str(raw_desc)
                
                try:
                    clean_date_str = str(edge_date_str).split()[0] 
                    edge_date = datetime.strptime(clean_date_str, "%Y-%m-%d")
                    days_diff = (target_date - edge_date).days
                    days_diff = max(0, days_diff)
                except Exception as e:
                    days_diff = self.LOOKBACK_DAYS 
                
                decay_weight = np.exp(-days_diff / self.LAMBDA_DECAY)
                
                G.add_edge(source, target,
                           weight=decay_weight,
                           impact=impact,
                           description=description,
                           date=clean_date_str
                )
                
        print(f"Historical graph fetched with {G.number_of_nodes()} nodes and {G.number_of_edges()} edges.")
        return G
    
    def apply_attention_mechanism(self, G, portfolio_stocks):
        """
        Step 3: Attention Mechanism - Dùng Weighted PageRank để lọc tin quan trọng
        """
        if G.number_of_nodes() == 0:
            print("Warning: Graph is empty.")
            return nx.DiGraph()
        
        print("Applying attention mechanism using PageRank...")
        
        # 1. Chạy Weighted PageRank (Ưu tiên node có nhiều kết nối MỚI)
        try:
            # weight='weight' sử dụng decay_weight đã tính ở trên
            pagerank_scores = nx.pagerank(G, weight="weight", alpha=0.85)
        except Exception as e:
            print(f"PageRank failed, falling back to equal weights: {e}")
            pagerank_scores = {node: 1.0 for node in G.nodes()}
            
        # 2. Sắp xếp node theo điểm số quan trọng
        sorted_nodes = sorted(pagerank_scores.items(), key=lambda x: x[1], reverse=True)        
        
        top_entities = []
        count = 0
        
        # 3. Lọc ra các Entity quan trọng nhất (Top-Q)
        # Lưu ý: Chúng ta lọc entity KHÔNG phải là Stock trong portfolio trước
        # Vì Stock trong portfolio chắc chắn sẽ được thêm vào sau.
        for node, score in sorted_nodes:
            # Kiểm tra xem node có phải là stock trong danh mục không
            is_stock_in_portfolio = any(stock in node for stock in portfolio_stocks)
            
            if not is_stock_in_portfolio:
                top_entities.append(node)
                count += 1
            
            if count >= self.TOP_Q:
                break
                
        print(f"Top-{self.TOP_Q} relevant entities selected: {top_entities}")
        
        # 4. Xây dựng Subgraph tập trung (Focused Graph)
        important_nodes = set(top_entities)
        
        # BẮT BUỘC thêm các mã cổ phiếu trong portfolio vào (nếu chúng tồn tại trong graph gốc)
        for node in G.nodes():
            if any(stock in node for stock in portfolio_stocks):
                important_nodes.add(node)
        
        # Tạo subgraph chứa các node quan trọng và đường nối giữa chúng
        G_TRR = G.subgraph(important_nodes).copy()
        
        # Loại bỏ các node cô lập (không có cạnh nối) để tiết kiệm token cho LLM
        # G_TRR.remove_nodes_from(list(nx.isolates(G_TRR)))
        
        print(f"Focused subgraph has {G_TRR.number_of_nodes()} nodes and {G_TRR.number_of_edges()} edges.")
        return G_TRR
     
    def format_graph_for_llm(self, G_TRR):
        """ 
        Chuyển đổi đồ thị thành văn bản (List of Tuples) để làm đầu vào cho LLM
        Format: (Date, Source, Impact, Target) [Description]
        """
        if G_TRR.number_of_edges() == 0:
            return "No relevant graph context found."

        tuples = []
        # Sắp xếp cạnh theo ngày giảm dần (Mới nhất lên đầu)
        sorted_edges = sorted(G_TRR.edges(data=True), key=lambda x: x[2].get("date", ""), reverse=True)
        
        for u, v, data in sorted_edges:
            date = data.get("date", "N/A")
            impact = data.get("impact", "RELATED")
            desc = data.get("description", "")
            
            # Cắt ngắn description nếu quá dài để tiết kiệm token
            if len(desc) > 100:
                desc = desc[:100] + "..."
            
            # Format dòng text
            tuple_str = f"- [{date}] {u} --({impact})--> {v} : {desc}"
            tuples.append(tuple_str)
                
        return "\n".join(tuples)
    
# --- Quick Test ---
if __name__ == "__main__":
    # Test class
    trr = TRRMemoryAttention()
    
    # Giả sử ngày hiện tại (hoặc ngày bạn muốn test)
    # Lưu ý: Cần đảm bảo DB có dữ liệu xung quanh ngày này
    test_date = "2025-11-23" 
    
    G_full = trr.fetch_historical_graph()
    
    my_portfolio = ["FPT", "SSI", "VCB", "VHM", "HPG", "GAS", "MSN", "MWG", "GVR", "VIC"]
    G_attention = trr.apply_attention_mechanism(G_full, my_portfolio)
    
    context_text = trr.format_graph_for_llm(G_attention)
    
    print("\n--- FORMATTED CONTEXT FOR LLM ---")
    print(context_text)
    
    trr.close()