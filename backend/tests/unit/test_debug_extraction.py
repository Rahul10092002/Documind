import os
import sys
from unittest.mock import MagicMock, patch

sys.path.append(r"e:\DocMind\backend")

from app.extractors.entity_extraction import extract_entities_via_llm, ExtractedEntities

def debug_extraction():
    test_text = (
        "Agreement signed on 15/08/2025 between Shri Ram Kumar (Landlord) and Shyam Lal (Tenant). "
        "The rent is ₹12,000 per month, payable by the 5th of each month. The Tenant must keep the premises clean."
    )
    
    with patch("app.extractors.entity_extraction.default_llm_client.get_structured_llm") as mock_get_structured_llm:
        mock_runnable = MagicMock()
        mock_get_structured_llm.return_value = mock_runnable
        
        mock_runnable.invoke.return_value = ExtractedEntities(
            parties=["Ram Kumar", "Shyam Lal"],
            dates=["15/08/2025", "5th of each month"],
            amounts=["₹12,000"],
            obligations=["Tenant must keep the premises clean"],
            suggested_questions=["What is the rent amount?", "When is the rent due?"]
        )
        
        try:
            print("Calling extract_entities_via_llm...")
            res = extract_entities_via_llm(test_text)
            print("Result was:", res)
        except Exception as e:
            print("Raised exception:", e)
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    debug_extraction()
