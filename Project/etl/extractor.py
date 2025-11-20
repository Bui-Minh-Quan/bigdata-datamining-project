import networkx as nx 
from concurrent.futures import ThreadPoolExecutor, as_completed
import pandas as pd
from threading import Lock
import time
import os 
import sys 
import re

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(ROOT_DIR)

from database.db import get_database
db = get_database()

# Import modules in project
try:
    from etl.llm_client import APIKeyManager, get_llm_chain
    from etl.prompts import BATCH_RELATION_EXTRACTION_PROMPT, ENTITY_EXTRACTION_PROMPT, RELATION_EXTRACTION_PROMPT, BATCH_ARTICLE_EXTRACTION_PROMPT
    from etl.graph_loader import save_graph
except ImportError:
    # Fallback for direct script execution
    from llm_client import APIKeyManager, get_llm_chain
    from prompts import BATCH_RELATION_EXTRACTION_PROMPT, ENTITY_EXTRACTION_PROMPT, RELATION_EXTRACTION_PROMPT, BATCH_ARTICLE_EXTRACTION_PROMPT
    from graph_loader import save_graph



graph_lock = Lock()
canonical_lock = Lock()
results_lock = Lock()

PORTFOLIO_STOCKS = ["FPT", "SSI", "VCB", "VHM", "HPG", "GAS", "MSN", "MWG", "GVR", "VIC"]
PORTFOLIO_SECTOR = ["Công nghệ", "Chứng khoán", "Ngân hàng", "Bất động sản", "Vật liệu cơ bản", 
                     "Dịch vụ Hạ tầng", "Tiêu dùng cơ bản", "Bán lẻ", "Chế biến", "Bất động sản"]

PORTFOLIO_STR = ", ".join([f"{s}-{sec}" for s, sec in zip(PORTFOLIO_STOCKS, PORTFOLIO_SECTOR)])

BASE_DELAY = 30
MAX_RETRIES = 3
MAX_WORKERS = 1  



# ------------------------
#    Helper functions 
# ------------------------
def parse_entity_response(response):
    """
    Phân tích response từ entity extraction prompt
    
    Returns:
        dict: {"POSITIVE": [(entity, explanation), ...], "NEGATIVE": [(entity, explanation), ...]}
    """
    if response is None:
        print("Response is None")
        return {"POSITIVE": [], "NEGATIVE": []}
        
    sections = {"POSITIVE": [], "NEGATIVE": []}
    current_section = None
    str_resp = response.content
    
    for line in str(str_resp).splitlines():
        line = line.strip()
        if not line:
            continue
        if "[[POSITIVE]]" in line.upper():
            current_section = "POSITIVE"
            continue
        if "[[NEGATIVE]]" in line.upper():
            current_section = "NEGATIVE"
            continue
        if current_section and ':' in line:
            entity = line.split(":", 1)[0].strip()
            # Skip invalid entities
            if not entity or "không có thực thể nào" in entity.lower():
                continue
            # content = all line except entity
            content = line.split(entity, 1)[-1].strip(':').strip()
            sections[current_section].append((entity, content))

    return sections

def parse_batch_articles_response(response_content):
    if response_content is None:
        return {}
    
    content = str(response_content)
    results = {}
    parts = re.split(r"\[\[ARTICLE_ID:\s*(.+?)\s*\]\]", content)
    
    for i in range(1, len(parts), 2):
        article_id = parts[i].strip()
        body = parts[i+1].strip()
        results[article_id] = body 
        
    
    return results
    
    


def parse_batch_entity_response(response):
    """
    Phân tích response từ batch relation extraction prompt
    
    Returns:
        list: [(source_entity, impact, target_entity, content), ...]
    """
    if response is None:
        print("Response is None")
        return []
        
    results = []
    current_source = None
    current_impact = None
    current_section = None
    
    str_resp = str(response.content)
    lines = str_resp.splitlines()
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
            
        # Check for source entity marker
        if line.startswith("[[SOURCE:") or "[[SOURCE:" in line:
            source_text = line.replace("[[SOURCE:", "").replace("]]", "").strip()
            if source_text and "không có thực thể nào" not in source_text.lower():
                current_source = source_text
            else:
                current_source = None
            continue
            
        # Check for impact marker
        if line.startswith("[[IMPACT:") or "[[IMPACT:" in line:
            impact_str = line.replace("[[IMPACT:", "").replace("]]", "").strip()
            current_impact = impact_str.upper()
            continue
            
        # Check for positive/negative section markers
        if "[[POSITIVE]]" in line.upper():
            current_section = "POSITIVE"
            continue
            
        if "[[NEGATIVE]]" in line.upper():
            current_section = "NEGATIVE"
            continue
            
        # Process entity and explanation
        if current_source and current_section and ':' in line:
            try:
                entity, *content_parts = line.split(":", 1)
                entity = entity.strip().strip('[]')
                
                if not entity or "không có thực thể nào" in entity.lower():
                    continue
                    
                if entity and content_parts:
                    content = content_parts[0].strip()
                    actual_impact = current_impact if current_impact else current_section
                    results.append((current_source, actual_impact, entity, content))
            except Exception as e:
                print(f"Error parsing line: {line}. Error: {e}")
                continue
    
    if not results:
        print("Warning: No relationships were parsed from the response")
        
    return results

def merge_entity(entity, canonical_set):
    """
    Trả về phiên bản canonical của entity nếu đã tồn tại (case-insensitive),
    nếu không thì thêm và trả về entity mới.
    
    FIX: Đảm bảo tên entity được lưu và trả về nhất quán (giữ nguyên viết hoa/thường của lần đầu)
    """
    # Chuẩn hóa: bỏ dấu ngoặc vuông, khoảng trắng thừa
    cleaned_entity = str(entity).strip('[').strip(']').strip()
    normalized_lower = cleaned_entity.lower()
    
    # Tìm entity đã tồn tại (case-insensitive)
    for existing_entity in canonical_set:
        if existing_entity.lower() == normalized_lower:
            # Trả về entity đã tồn tại (giữ nguyên viết hoa/thường của lần đầu)
            return existing_entity
    
    # Chưa tồn tại → thêm entity mới (GIỮ NGUYÊN viết hoa/thường gốc)
    canonical_set.add(cleaned_entity)
    return cleaned_entity

def get_graph_context(G, max_entities=50):
    """
    Chuyển đổi các entities trong graph thành chuỗi để đưa vào prompt
    """
    entities = [node for node in G.nodes() if not node.startswith("Article_")]
    # Giới hạn số lượng để không làm prompt quá dài
    entities = entities[:max_entities]
    return ", ".join(entities) if entities else "Chưa có thực thể nào"



def invoke_chain_with_retry(prompt_template, prompt_inputs, api_manager, base_delay=BASE_DELAY,
                            temperature=0.15, model_name="gemini-2.0-flash"):
    """
    Gọi LLM với cơ chế retry:
    Thay đổi quan trọng: Nhận vào prompt_template chứ KHÔNG phải chain.
    Mỗi lần retry sẽ TẠO LẠI CHAIN MỚI với key mới.
    """
    total_attempts = 0
    max_total_attempts = len(api_manager.keys) * api_manager.MAX_RETRIES_PER_KEY

    while total_attempts < max_total_attempts:
        try:
            # --- ĐIỂM KHÁC BIỆT: Tạo chain MỚI ngay trong vòng lặp ---
            # Điều này đảm bảo chain luôn dùng Key hiện tại của api_manager
            chain = get_llm_chain(api_manager, prompt_template, temperature, model_name)
            # ---------------------------------------------------------
            
            response = chain.invoke(prompt_inputs)
            api_manager.reset_errors() # Nếu thành công thì reset lỗi
            return response

        except Exception as e:
            total_attempts += 1
            print(f"⚠️ Lỗi (Lần {total_attempts}): {str(e)[:100]}...")

            # Báo lỗi cho manager để nó chuyển index key
            key_changed = api_manager.on_error()

            if total_attempts >= max_total_attempts:
                print("❌ Đã thử tất cả keys nhưng vẫn lỗi.")
                return None

            if key_changed:
                print("🔁 Đã chuyển API key mới -> Sẽ tạo lại Chain ở vòng lặp sau.")
                delay = base_delay
            else:
                # Nếu chưa đổi key (retry lại key cũ)
                delay = base_delay * 1.5

            print(f"⏳ Đợi {delay}s...")
            time.sleep(delay)
            
    return None

            
# -----------------------------
#       Core functions
# -----------------------------
def process_batch_relations(batch, G, canonical_entities, api_manager, article_timestamp):
    # Process a single batch of entities for relation extraction
    input_text = ""
    for entity, impact, content in batch:
        input_text += f"Thực thể: {entity}\nẢnh hưởng nhận được: {impact} - {content}\n---\n"
    
    with graph_lock:
        existing_entities = get_graph_context(G)
        
    prompt_inputs = {
        "input_entities": input_text,
        "portfolio": PORTFOLIO_STR,
        "existing_entities": existing_entities
    }
    
    # --- SỬA: Truyền thẳng Prompt Template (không tạo chain = get_llm_chain ở đây nữa) ---
    response = invoke_chain_with_retry(BATCH_RELATION_EXTRACTION_PROMPT, prompt_inputs, api_manager)
    # -------------------------------------------------------------------------------------
    
    relations = parse_batch_entity_response(response)
    new_entities = []
    
    for source, impact, target, content in relations:
        with canonical_lock:
            canon_source = merge_entity(source, canonical_entities)
            canon_target = merge_entity(target, canonical_entities)
            
        with graph_lock:
            # add nodes 
            for node in [canon_source, canon_target]:
                if not G.has_node(node):
                    node_type = "Stock" if node in PORTFOLIO_STOCKS else "Entity"
                    G.add_node(node, type=node_type, updated_at = article_timestamp)
            # add edge
            if not G.has_edge(canon_source, canon_target):
                G.add_edge(canon_source, canon_target, impact=impact, description=content, date=article_timestamp)
        
        new_entities.append((canon_target, impact, content))
        
    return new_entities

def process_single_article(article, G, canonical_entities, api_manager):
    # Process a single article to extract entities and relations
    article_id = article['_id']
    title = article.get("title", "")
    description = article.get("description", "")
    date_str = article.get("date", "")
    stock_codes = ", ".join(article.get("stockCodes", []))
    
    print(f"Processing: {title[:30]}...")
    
    # Node article 
    article_node = f"Article_{article_id}"
    
    with graph_lock:
        if not G.has_node(article_node):
            G.add_node(article_node, type="Article", title=title, date=date_str)
    
    # Phase 1: Entity Extraction
    with graph_lock:
        existing = get_graph_context(G)
    
    prompt_inputs = {
        "date": date_str,
        "stockCodes": stock_codes,
        "title": title,
        "description": description,
        "portfolio": PORTFOLIO_STR,
        "existing_entities": existing
    }
    
    # --- SỬA: Đổi BATCH_RELATION... thành ENTITY_EXTRACTION_PROMPT ---
    response = invoke_chain_with_retry(ENTITY_EXTRACTION_PROMPT, prompt_inputs, api_manager)
    # -----------------------------------------------------------------

    entities_dict = parse_entity_response(response)
    
    frontier = [] # List off entities to run Phase 2
    
    # Process the results from Phase 1
    for impact_type, items in entities_dict.items():
        for entity_name, reason in items:
            with canonical_lock:
                canon_entity = merge_entity(entity_name, canonical_entities)
            
            with graph_lock:
                # create node Entity
                if not G.has_node(canon_entity):
                    node_type = "Stock" if canon_entity in PORTFOLIO_STOCKS else "Entity"
                    G.add_node(canon_entity, type=node_type, updated_at=date_str)
                
                # create edge Article -> Entity
                G.add_edge(article_node, canon_entity, impact=impact_type, description=reason, date=date_str)
                
                frontier.append((canon_entity, impact_type, reason))
    
    # Phase 2: Relation Extraction for entities in frontier
    BATCH_SIZE = 50
    if frontier: 
        for i in range(0, len(frontier), BATCH_SIZE):
            batch = frontier[i: i + BATCH_SIZE]
            # call process_batch_relations
            process_batch_relations(batch, G, canonical_entities, api_manager, date_str)
            
            
# Process a batch of articles            
def process_article_batch(articles_batch, G, canonical_entities, api_manager):
    batch_content = ""
    
    id_map = {}
    
    for article in articles_batch:
        # SỬA 1: Ép kiểu _id về string ngay lập tức để làm key thống nhất
        article_id = str(article['_id'])
        
        title = article.get("title", "Không có tiêu đề")
        description = article.get("summary", article.get("description", "Không có mô tả"))
        
        # SỬA 2: Chỉ đưa article_id vào prompt, không đưa cả object article
        batch_content += f"[ID: {article_id}] Tiêu đề: {title} | Nội dung tóm tắt: {description}\n\n"
        
        # Lưu vào map với key là string
        id_map[article_id] = article
        
    # get context from graph
    with graph_lock:
        existing = get_graph_context(G)
    
    prompt_inputs = {
        "batch_content": batch_content,
        "existing_entities": existing,
        "portfolio": PORTFOLIO_STR
    }
    
    # Call LLM
    try:
        # Đảm bảo bạn đã import BATCH_ARTICLE_EXTRACTION_PROMPT
        response = invoke_chain_with_retry(BATCH_ARTICLE_EXTRACTION_PROMPT, prompt_inputs, api_manager)
        if not response: return
    except Exception as e:
        print(f"Error invoking LLM for batch: {e}")
        return

    # Parse response
    parsed_results = parse_batch_articles_response(response.content)
    print(f"✓ Batch {len(articles_batch)} bài -> Trích xuất được cho {len(parsed_results)} bài.")
    
    # Process each article's results
    frontier = [] 
    
    for article_id_str, extraction_text in parsed_results.items():
        # SỬA 3: Strip khoảng trắng thừa của ID do LLM sinh ra
        clean_id = article_id_str.strip()
        
        # Lúc này id_map key là string, clean_id cũng là string => Tìm thấy nhau
        original_article = id_map.get(clean_id)
        
        if not original_article:
            # Debug: In ra để biết tại sao không khớp
            # print(f"Warning: Không tìm thấy ID '{clean_id}' trong map gốc.") 
            continue
        
        # Mock response object for parse_entity_response
        class MockResponse:
            content = extraction_text
            
        entities_dict = parse_entity_response(MockResponse())
        date_str = original_article.get("date", "")
        
        # create article node
        article_node = f"Article_{clean_id}"
        with graph_lock:
            if not G.has_node(article_node):
                G.add_node(article_node, type="Article", title=original_article.get("title", ""), date=date_str)
        
        # Save entities and edges
        for impact_type, items in entities_dict.items():
            for entity_name, reason in items:
                with canonical_lock:
                    canon_entity = merge_entity(entity_name, canonical_entities)
                
                with graph_lock:
                    if not G.has_node(canon_entity):
                        is_stock = any(stock in canon_entity for stock in PORTFOLIO_STOCKS)
                        node_type = "Stock" if is_stock else "Entity"
                        # node_type = "Stock" if canon_entity in PORTFOLIO_STOCKS else "Entity"
                        G.add_node(canon_entity, type=node_type, updated_at=date_str)
                    
                    # Add edge
                    if not G.has_edge(article_node, canon_entity):
                        G.add_edge(article_node, canon_entity, impact=impact_type, description=reason, date=date_str)
                        
                        # Add to frontier for Phase 2
                        frontier.append((canon_entity, impact_type, reason))
                        
    # Phase 2: Relation Extraction
    BATCH_SIZE = 50
    if frontier:
        unique_frontier = list(set(frontier))
        for i in range(0, len(unique_frontier), BATCH_SIZE):
            batch = unique_frontier[i: i + BATCH_SIZE]
            process_batch_relations(batch, G, canonical_entities, api_manager, articles_batch[0].get('date', ''))

# ---- MAIN FUNCTION ----
def build_daily_knowledge_graph(target_date):
    """ 
    Input: Target date to build knowledge graph (YYYY-MM-DD)
    Output: networkx graph object
    """
    print(f"Building knowledge graph for date: {target_date}")
    
    # 1. Get summarized articles in target date from mongoDB
    cursor = db['summarized_news'].find({"date": target_date})
    articles = list(cursor)
    articles = articles[:20]  # Limit to first 20 articles for performance during testing
    
    if not articles:
        print("No articles found for the target date.")
        return nx.DiGraph()
    
    print(f"Found {len(articles)} articles for date {target_date}")
    
    # 2. Initialize graph and canonical entity set
    G = nx.DiGraph()
    canonical_entities = set()
    api_manager = APIKeyManager()
    
    # 3. Process articles with ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = [
            executor.submit(process_single_article, article, G, canonical_entities, api_manager)
            for article in articles
        ]
        
        # wait for all to complete
        for future in as_completed(futures):
            try:
                future.result()
            except Exception as e:
                print(f"Error processing article: {e}")
    
    print(f"Knowledge graph construction completed. Total nodes: {G.number_of_nodes()}, Total edges: {G.number_of_edges()}")
    return G

def build_daily_knowledge_graph_batch(target_date):
    """ 
    Input: Target date to build knowledge graph (YYYY-MM-DD)
    Output: networkx graph object
    """
    print(f"Building knowledge graph for date: {target_date}")
    
    # 1. Get summarized articles in target date from mongoDB
    cursor = db['summarized_news'].find({"date": target_date})
    articles = list(cursor)
    # articles = articles[:40]  # Limit to first 20 articles for performance during testing
    
    if not articles:
        print("No articles found for the target date.")
        return nx.DiGraph()
    
    print(f"Found {len(articles)} articles for date {target_date}")
    
    # 2. Initialize graph and canonical entity set
    G = nx.DiGraph()
    canonical_entities = set()
    api_manager = APIKeyManager()
    
    # 3. Process articles in batches
    BATCH_SIZE = 10
    for i in range(0, len(articles), BATCH_SIZE):
        batch = articles[i: i + BATCH_SIZE]
        process_article_batch(batch, G, canonical_entities, api_manager)
        # wait for 4 seconds
        time.sleep(4)
        
        
    
    print(f"Knowledge graph construction completed. Total nodes: {G.number_of_nodes()}, Total edges: {G.number_of_edges()}")
    return G

if __name__ == "__main__":
    # Example run
    # G = build_daily_knowledge_graph("2025-11-19 00:00:00")
    # print("Sample nodes:", list(G.nodes(data=True))[:5])
    
    G = build_daily_knowledge_graph_batch("2025-11-19 00:00:00")
    # print("Sample nodes:", list(G.nodes(data=True))[:5])
    if G.number_of_nodes() > 0:
        try:
            save_graph(G)
        except Exception as e:
            print(f"Error saving graph to Neo4j: {e}") 
    else :
        print("Graph is empty, not saving to Neo4j.")