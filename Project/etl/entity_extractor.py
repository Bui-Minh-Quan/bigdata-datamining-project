import os
import sys

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(ROOT_DIR)

import networkx as nx
from pymongo import MongoClient
from neo4j import GraphDatabase
from database.db import get_database
from datetime import datetime


# Connect to MongoDB
db = get_database()
summary_collection = db['summarized_news']

# Connect to Neo4j
neo4j_driver = GraphDatabase.driver(
    "bolt://localhost:7687", auth=("neo4j", "password123")
)


# Sample data
data = [
    ("2007-08-01", "Tighter credit could slow U.S. GDP growth", "impacts", "U.S. consumers"),
    ("2007-08-02", "American Home Mortgage closing most operations", "impacts", "Mortgage industry"),
    ("2007-08-03", "IMF chief warns of globalization risks", "impacts", "U.S. subprime borrowers"),
    ("2007-08-01", "U.S. consumers", "impacts", "U.S. housing market"),
    ("2007-08-02", "Mortgage industry", "impacts", "U.S. housing market"),
    ("2007-08-03", "U.S. subprime borrowers", "impacts", "U.S. housing market"),
    ("2007-07-30", "U.S. housing market", "impacts", "AAPL stock"),
    ("2007-07-30", "U.S. housing market", "impacts", "RY stock"),
]


# Place Holder for entity extraction function
def extract_entities(text):
    # This is a placeholder function. Replace with actual NER model.
    # For demonstration, let's assume it extracts words starting with capital letters as entities.
    today = datetime.today().date()
    
    nodes = [("Event", "Demo Event"), ("Entity", "Demo Entity")]
    edges = [("Demo Event", "Demo Entity", "impacts")]
    return nodes, edges, today
    
    
# Load historical graph    
def load_historical_graph():
    G = nx.MultiDiGraph()
    with neo4j_driver.session() as session:
        # Load nodes 
        nodes = session.run("MATCH (n) RETURN labels(n) AS labels, n.name AS name")
        for record in nodes:
            label = record["labels"][0] if record["labels"] else "Unknown"
            name = record["name"]
            G.add_node(name, type=label, first_seen=None, last_seen=None)
            
        # Load edges
        edges = session.run("MATCH (a)-[r]->(b) RETURN a.name AS source, b.name AS target, type(r) AS rel")
        for record in edges:
            G.add_edge(record["source"], record["target"], relation=record["rel"], timestamp=None)

    return G

# Build temporal graph from MongoDB
def build_temporal_graph(historical_graph=None):
    G = nx.MultiDiGraph() if historical_graph is None else historical_graph.copy()
    
    for doc in summary_collection.find():
        summary = doc.get("summary", "")
        post_id = doc.get("postID")
        nodes, edges, timestamp = extract_entities(summary)
        
        # add nodes 
        for node_type, name in nodes:
            if name not in G:
                G.add_node(name, type=node_type, first_seen=timestamp, last_seen=timestamp)
            else:
                # Update temporal info
                G.nodes[name]["first_seen"] = min(G.nodes[name]["first_seen"], timestamp) if G.nodes[name]["first_seen"] else timestamp
                G.nodes[name]["last_seen"] = max(G.nodes[name]["last_seen"], timestamp) if G.nodes[name]["last_seen"] else timestamp

        # add edges
        for source, target, rel in edges:
            G.add_edge(source, target, relation=rel, timestamp=timestamp, source_doc=post_id)
    
    return G
            

# Push graph to Neo4j
def save_graph_to_neo4j(G):
    with neo4j_driver.session() as session:
        # add nodes
        for node, data in G.nodes(data=True):
            session.run(
                "MERGE (n:{label} {{name: $name}})".format(label=data['type']),
                name=node 
            )
            
        # add edge
        for u, v, data in G.edges(data=True):
            session.run(
                """ 
                MATCH (a {{name: $source}})
                MATCH (b {{name: $target}})
                MERGE (a)-[r:{rel}]->(b)
                """.format(rel=data['relation']),
                source=u, target=v 
            )

# Main
if __name__ == "__main__":
    print("Loading historical graph from Neo4j...")
    historical_graph = load_historical_graph()
    print(f"Historical graph: {len(historical_graph.nodes)} nodes, {len(historical_graph.edges)} edges")
    
    print("Building temporal graph from MongoDB summaries...")
    G = build_temporal_graph(historical_graph)
    print(f"Current graph: {len(G.nodes)} nodes, {len(G.edges)} edges")
    
    print("Performing example NetworkX calculations: degree centrality")
    centrality = nx.degree_centrality(G)
    for node, val in list(centrality.items())[:5]:
        print(f"{node}: {val:.2f}")

    print("Saving graph to Neo4j ...")
    save_graph_to_neo4j(G)
    print("Done!")