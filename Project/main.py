import logging 
from datetime import date, datetime, timedelta

# Crawling
from crawling.news_daily_crawl import main_news_crawl
from crawling.posts_daily_crawl import main_posts_crawling

# ETL
from etl.summarizer import run_summarization
from etl.reasoning import reasoning
from etl.entity_extractor import build_phase_A_pipeline


# database and knowledge graph
from database.db import get_database
import networkx as nx
from neo4j import GraphDatabase

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Neo4j configuration
NEO4J_URI = "bolt://localhost:7687"
NEO4J_AUTH = ("neo4j", "password123")


# ============================================================
#                     MAIN PIPELINE
# ============================================================

def run_pipeline(symbols, run_date: date):
    if run_date is None:
        run_date = datetime.now() # if no date provided, use now
    
    logger.info("========== PIPELINE START ==========")
    logger.info(f"Run date = {run_date}")
    
    # 1. Crawling
    logger.info("---- Step 1: Crawling ----")
    main_news_crawl()
    main_posts_crawling()
    
    # 2. ETL - Summarization
    logger.info("---- Step 2: ETL - Summarization ----")
    run_summarization()
    
    # 3. ETL - Entity Extraction and Knowledge Graph Building
    logger.info("---- Step 3: ETL - Entity Extraction and Knowledge Graph Building ----")
    _, tuples = build_phase_A_pipeline(save_to_neo4j=False)
    
    # 4. Reasoning
    predicted_movements = {}
    logger.info("---- Step 4: Reasoning ----")
    if not symbols:
        logger.warning("No stock symbols provided for reasoning step.")
    else:
        for symbol in symbols:
            movement = reasoning(symbol, run_date, tuples)
            predicted_movements[symbol] = movement
            logger.info(f"Predicted stock movement for {symbol} on {run_date}: {movement}")
    logger.info("========== PIPELINE END ==========")
    
    return predicted_movements

if __name__ == "__main__":
    # Example stock symbols to run reasoning on
    stock_symbols = ['FPT', 'SSI', 'VCB', 'VHM', 'HPG', 'GAS', 'MSN', 'MWG', 'GVR', 'VIC']
    run_pipeline(stock_symbols, None)
