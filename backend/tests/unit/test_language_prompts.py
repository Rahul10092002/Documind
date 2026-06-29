import os
import sys
import unittest
from unittest.mock import MagicMock, patch

# Ensure standard output uses UTF-8 to prevent console encoding issues on Windows
sys.stdout.reconfigure(encoding='utf-8')

# Ensure the backend directory is in the path
backend_path = os.path.dirname(os.path.abspath(__file__))
if backend_path not in sys.path:
    sys.path.insert(0, backend_path)

from app.extractors.entity_extraction import extract_entities_via_llm
from app.services import generate_risk_and_draft


class TestLanguagePrompts(unittest.TestCase):
    
    @patch("app.utils.entity_extraction.default_llm_client.get_structured_llm")
    def test_extract_entities_language_instructions_hindi(self, mock_get_structured_llm):
        mock_runnable = MagicMock()
        mock_get_structured_llm.return_value = mock_runnable
        
        from app.utils.entity_extraction import ExtractedEntities
        mock_data = ExtractedEntities(
            parties=["parties"],
            dates=["dates"],
            amounts=["amounts"],
            obligations=["obligations"],
            suggested_questions=["questions"]
        )
        mock_runnable.invoke.return_value = mock_data
        mock_runnable.return_value = mock_data
        
        # Run extraction with language 'hi'
        extract_entities_via_llm("Dummy legal text", language="hi")
        
        # Check call arguments
        if mock_runnable.invoke.called:
            prompt_val = mock_runnable.invoke.call_args[0][0]
        else:
            prompt_val = mock_runnable.call_args[0][0]
        human_text = prompt_val.to_messages()[1].content
        self.assertIn("in Hindi (Devanagari script)", human_text)
        self.assertIn("Hindi (Devanagari script)", human_text)

    @patch("app.utils.entity_extraction.default_llm_client.get_structured_llm")
    def test_extract_entities_language_instructions_english(self, mock_get_structured_llm):
        mock_runnable = MagicMock()
        mock_get_structured_llm.return_value = mock_runnable
        
        from app.utils.entity_extraction import ExtractedEntities
        mock_data = ExtractedEntities(
            parties=["parties"],
            dates=["dates"],
            amounts=["amounts"],
            obligations=["obligations"],
            suggested_questions=["questions"]
        )
        mock_runnable.invoke.return_value = mock_data
        mock_runnable.return_value = mock_data
        
        # Run extraction with language 'en'
        extract_entities_via_llm("Dummy legal text", language="en")
        
        if mock_runnable.invoke.called:
            prompt_val = mock_runnable.invoke.call_args[0][0]
        else:
            prompt_val = mock_runnable.call_args[0][0]
        human_text = prompt_val.to_messages()[1].content
        self.assertIn("in English", human_text)
        self.assertIn("English", human_text)

    @patch("app.utils.answer_service.default_llm_client.get_resilient_llm")
    @patch("app.utils.answer_service.default_llm_client.get_primary_llm")
    def test_generate_risk_and_draft_language_instructions_hindi(self, mock_get_primary, mock_get_resilient):
        mock_llm = MagicMock()
        mock_get_resilient.return_value = mock_llm
        mock_get_primary.return_value = MagicMock()
        
        from langchain_core.messages import AIMessage
        mock_message = AIMessage(content='{"risk_flags": [], "risk_obligation_summary": "Hindi summary"}')
        mock_llm.return_value = mock_message
        mock_llm.invoke.return_value = mock_message
        
        # Run with 'hi-Latn' (Hinglish/Hindi)
        generate_risk_and_draft("Dummy legal text", language="hi-Latn")
        
        self.assertTrue(mock_llm.invoke.called or mock_llm.called)
        
        # Extract prompt argument depending on how it was invoked
        if mock_llm.invoke.called:
            prompt_val = mock_llm.invoke.call_args[0][0]
        else:
            prompt_val = mock_llm.call_args[0][0]
            
        system_text = prompt_val.to_messages()[0].content
        self.assertIn("Hindi (in Devanagari script)", system_text)

    @patch("app.utils.answer_service.default_llm_client.get_resilient_llm")
    @patch("app.utils.answer_service.default_llm_client.get_primary_llm")
    def test_generate_risk_and_draft_language_instructions_english(self, mock_get_primary, mock_get_resilient):
        mock_llm = MagicMock()
        mock_get_resilient.return_value = mock_llm
        mock_get_primary.return_value = MagicMock()
        
        from langchain_core.messages import AIMessage
        mock_message = AIMessage(content='{"risk_flags": [], "risk_obligation_summary": "English summary"}')
        mock_llm.return_value = mock_message
        mock_llm.invoke.return_value = mock_message
        
        # Run with 'en'
        generate_risk_and_draft("Dummy legal text", language="en")
        
        self.assertTrue(mock_llm.invoke.called or mock_llm.called)
        
        # Extract prompt argument depending on how it was invoked
        if mock_llm.invoke.called:
            prompt_val = mock_llm.invoke.call_args[0][0]
        else:
            prompt_val = mock_llm.call_args[0][0]
            
        system_text = prompt_val.to_messages()[0].content
        self.assertIn("English", system_text)


if __name__ == "__main__":
    unittest.main()
