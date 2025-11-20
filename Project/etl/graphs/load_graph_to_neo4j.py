# Load graph created using networkx (in .pkl file) to Neo4j
import logging
import pickle
import networkx as nx
from neo4j import GraphDatabase

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Neo4j configuration
NEO4J_URI = "bolt://localhost:7687"
NEO4J_AUTH = ("neo4j", "password123")


def load_graph_to_neo4j(pkl_file_path):
    # Load the graph from a .pkl file
    with open(pkl_file_path, 'rb') as f:
        G = pickle.load(f)

    logger.info(f"Loaded graph with {G.number_of_nodes()} nodes and {G.number_of_edges()} edges from {pkl_file_path}")

    # Connect to Neo4j
    driver = GraphDatabase.driver(NEO4J_URI, auth=NEO4J_AUTH)
    with driver.session() as session:
        # Clear existing data
        session.run("MATCH (n) DETACH DELETE n")
        logger.info("Cleared existing data in Neo4j database.")

        # -----------------------------
        # Create nodes
        # -----------------------------
        for node, data in G.nodes(data=True):
            data = data.copy()

            # Set node id
            data["id"] = node

            # Use "type" as label (default = Entity)
            raw_label = data.pop("type", "entity")
            label = str(raw_label).capitalize()  # "article" → "Article"

            # Node properties
            properties = ', '.join([f"{key}: ${key}" for key in data.keys()])

            query = f"CREATE (n:{label} {{ {properties} }})"
            session.run(query, **data)

        logger.info(f"Created {G.number_of_nodes()} nodes in Neo4j.")

        # -----------------------------
        # Create relationships
        # -----------------------------
        for u, v, data in G.edges(data=True):
            data = data.copy()

            # Use impact as relationship type
            rel_type = data.pop("impact", None)
            if rel_type is None:
                rel_type = "RELATED"
            rel_type = str(rel_type).upper()  # POSITIVE, NEGATIVE

            # Remaining properties
            properties = ', '.join([f"{key}: ${key}" for key in data.keys()])

            if properties:
                query = f"""
                MATCH (a {{id: $u_id}}), (b {{id: $v_id}})
                CREATE (a)-[r:{rel_type} {{ {properties} }}]->(b)
                """
            else:
                query = f"""
                MATCH (a {{id: $u_id}}), (b {{id: $v_id}})
                CREATE (a)-[r:{rel_type}]->(b)
                """

            params = {"u_id": u, "v_id": v}
            params.update(data)

            session.run(query, **params)

        logger.info(f"Created {G.number_of_edges()} relationships in Neo4j.")

    driver.close()
    logger.info("Graph loading to Neo4j completed.")


if __name__ == "__main__":
    pkl_file_path = "etl/graphs/knowledge_graph (4).pkl"
    load_graph_to_neo4j(pkl_file_path)

