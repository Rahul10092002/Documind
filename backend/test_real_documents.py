import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Ensure the backend directory is in python path
backend_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(backend_dir)

load_dotenv()

from app.utils.pdf_extraction import extract_text_from_pdf
from app.utils.entity_extraction import run_full_entity_extraction

def test_real_doc(file_path: Path):
    print(f"\n==================================================================")
    print(f" TESTING ENTITY EXTRACTION ON: {file_path.name}")
    print(f"==================================================================")
    
    if not file_path.exists():
        print(f"ERROR: File {file_path} does not exist.")
        return
        
    try:
        print("1. Extracting text from PDF...")
        text = extract_text_from_pdf(file_path)
        print(f"   Success! Extracted {len(text)} characters.")
        
        print("2. Running full entity extraction pass...")
        entities = run_full_entity_extraction(text)
        
        print("\n3. RESULTS:")
        print(f"   Dates Extracted ({len(entities['dates'])}): {entities['dates']}")
        print(f"   Amounts Extracted ({len(entities['amounts'])}): {entities['amounts']}")
        print(f"   Parties Extracted ({len(entities['parties'])}): {entities['parties']}")
        print(f"   Obligations Extracted ({len(entities['obligations'])}): {entities['obligations']}")
        
    except Exception as e:
        print(f"❌ ERROR encountered during testing: {e}")
        import traceback
        traceback.print_exc()

def main():
    uploads_dir = Path(backend_dir) / "uploads"
    
    # Locate 3 real candidate documents in uploads
    candidates = [
        "20260622_165511_892650_Lease_Agreement.pdf",
        "20260622_165652_419608_Purchase_Agreement.pdf",
        "20260622_085054_641789_Rahul_Patidar_Resume.pdf"
    ]
    
    # If standard ones aren't found, find any PDF files
    to_test = []
    for c in candidates:
        p = uploads_dir / c
        if p.exists():
            to_test.append(p)
            
    if len(to_test) < 3:
        # Fallback to any PDF files in uploads
        all_pdfs = list(uploads_dir.glob("*.pdf"))
        for pdf in all_pdfs:
            if pdf not in to_test:
                to_test.append(pdf)
            if len(to_test) == 3:
                break
                
    if not to_test:
        print("No PDF files found in uploads directory.")
        return
        
    print(f"Found {len(to_test)} real documents to test: {[p.name for p in to_test]}")
    for pdf_path in to_test:
        test_real_doc(pdf_path)

if __name__ == "__main__":
    main()
