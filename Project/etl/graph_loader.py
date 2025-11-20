import os 
from neo4j import GraphDatabase
from dotenv import load_dotenv
from database.db import get_database

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
    
        print("Pushing graph to Neo4j...")
        with self.driver.session() as session:
            # 1. Create Constraints
            session.run("CREATE CONSTRAINT IF NOT EXISTS FOR (a:Article) REQUIRE a.id IS UNIQUE")
            session.run("CREATE CONSTRAINT IF NOT EXISTS FOR (e:Entity) REQUIRE e.name IS UNIQUE")
            session.run("CREATE CONSTRAINT IF NOT EXISTS FOR (s:Stock) REQUIRE s.name IS UNIQUE")
            
            # 2. Push Nodes
            for node, data in G.nodes(data=True):
                node_type = data.get("type", "Entity")
                
                # Node article
                if node_type == "Article":
                    article_id = node.replace("Article_", "")
                    session.run("""
                                Merge (a:Article {id: $id})
                                Set a.title = $title, a.date = $date
                                """,id=article_id, title=data.get("title", ""), date=str(data.get("date", "")))
                
                # Node Entity or Stock
                else: 
                    label = "Stock" if node_type == "Stock" else "Entity"
                    
                    # Use MERGE to avoid duplicates
                    query = f"""
                            MERGE (e:{label} {{name: $name}})
                            SET e.updatedAt = $date
                    """
                    session.run(query, name=node, date=str(data.get("updatedAt", "")))
            
            # 3. Push Edges
            count = 0 
            for u, v, data in G.edges(data=True):
                impact = data.get("impact", "RELATED")
                description = data.get("description", "")
                date = data.get("date")
                
                query = """
                    MATCH (source), (target)
                    WHERE (source.id = $u OR source.name = $u)
                        And (target.id = $v OR target.name = $v)
                    MERGE (source)-[r:AFFECTS]->(target)
                    SET r.impact = $impact, 
                        r.description = $description,
                        r.date = $date
                """
                
                u_clean = u.replace("Article_", "") if "Article_" in u else u
                v_clean = v.replace("Article_", "") if "Article_" in v else v

                session.run(query, u=u_clean, v=v_clean, impact=impact, description=description, date=str(date))
                count += 1
                
            print(f"✓ Đã đẩy {G.number_of_nodes()} nodes và {count} edges lên Neo4j.")

# Helper function
def save_graph(G):
    loader = GraphLoader()
    loader.push_graph_to_neo4j(G)
    loader.close()
    print("✓ Đóng kết nối Neo4j.")
    
