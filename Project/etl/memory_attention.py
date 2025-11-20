import os 
import networkx as nx
import numpy as np
from datetime import datetime, timedelta
from neo4j import GraphDatabase
from dotenv import load_dotenv

load_dotenv()

class TRRMemoryAttention:
    def __init__(self, uri=None, user=None, password=None):
        uri = uri or os.getenv("NEO4J_URI", "bolt://localhost:7687")
        user = user or os.getenv("NEO4J_USER", "neo4j")
        password = password or os.getenv("NEO4J_PASSWORD", "password123")
        
        try:
            self.driver = GraphDatabase.driver(uri, auth=(user, password))
            print("✓ Kết nối Neo4j thành công!")
        except Exception as e:
            print(f"❌ Lỗi kết nối Neo4j: {e}")
            self.driver = None
        
        # Configure attention parameters
        self.LAMBDA_DECAY = 1 # Decay factor for time-based attention
        self.TOP_Q = 6 # Number of top relevant memories to consider
        self.LOOKBACK_DAYS = 30 # Lookback window in days
        
    def close(self):
        if self.driver:
            self.driver.close()
    
    def fetch_historical_graph(self, target_date_str):
        """ 
        Step 2: Memory - Get historical knowledge graph up from Neo4j (Contextualized Graph G_temporal)
        """
        target_date = datetime.strptime(target_date_str, "%Y-%m-%d")
        start_date = target_date - timedelta(days=self.LOOKBACK_DAYS)
        start_date_str = start_date.strftime("%Y-%m-%d")
        
        print(f"Fetching historical graph from {start_date_str} to {target_date_str}...")
        
        query = """ 
            MATCH (s)-[r:AFFECTS]->(t)
            WHERE r.date >= $start_date AND r.date <= $target_date 
            RETURN 
                COALESCE(s.name, s.title, s.id) as source,
                COALESCE(t.name, t.title, t.id) as target, 
                r.impact as impact, 
                r.date as date, 
                r.description as description
        """        
    
        G = nx.DiGraph()
        with self.driver.session() as session:
            result = session.run(query, start_date=start_date_str, target_date=target_date_str)
            
            for record in result:
                source = record["source"]
                target = record["target"]
                edge_date_str = record["date"]
                impact = record["impact"]
                description = record["description"]
                
                # calculate days difference for time decay
                try:
                    edge_date = datetime.strptime(edge_date_str, "%Y-%m-%d")
                    days_diff = (target_date - edge_date).days
                except:
                    days_diff = 0
                
                # Calculate time decay factor
                decay_weight = np.exp(-days_diff / self.LAMBDA_DECAY)
                
                G.add_edge(source, target,
                           weight=decay_weight,
                           impact=impact,
                           description=description,
                           date=edge_date_str
                )
        print(f"Historical graph fetched with {G.number_of_nodes()} nodes and {G.number_of_edges()} edges.")
        return G
    
    def apply_attention_mechanism(self, G, portfolio_stocks):
        """
        Step 3: Attention Mechanism - Use PageRank to identify important nodes
        """
        if len(G.nodes()) == 0:
            return nx.DiGraph()
        
        print("Applying attention mechanism using PageRank...")
        
        # 1. Run Weighted PageRank
        try:
            pagerank_scores = nx.pagerank(G, weight="weight")
        except:
            # Fallback to unweighted PageRank
            pagerank_scores = {node: 1.0 for node in G.nodes()}
            
        # 2. Select top-Q relevant nodes connected to portfolio stocks
        sorted_nodes = sorted(pagerank_scores.items(), key=lambda x: x[1], reverse=True)        
        
        top_entities = []
        count = 0
        # if node is not in portfolio stocks, add to top entities
        for node, score in sorted_nodes:
            is_stock = any(stock in node for stock in portfolio_stocks)
            
            if not is_stock:
                top_entities.append(node)
                count += 1
            if count >= self.TOP_Q:
                break
        print(f"Top-{self.TOP_Q} relevant entities selected: {top_entities}")
        
        
        # 3. Build focused subgraph
        important_nodes = set(top_entities)
        # Add portfolio stocks to important nodes
        for node in G.nodes():
            if any(stock in node for stock in portfolio_stocks):
                important_nodes.add(node)
                
        G_TRR = G.subgraph(important_nodes).copy()
        print(f"Focused subgraph has {G_TRR.number_of_nodes()} nodes and {G_TRR.number_of_edges()} edges.")
        return G_TRR
     
    def format_graph_for_llm(self, G_TRR):
        """ 
        Turn graph into text (Tuples) for LLM input
        Format: (Date, Source, Impact, Target)
        """
        tuples = []
        sorted_edges = sorted(G_TRR.edges(data=True), key=lambda x: x[2].get("date", ""), reverse=True)
        
        for u, v, data in sorted_edges:
            date = data.get("date", "N/A")
            impact = data.get("impact", "RELATED")
            desc = data.get("description", "")
            
            tuple_str = f"{date}, {u}, {impact}, {v}"
            tuples.append(tuple_str)
                
        return "\n".join(tuples)
    
# quick test
if __name__ == "__main__":
    trr = TRRMemoryAttention()
    G_full = trr.fetch_historical_graph("2025-11-20")
    
    my_portfolio = ["FPT", "SSI", "VCB", "VHM", "HPG", "GAS", "MSN", "MWG", "GVR", "VIC"]
    G_attention = trr.apply_attention_mechanism(G_full, my_portfolio)
    
    context_text = trr.format_graph_for_llm(G_attention)
    print("Formatted graph for LLM input:")
    print(context_text)
    trr.close()
            
            