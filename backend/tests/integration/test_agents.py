import sys
import os
import asyncio
import copy
from langgraph.graph import StateGraph, START, END

# Add the backend directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


from app.agents.ingestion_agent import ingestion_agent
from app.agents.language_detect_agent import detect_language_agent
from app.agents.extraction_agent import extraction_agent
from app.agents.risk_flagging_agent import risk_flagging_agent
from app.agents.state import DocuMindState

# 1. Define Conditional Routing Functions
def route_after_ingestion(state: DocuMindState) -> str:
    """Route to language detection if ingestion succeeded, otherwise end the flow."""
    if state.get("current_step") == "failed" or state.get("errors"):
        print("--> Ingestion failed, routing to END")
        return END
    print("--> Ingestion succeeded, routing to detect_language")
    return "detect_language"

# 2. Build the LangGraph Workflow
def build_graph() -> StateGraph:
    workflow = StateGraph(DocuMindState)
    
    # Add Nodes
    workflow.add_node("ingest", ingestion_agent)
    workflow.add_node("detect_language", detect_language_agent)
    workflow.add_node("extract", extraction_agent)
    workflow.add_node("risk_flag", risk_flagging_agent)
    
    # Add Edges
    workflow.add_edge(START, "ingest")
    
    # Add Conditional Edge from ingest
    workflow.add_conditional_edges(
        "ingest",
        route_after_ingestion,
        {
            "detect_language": "detect_language",
            END: END
        }
    )
    
    # Parallel execution: Add Edge from detect_language to extract and risk_flag
    workflow.add_edge("detect_language", "extract")
    workflow.add_edge("detect_language", "risk_flag")
    
    # Add Edges to END
    workflow.add_edge("extract", END)
    workflow.add_edge("risk_flag", END)
    
    return workflow.compile()

import json

def save_state_cache(state: dict, filepath: str):
    state_copy = dict(state)
    if "raw_bytes" in state_copy:
        state_copy["raw_bytes"] = ""
    if "documents" in state_copy:
        state_copy["documents"] = [
            {"page_content": doc.page_content, "metadata": doc.metadata}
            for doc in state_copy["documents"]
        ]
    if "retrieved_chunks" in state_copy:
        state_copy["retrieved_chunks"] = [
            {"page_content": doc.page_content, "metadata": doc.metadata}
            for doc in state_copy["retrieved_chunks"]
        ]
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(state_copy, f, ensure_ascii=False, indent=2)

def load_state_cache(filepath: str) -> dict:
    with open(filepath, "r", encoding="utf-8") as f:
        state = json.load(f)
    from langchain_core.documents import Document
    if "documents" in state:
        state["documents"] = [
            Document(page_content=doc["page_content"], metadata=doc["metadata"])
            for doc in state["documents"]
        ]
    if "retrieved_chunks" in state:
        state["retrieved_chunks"] = [
            Document(page_content=doc["page_content"], metadata=doc["metadata"])
            for doc in state["retrieved_chunks"]
        ]
    state["raw_bytes"] = b""
    return state

def run_manual_test():
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    file_path = os.path.join(base_dir, "test_files", "credit_card.pdf")
    
    # Determine the pipeline type dynamically from the file extension
    ext = os.path.splitext(file_path)[1].lower()
    if ext == ".pdf":
        pipeline = "pdf"
    elif ext in (".docx", ".doc"):
        pipeline = "word"
    elif ext in (".png", ".jpg", ".jpeg"):
        pipeline = "image"
    else:
        pipeline = "text"

    # Define the initial state matching DocuMindState schema
    initial_state: DocuMindState = {
        "document_id": "test-doc-1",
        "file_path": file_path,
        "raw_bytes": b"",
        "raw_text": "",
        "documents": [],
        "is_scanned": False,
        "char_count": 0,
        "detected_language": "",
        "detected_boilerplate": [],
        "language_confidence": 0.0,
        "prompt_locale": "english",
        "ner_entities": {},
        "llm_entities": {},
        "merged_entities": {},
        "risk_flags_raw": [],
        "risk_flags_deduped": [],
        "executive_summary": "",
        "risk_analysis_partial": False,
        "executive_summary_available": False,
        "retrieved_chunks": [],
        "rag_answer": "",
        "confidence_score": 0.0,
        "suggested_questions": [],
        "draft_reply": "",
        "current_step": "init",
        "errors": [],
        "retry_count": 0,
        "pipeline_type": pipeline,
    }

    cache_file = os.path.join(base_dir, "test_state_cache.json")
    state = initial_state
    if os.path.exists(cache_file):
        try:
            state = load_state_cache(cache_file)
            print(f"--> Loaded cached state from {cache_file}. Resuming execution.")
        except Exception as ex:
            print(f"--> Failed to load cached state: {ex}. Starting fresh.")

    print(f"--- Running LangGraph with File: {file_path} ---")
    
    async def main_async():
        nonlocal state
        
        # Step 1: Ingestion
        if not state.get("raw_text"):
            print("\n--- Running Ingestion Agent ---")
            state = ingestion_agent(state)
            save_state_cache(state, cache_file)
            
        if state.get("current_step") == "failed" or state.get("errors"):
            print("--> Ingestion failed, stopping.")
            return

        # Step 2: Language Detection
        if not state.get("detected_language"):
            print("\n--- Running Language Detection Agent ---")
            state = detect_language_agent(state)
            save_state_cache(state, cache_file)
            
        # Step 3: Parallel execution (Extraction & Risk Flagging)
        run_extract = not state.get("merged_entities") or not state.get("merged_entities", {}).get("parties")
        run_risk = not state.get("risk_flags_deduped")
        
        tasks = []
        if run_extract:
            print("\n--- Queueing Extraction Agent ---")
            tasks.append(extraction_agent(copy.deepcopy(state)))
        if run_risk:
            print("\n--- Queueing Risk Flagging Agent ---")
            tasks.append(risk_flagging_agent(copy.deepcopy(state)))
            
        if tasks:
            print(f"\n--- Running Parallel Agents ({len(tasks)} tasks queued) ---")
            try:
                results = await asyncio.gather(*tasks)
                # Merge results back into state safely
                for res in results:
                    # Append-mode keys
                    for k in ("risk_flags_raw", "errors"):
                        state[k] = state.get(k, []) + res.get(k, [])
                    # Last-write keys (non-critical, take either)
                    for k in ("current_step",):
                        if res.get(k):
                            state[k] = res[k]
                    # Remaining keys: only overwrite if result has a non-empty value
                    for k, v in res.items():
                        if k not in ("risk_flags_raw", "errors", "current_step"):
                            if v or k not in state:
                                state[k] = v
                save_state_cache(state, cache_file)
            except Exception as e:
                print(f"Parallel execution failed: {e}")
                state.setdefault("errors", []).append(str(e))
                save_state_cache(state, cache_file)  # save partial state so resume works
                raise
        else:
            print("\n--- All agents already run. Resumed from cache. ---")

        print("\n--- Final Graph State Result ---")
        print(f"Current Step: {state['current_step']}")
        print(f"Char Count: {state['char_count']}")
        print(f"Detected Language: {state['detected_language']}")
        print(f"Language Confidence: {state['language_confidence']}")
        print(f"Prompt Locale: {state['prompt_locale']}")
        print(f"NER Entities: {state['ner_entities']}")
        print(f"Merged Entities: {state['merged_entities']}")
        print(f"Risk Flags Raw: {state.get('risk_flags_raw')}")
        print(f"Risk Flags Deduped: {state.get('risk_flags_deduped')}")
        print(f"Executive Summary: {state.get('executive_summary')}")
        print(f"Risk Analysis Partial: {state.get('risk_analysis_partial')}")
        print(f"Executive Summary Available: {state.get('executive_summary_available')}")
        print(f"Errors: {state['errors']}")

    asyncio.run(main_async())

if __name__ == "__main__":
    run_manual_test()
