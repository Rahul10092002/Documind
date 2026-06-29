import os
import sys

# Ensure the backend directory is in the python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import settings
from app.llm import default_llm_client

def main():
    print("==================================================")
    print("          LLM Provider Configuration Checker")
    print("==================================================")
    
    # 1. Read Settings
    provider_env = settings.llm_provider.lower()
    fallback_enabled = settings.enable_gemini_fallback
    groq_api_key = settings.groq_api_key
    google_api_key = settings.effective_google_api_key
    
    print(f"Configured Primary Provider : {provider_env.upper()}")
    print(f"Fallback to Gemini Enabled  : {fallback_enabled}")
    print(f"Groq API Key Configured    : {'Yes' if groq_api_key else 'No'}")
    print(f"Google/Gemini Key Configured: {'Yes' if google_api_key else 'No'}")
    print("-" * 50)
    
    # 2. Inspect Primary LLM Client Instance
    try:
        llm = default_llm_client.get_primary_llm()
        llm_class_name = type(llm).__name__
        print(f"Successfully initialized primary LLM client.")
        print(f"Primary Client Class Name   : {llm_class_name}")
        
        # Safely fetch model details
        if hasattr(llm, "model"):
            print(f"Primary Client Model Name   : {llm.model}")
        elif hasattr(llm, "model_name"):
            print(f"Primary Client Model Name   : {llm.model_name}")
    except Exception as e:
        print(f"[ERROR] Failed to initialize primary LLM client: {e}")
        
    # 3. Inspect Fallback LLM Client Instance (if applicable)
    if fallback_enabled and provider_env == "groq":
        try:
            print("-" * 50)
            gemini_llm = default_llm_client.get_fallback_llm()
            gemini_class_name = type(gemini_llm).__name__
            print(f"Successfully initialized fallback Gemini client.")
            print(f"Fallback Client Class Name  : {gemini_class_name}")
            if hasattr(gemini_llm, "model"):
                print(f"Fallback Client Model Name  : {gemini_llm.model}")
        except Exception as e:
            print("-" * 50)
            print(f"[WARNING] Fallback is enabled, but Gemini client initialization failed: {e}")
            
    print("==================================================")

if __name__ == "__main__":
    main()
