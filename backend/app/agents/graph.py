from langgraph.graph import StateGraph, START, END
from app.agents.ingestion_agent import ingestion_agent
from app.agents.language_detect_agent import detect_language_agent
from app.agents.extraction_agent import extraction_agent
from app.agents.risk_flagging_agent import risk_flagging_agent
from app.agents.state import DocuMindState

def route_after_ingestion(state: DocuMindState) -> str:
    """Route to language detection if ingestion succeeded, otherwise end the flow."""
    if state.get("current_step") == "failed" or state.get("errors"):
        return END
    return "detect_language"

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

# Compiled graph instance
graph = build_graph()
