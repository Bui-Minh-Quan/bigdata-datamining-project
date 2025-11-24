import os 
from neo4j import GraphDatabase
from dotenv import load_dotenv

load_dotenv()

class GraphLoader:
    def __init__(self):
        uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
        user = os.getenv("NEO4J_USER", "neo4j")
        password = os.getenv("NEO4J_PASSWORD", "password123")
        
        try:
            self.driver = GraphDatabase.driver(uri, auth=(user, password))
            print("✓ Kết nối Neo4j thành công!")
        except Exception as e:
            print(f"❌ Lỗi kết nối Neo4j: {e}")
            self.driver = None
    
    def close(self):
        if self.driver:
            self.driver.close()
    
    def push_graph_to_neo4j(self, G):
        if not self.driver:
            print("Cannot connect to Neo4j. Skipping push.")
            return
    
        print("Pushing graph to Neo4j (Batch Mode)...")
        with self.driver.session() as session:
            # 1. Create Constraints (Giữ nguyên)
            session.run("CREATE CONSTRAINT IF NOT EXISTS FOR (a:Article) REQUIRE a.id IS UNIQUE")
            session.run("CREATE CONSTRAINT IF NOT EXISTS FOR (e:Entity) REQUIRE e.name IS UNIQUE")
            session.run("CREATE CONSTRAINT IF NOT EXISTS FOR (s:Stock) REQUIRE s.name IS UNIQUE")
            
            # --- CHUẨN BỊ DỮ LIỆU ĐỂ BATCHING ---
            articles = []
            others = [] # Stock & Entity
            edges = []

            # Phân loại Nodes
            for node, data in G.nodes(data=True):
                node_type = data.get("type", "Entity")
                if node_type == "Article":
                    clean_id = node.replace("Article_", "")
                    articles.append({
                        "id": clean_id,
                        "title": data.get("title", ""),
                        "date": str(data.get("date", ""))
                    })
                else:
                    # Stock hoặc Entity
                    others.append({
                        "name": node,
                        "label": "Stock" if node_type == "Stock" else "Entity",
                        "updatedAt": str(data.get("updatedAt", ""))
                    })

            # Chuẩn bị Edges
            for u, v, data in G.edges(data=True):
                u_clean = u.replace("Article_", "") if "Article_" in u else u
                v_clean = v.replace("Article_", "") if "Article_" in v else v
                
                edges.append({
                    "source": u_clean,
                    "target": v_clean,
                    "impact": data.get("impact", "RELATED"),
                    "description": data.get("description", ""),
                    "date": str(data.get("date", ""))
                })

            # --- THỰC THI BATCH QUERY (NHANH HƠN RẤT NHIỀU) ---

            # 2.1 Push Articles (1 Query duy nhất)
            if articles:
                session.run("""
                UNWIND $batch AS row
                MERGE (a:Article {id: row.id})
                SET a.title = row.title, a.date = row.date
                """, batch=articles)

            # 2.2 Push Stocks/Entities (1 Query duy nhất)
            # Vì Label (Stock/Entity) là động, ta dùng apoc hoặc tách list. 
            # Để đơn giản và không phụ thuộc APOC, ta tách list Python ở trên rồi chạy UNWIND.
            # Ở đây trick là dùng foreach hoặc call procedure, nhưng đơn giản nhất là chạy 2 batch:
            stocks = [x for x in others if x['label'] == 'Stock']
            entities = [x for x in others if x['label'] == 'Entity']

            if stocks:
                session.run("""
                UNWIND $batch AS row
                MERGE (s:Stock {name: row.name})
                SET s.updatedAt = row.updatedAt
                """, batch=stocks)
            
            if entities:
                session.run("""
                UNWIND $batch AS row
                MERGE (e:Entity {name: row.name})
                SET e.updatedAt = row.updatedAt
                """, batch=entities)

            # 3. Push Edges (FIX LỖI CARTESIAN PRODUCT & BATCHING)
            if edges:
                # Query này tách MATCH ra làm 2 dòng riêng biệt -> Hết Warning
                query = """
                UNWIND $batch AS row
                MATCH (source) WHERE source.id = row.source OR source.name = row.source
                MATCH (target) WHERE target.id = row.target OR target.name = row.target
                MERGE (source)-[r:AFFECTS]->(target)
                SET r.impact = row.impact, 
                    r.description = row.description,
                    r.date = row.date
                """
                session.run(query, batch=edges)
                
            print(f"✓ Đã đẩy {len(articles) + len(others)} nodes và {len(edges)} edges lên Neo4j (Batch processing).")

# Helper function
def save_graph(G):
    loader = GraphLoader()
    loader.push_graph_to_neo4j(G)
    loader.close()
    print("✓ Đóng kết nối Neo4j.")