import os
import sys
from unittest.mock import MagicMock, patch

# Ensure the backend directory is in python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.utils.entity_extraction import run_full_entity_extraction


def test_full_entity_extraction_mocked():
    """Verify entity extraction structure and merging behavior using mocked LLM response."""
    test_text = (
        "Agreement signed on 15/08/2025 between Shri Ram Kumar (Landlord) and Shyam Lal (Tenant). "
        "The rent is ₹12,000 per month, payable by the 5th of each month. The Tenant must keep the premises clean."
    )
    
    mock_response = MagicMock()
    # Mock return content matching standard LLM output format
    mock_response.content = """
    {
      "dates": ["15/08/2025", "5th of each month"],
      "amounts": ["₹12,000"],
      "parties": ["Ram Kumar", "Shyam Lal"],
      "obligations": ["Tenant must keep the premises clean"]
    }
    """
    
    with patch("app.utils.entity_extraction.get_llm") as mock_get_llm:
        mock_llm_instance = MagicMock()
        mock_llm_instance.invoke.return_value = mock_response
        mock_get_llm.return_value = mock_llm_instance
        
        result = run_full_entity_extraction(test_text)
        
        # Verify JSON shape
        assert isinstance(result, dict)
        assert set(result.keys()) == {"dates", "amounts", "parties", "obligations"}
        
        assert isinstance(result["dates"], list)
        assert isinstance(result["amounts"], list)
        assert isinstance(result["parties"], list)
        assert isinstance(result["obligations"], list)
        
        # Verify correctness of extracted and merged values
        assert "15/08/2025" in result["dates"]
        assert "₹12,000" in result["amounts"]
        assert "Ram Kumar" in result["parties"]
        assert "Shyam Lal" in result["parties"]
        assert "Tenant must keep the premises clean" in result["obligations"]


def test_full_entity_extraction_real():
    """Verify entity extraction on a real/mocked document if the Groq API key is present."""
    if not os.getenv("GROQ_API_KEY"):
        print("GROQ_API_KEY environment variable not set. Skipping real LLM integration test.")
        return
        
    print("GROQ_API_KEY is configured. Running real LLM integration test...")
    test_text = (
        "This Lease Agreement is executed on this 22nd day of June 2026 by and between "
        "Mr. Rahul Patidar, hereinafter referred to as the Lessor, and M/s DocuMind Technologies, "
        "hereinafter referred to as the Lessee. The Lessee shall pay a monthly rent of Rs. 25,000 "
        "on or before the 10th of every calendar month. The Lessee agrees to pay a security deposit of Rs 50,000."
    )
    
    result = run_full_entity_extraction(test_text)
    
    # Assert JSON shape
    assert isinstance(result, dict)
    assert set(result.keys()) == {"dates", "amounts", "parties", "obligations"}
    assert isinstance(result["dates"], list)
    assert isinstance(result["amounts"], list)
    assert isinstance(result["parties"], list)
    assert isinstance(result["obligations"], list)
    
    # Regex pass checks
    assert any("25,000" in c for c in result["amounts"])
    assert any("50,000" in c for c in result["amounts"])
    
    # LLM pass checks
    assert len(result["parties"]) > 0
    assert len(result["obligations"]) > 0
    
    print("Real LLM Integration Test Passed!")
    print(f"Extracted Entities:\n{result}")


if __name__ == "__main__":
    print("Running Entity Extraction Test Suite...")
    test_full_entity_extraction_mocked()
    print("- test_full_entity_extraction_mocked: PASSED")
    test_full_entity_extraction_real()
    print("- test_full_entity_extraction_real: PASSED")
    print("ALL TESTS PASSED SUCCESSFULLY!")
