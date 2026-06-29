import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.utils.llm_client import default_llm_client

def test_llms():
    print("Testing Primary LLM:")
    try:
        primary = default_llm_client.get_primary_llm()
        resp = primary.invoke("Say hello")
        print("Primary response:", resp.content)
    except Exception as e:
        print("Primary failed with:", type(e), e)

    print("\nTesting Fallback LLM:")
    try:
        fallback = default_llm_client.get_fallback_llm()
        resp = fallback.invoke("Say hello")
        print("Fallback response:", resp.content)
    except Exception as e:
        print("Fallback failed with:", type(e), e)

if __name__ == "__main__":
    test_llms()
