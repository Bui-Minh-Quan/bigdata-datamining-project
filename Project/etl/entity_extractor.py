import os
import sys

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(ROOT_DIR)

from datetime import datetime, date 
from dateutil import parser as date_parser 
from typing import List, Tuple, Dict, Optional 
import math 
import logging 
import re

import networkx as nx 
from pymongo import MongoClient 
from neo4j import GraphDatabase 
import random    

from database.db import get_database


# -----------------------------
# Configuration 
# -----------------------------
NEO4J_URI = "bolt://localhost:7687"
NEO4J_AUTH = ("neo4j", "password123")

DECAY_LAMBDA_PER_DAY = 1
TOP_Q = 10
MEMORY_LOOKUP_WINDOW_DAYS = 365 * 5 

# Logging 
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("entity_extractor")

# -----------------------------
# Helpers: date parsing & decay
# -----------------------------
def parse_date(d: Optional[str]) -> date:
    if d is None:
        return datetime.utcnow().date()

    if isinstance(d, (datetime, date)):
        return d.date() if isinstance(d, datetime) else d 
    
    try:
        return date_parser.parse(d).date()
    except Exception:
        logger.warning("Could not parse date %r, using today", d)
        return datetime.utcnow().date()
    
def retention_factor(event_date: date, ref_date: Optional[date] = None, decay_lambda: float = DECAY_LAMBDA_PER_DAY) -> float:
    """
    Exponential decay retention factor R = exp(-lambda * days_old).
    """
    ref = ref_date or datetime.utcnow().date()
    days_old = (ref - event_date).days 
    if days_old < 0:
         days_old = 0
    return math.exp(-decay_lambda * days_old)


# -----------------------------
# DB connections
# -----------------------------
mongo_db = get_database()
summary_collection = mongo_db['summarized_news']

neo4j_driver = GraphDatabase.driver(NEO4J_URI, auth=NEO4J_AUTH)


# -----------------------------
# Placeholder LLM Brainstorming
# -----------------------------
def brainstorm_with_llm(summary: str) -> List[Tuple[str, str, str]]:
    """ 
    Placeholder for LLM chain-of-impact generation 
    
    Input:
        summary (str) - summarized news text.
    
    Output:
        List of directed triples (subject, relation, object) representing a chain of multiple chains
        - subject and object are entity / event strings
        - relation is typically 'impacts' 
    
    """
    triples = []
    text = (summary or "").lower()
    if not text.strip():
        return triples
    
    triples.append(("Mỹ", "impacts", "Kinh tế toàn cầu"))
    triples.append(("Căng thẳng thương mại", "impacts", "Thị trường chứng khoán"))
    triples.append(("Chính sách tiền tệ", "impacts", "Lãi suất"))
    triples.append(("Lãi suất", "impacts", "Đầu tư doanh nghiệp"))
    triples.append(("Mỹ", "taxes", "Trung Quốc"))
    triples.append(("Trung Quốc", "impacts", "Thị trường hàng hóa"))
    triples.append(("Thị trường hàng hóa", "impacts", "Giá cả tiêu dùng"))
    triples.append(("Giá cả tiêu dùng", "impacts", "Lạm phát"))
    triples.append(("Trung Quốc", "taxes", "Mỹ"))
    triples.append(("Mỹ", "taxes", "Liên minh châu Âu"))
    triples.append(("Liên minh châu Âu", "impacts", "Thị trường tài chính"))
    
    
    return triples 

# -----------------------------
# Load historical chains (memory) from Neo4j into NetworkX
# -----------------------------
def load_historical_graph(max_days_old: Optional[int] = MEMORY_LOOKUP_WINDOW_DAYS) -> nx.DiGraph:
    """
    Load nodes and edges stored in Neo4j into a NetworkX MultiDiGraph.
    Expects edges in Neo4j have properties: timestamp (ISO date string) and maybe weight.
    
    If max_days_old is set, only load edges whose timestamp within last max_days_old days.
    """
    
    G_hist = nx.MultiDiGraph()
    logger.info("Loading historical graph from Neo4j...")
    
    with neo4j_driver.session() as session:
        # Load nodes 
        node_query = """
        MATCH (n)
        RETURN labels(n) AS labels,
            n.name AS name,
            coalesce(n.first_seen, null) AS first_seen,
            coalesce(n.last_seen, null) AS last_seen
        """
        for record in session.run(node_query):
            name = record["name"]
            labels = record['labels']
            node_type = labels[0] if labels else "Entity" 
            first_seen = parse_date(record["first_seen"]) if record["first_seen"] else None
            last_seen = parse_date(record["last_seen"]) if record["last_seen"] else None
            G_hist.add_node(name, type=node_type, first_seen=first_seen, last_seen=last_seen)
            
        # Load edges
        edge_query = """
        MATCH (a)-[r]->(b)
        RETURN a.name AS source, b.name AS target, type(r) AS rel,
            coalesce(r.timestamp, null) AS ts,
            coalesce(r.weight, 1.0) AS weight
        """
        for record in session.run(edge_query):
            source = record["source"]
            target = record['target']
            relation = record['rel'] or "impacts"
            ts_raw = record["ts"]
            weight = record["weight"] if record["weight"] is not None else 1.0 
            
            if ts_raw:
                ts = parse_date(ts_raw)
            else:
                ts = None 
            
            if max_days_old is not None and ts is not None: 
                days_old = (datetime.utcnow().date() - ts).days 
                if days_old > max_days_old:
                    continue 
            
            # ensure nodes exist
            if source not in G_hist:
                G_hist.add_node(source, type="Entity", first_seen=ts, last_seen=ts)
            if target not in G_hist:
                G_hist.add_node(target, type="Entity", first_seen=ts, last_seen=ts)
                
            
            G_hist.add_edge(source, target, relation=relation, timestamp=ts, weight=weight)
    
    logger.info("Loaded historical graph: %d nodes, %d edges", G_hist.number_of_nodes(), G_hist.number_of_edges())
    return G_hist


# -----------------------------
# Build today's base graph G from MongoDB summaries
# -----------------------------
def build_daily_graph_from_summaries(limit: Optional[int] = None) -> nx.MultiDiGraph:
    """ 
    For each doc in summarized_news, call brainstorm_with_llm(summary)
    to get triples, and add to a MultiDiGraph. Node/edge attributes include timestamp.
    
    limit: max number of documents to process
    """
    G_daily = nx.MultiDiGraph()
    logger.info("Building daily graph from MongoDB summaries (limit=%s)...", limit)
    cursor = summary_collection.find().sort("date", 1)
    
    if limit:
        cursor = cursor.limit(limit)
        
    count = 0
    for doc in cursor:
        count += 1
        post_id = doc.get("postID")
        summary = doc.get("summary") or doc.get("originalContent") or ""
        raw_date = doc.get("date")
        ts = parse_date(raw_date)
        
        triples = brainstorm_with_llm(summary)
        
        
        for subject, relation, object in triples:
            # Add nodes with temporal info
            for node, node_type in ((subject, "Event/Entity"), (object, "Entity")):
                if node not in G_daily:
                    G_daily.add_node(node, type=node_type, first_seen=ts, last_seen=ts)
                else: 
                    # update first/last_seen 
                    first_seen = G_daily.nodes[node].get("first_seen")
                    last_seen = G_daily.nodes[node].get("last_seen")
                    
                    if first_seen is None or ts < first_seen:
                        G_daily.nodes[node]["first_seen"] = ts 
                    if last_seen is None or ts > last_seen:
                        G_daily.nodes[node]["last_seen"] = ts
                    
            # add directed edge with timestamp and source document
            G_daily.add_edge(subject, object, relation=relation, timestamp=ts, source_doc=post_id, weight=1)
        
    logger.info("Built daily graph: processed %d docs -> %d nodes, %d edges", count, G_daily.number_of_nodes(), G_daily.number_of_edges())
    return G_daily

# -----------------------------
# Merge historical memory into today's G with decay
# -----------------------------
def merge_memory_into_graph(G_daily:nx.MultiDiGraph, G_hist: nx.MultiDiGraph, 
                            decay_lambda: float = DECAY_LAMBDA_PER_DAY, ref_date: Optional[date] = None) -> nx.MultiDiGraph:
    """
    Merge historical edges/nodes into daily graph. For each historical edge, compute retention factor R and
    add to the merged graph with its decayed weight.

    Returns a new graph G_temporal (copy of G_daily merged with history).
    """
    ref = ref_date or datetime.utcnow().date()
    G = G_daily.copy()
    
    # Ensure nodes from history exist
    for node, data in G_hist.nodes(data=True):
        if node not in G: 
            G.add_node(node, **data)
            
    # For edges: add with decayed weight 
    for u, v, data in G_hist.edges(data=True):
        ts: Optional[date] = data.get("timestamp")
        if ts is None: 
            # if no timestamp, treat as old or as 0 days old, we choose 0 here
            ts = ref 
        
        # if memory lookup window is set, filter outside
        R = retention_factor(ts, ref_date=ref, decay_lambda=decay_lambda)
        
        # original stored weight if present
        orig_w = data.get("weight", 1.0)
        decayed_w = orig_w * R 
        
        # Add edge: if edge already exists in G, we still add new Multi edge
        G.add_edge(u, v, relation=data.get("relation", "impact"), timestamp=ts, weight=decayed_w, source="memory")
        
        # Update nodes' first/last seen
        for node in (u, v):
            nfs = G.nodes[node].get("first_seen")
            nls = G.nodes[node].get("last_seen")
            if ts:
                if nfs is None or ts < nfs:
                    G.nodes[node]['first_seen'] = ts 
                if nls is None or ts > nls:
                    G.nodes[node]['last_seen'] = ts 
        
    logger.info("Merged history: Result graph has %d nodes, %d edges", G.number_of_nodes(), G.number_of_edges())
    return G


def compute_weighted_pagerank_and_extract_trr(G_temporal: nx.MultiDiGraph, top_q:int = TOP_Q) -> Tuple[nx.DiGraph, List[str]]:
    """
    Compute PageRank on an aggregated DiGraph where multi-edges are collapsed by summing weights.
    Then select top_q nodes, and extract the subgraph (connected components containing top nodes).

    Returns:
        G_trr (nx.DiGraph) - subgraph focused on top entities (no multi-edges).
        top_nodes (List[str]) - list of top node names by pagerank.
    """
    
    # build aggregated DiGraph with Weight = sum of edge weights (decayed)
    agg = nx.DiGraph()
    for u, v, data in G_temporal.edges(data=True):
        w = data.get("weight", 1.0)
        if agg.has_edge(u, v):
            agg[u][v]['weight'] += w
        else:
            agg.add_edge(u, v, weight=w)
        
    # Ensure isolated nodes included
    for node, data in G_temporal.nodes(data=True):
        if node not in agg:
            agg.add_node(node)
    
    # Compute pagerank using 'weight' attribute
    try:
        page_rank = nx.pagerank(agg, weight='weight')
    except Exception as e:
        logger.warning("PageRank failed (%s), falling back to unweighted", e)
        page_rank = nx.pagerank(agg)
    
    # get top_q nodes 
    sorted_page_rank = sorted(page_rank.items(), key=lambda kv: kv[1], reverse=True)
    top_nodes = [node for node, _ in sorted_page_rank[:top_q]]
    logger.info("Top-%d nodes by weighted PageRank: %s", top_q, top_nodes)
    
    # Extract subgraph: include any node in the same connected component (undirected) as top nodes
    und = agg.to_undirected()
    nodes_to_keep = set()
    for top_node in top_nodes:
        if top_node in und:
            comp = next((c for c in nx.connected_components(und) if top_node in c), None)
            if comp:
                nodes_to_keep.update(comp)
                
        else:
            nodes_to_keep.add(top_node)
    
    # Build subgraph from original temporal multi-digraph but collapsed similarity to DiGraph
    G_trr = nx.DiGraph()
    for u, v, data in G_temporal.edges(data=True):
        if u in nodes_to_keep and v in nodes_to_keep:
            w = data.get("weight", 1.0)
            relation = data.get("relation", "impacts")
            if G_trr.has_edge(u, v):
                G_trr[u][v]["weight"] += w 
                # collect relation types (as list)
                if relation not in G_trr[u][v].get("relations", []):
                    G_trr[u][v]['relations'].append(relation)
            else:
                G_trr.add_edge(u, v, weight=w, relations=[relation])
            
    # copy node attributes 
    for node in nodes_to_keep:
        if node in G_temporal.nodes:
            G_trr.add_node(node, **G_temporal.nodes[node])
    
    logger.info("Extracted G_TRR: %d nodes, %d edges", G_trr.number_of_nodes(), G_trr.number_of_edges())
    return G_trr, top_nodes
                    
     
# -----------------------------
# Export relational tuples for Phase B
# -----------------------------
def graph_to_relational_tuples(G: nx.DiGraph) -> List[Tuple[str, str, str, str]]:
    """ 
    Convert G (G_TRR) into list of tuples:
    (timestamp_list, subject, relation, object_list)

    Return:
        list of (timestamp, subject, relation, object)
    """
    
    tuples = []
    for u, v, data in G.edges(data=True):
        relations = data.get("relations", ["impacts"])
        
        subj_ts = G.nodes[u].get("last_seen")
        obj_ts = G.nodes[v].get("last_seen")
        ts = subj_ts or obj_ts or None
        ts_str = ts.isoformat() if ts else None
        
        tuples.append((ts_str, u, ",".join(relations), v))
        
    return tuples 


# -----------------------------
# Save G_TRR to Neo4j 
# -----------------------------

def clean_label(raw: str) -> str:
    """Clean a string so it can be used as a Neo4j label."""
    if not raw:
        return "Entity"
    # Replace invalid chars with underscore
    cleaned = re.sub(r"[^A-Za-z0-9_]", "_", raw)
    # Neo4j labels cannot start with a number
    if cleaned[0].isdigit():
        cleaned = "_" + cleaned
    return cleaned

def save_trr_to_neo4j(G_trr: nx.DiGraph):
    logger.info("Saving G_TRR to Neo4j ...")
    with neo4j_driver.session() as session:
        tx = session.begin_transaction()

        # Save nodes
        for node, data in G_trr.nodes(data=True):
            raw_label = data.get("type", "Entity")
            label = clean_label(raw_label)

            first = data.get("first_seen")
            last = data.get("last_seen")

            tx.run(
                f"MERGE (n:{label} {{name: $name}}) "
                "SET n.first_seen = coalesce(n.first_seen, $first), "
                "    n.last_seen = $last",
                name=node,
                first=(first.isoformat() if first else None),
                last=(last.isoformat() if last else None)
            )

        # Save edges
        for u, v, data in G_trr.edges(data=True):
            relations = data.get("relations", ["IMPACTS"])
            rel_type = clean_label(relations[0].upper())
            weight = float(data.get("weight", 1.0))

            ts = G_trr.nodes[u].get("last_seen") or G_trr.nodes[v].get("last_seen")
            ts_iso = ts.isoformat() if ts else None

            tx.run(
                f"""
                MATCH (a {{name: $source}})
                MATCH (b {{name: $target}})
                MERGE (a)-[r:{rel_type}]->(b)
                SET r.weight = coalesce(r.weight, 0) + $weight,
                    r.timestamp = $ts
                """,
                source=u, target=v, weight=weight, ts=ts_iso
            )

        tx.commit()
        logger.info("Saved G_TRR to Neo4j")

# -----------------------------
# Main pipeline function (Phase A)
# -----------------------------
def build_phase_A_pipeline(limit_docs: Optional[int] = None,
                           decay_lambda: float = DECAY_LAMBDA_PER_DAY,
                           top_q: int = TOP_Q,
                           save_to_neo4j: bool = True) -> Tuple[nx.DiGraph, List[Tuple[str, str, str, str]]]:
    
    # Run steps (1) - (3) and return G_TRR and relational tuples for Phase B 
    # 1) Build daily graph G
    G_daily = build_daily_graph_from_summaries(limit=limit_docs)
    
    # 2) Load history Memory from Neo4j
    G_hist = load_historical_graph(max_days_old=MEMORY_LOOKUP_WINDOW_DAYS)
    
    # 3) MERGEt -> G_temporal with decay
    G_temporal = merge_memory_into_graph(G_daily, G_hist, decay_lambda=decay_lambda)
    
    # 4) Attention: Compute weighted PageRank and extract small G_TRR
    G_trr, top_nodes = compute_weighted_pagerank_and_extract_trr(G_temporal, top_q=top_q)
    
    # 5) Prepare relational tuples for Phase B
    tuples = graph_to_relational_tuples(G_trr)
    
    # 6) Save to Neo4j
    if save_to_neo4j:
        save_trr_to_neo4j(G_trr)
    
    return G_trr, tuples 


# -----------------------------
# if run as script
# -----------------------------
if __name__ == "__main__":
    logger.info("Running Phase A pipeline (build graph)...")
    G_trr, tuples = build_phase_A_pipeline(limit_docs=500)
    logger.info("G_TRR nodes: %d, edges: %d", G_trr.number_of_nodes(), G_trr.number_of_edges())
    logger.info("Sample relational tuples (for Phase B):")
    for t in tuples[:10]:
        logger.info(t)