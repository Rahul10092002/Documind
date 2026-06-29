import os
import sys
from pathlib import Path

# Add backend directory to path
backend_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(backend_dir)

from app.agents.ingestion_agent import ingestion_agent
from app.extractors.pdf_extraction import verify_devanagari_quality

def get_pipeline_type(file_path: Path) -> str:
    ext = file_path.suffix.lower()
    if ext == ".pdf":
        return "pdf"
    elif ext in (".docx", ".doc"):
        return "word"
    elif ext in (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tiff"):
        return "image"
    elif ext in (".txt", ".md", ".json", ".xml"):
        return "text"
    return None

def main():
    test_files_dir = Path(backend_dir) / "test_files"
    if not test_files_dir.exists():
        print(f"Error: Directory '{test_files_dir}' not found.")
        sys.exit(1)
        
    print(f"Scanning directory: {test_files_dir}")
    print("=" * 60)
    
    files_to_process = [f for f in test_files_dir.iterdir() if f.is_file()]
    if not files_to_process:
        print("No files found to process.")
        sys.exit(0)
        
    for file_path in files_to_process:
        pipeline = get_pipeline_type(file_path)
        if not pipeline:
            print(f"Skipping unsupported file: {file_path.name}")
            print("-" * 60)
            continue
            
        print(f"\nProcessing: {file_path.name} (Pipeline: {pipeline})")
        print("-" * 60)
        
        try:
            # Initialize default DocuMindState values needed by the agent
            initial_state = {
                "document_id": f"test_{file_path.stem}",
                "file_path": str(file_path),
                "pipeline_type": pipeline,
                "prompt_locale": None,
                "errors": [],
                "retry_count": 0,
                "raw_bytes": b"",
                "raw_text": "",
                "documents": [],
                "is_scanned": False,
                "char_count": 0,
            }
            
            state = ingestion_agent(initial_state)
            
            if state.get("current_step") == "failed":
                raise RuntimeError(f"Ingestion agent failed: {state.get('errors')}")
                
            raw_text = state["raw_text"]
            docs = state["documents"]
            
            print("EXTRACTION METRICS:")
            print(f"  Character count: {len(raw_text)}")
            print(f"  Document chunks: {len(docs)}")
            
            # Show metadata sample
            if docs:
                print(f"  First chunk metadata: {docs[0].metadata}")
            
            # Verify Devanagari quality for text extracted
            quality = verify_devanagari_quality(raw_text)
            print(f"  Devanagari Quality OK: {quality['ok']} (Word count: {quality['word_count']})")
            if quality['issues']:
                print("  Quality Issues:")
                for issue in quality['issues']:
                    print(f"    - {issue}")
                
            # Save output to a file for manual review
            output_txt = file_path.with_suffix(file_path.suffix + ".extracted.txt")
            output_txt.write_text(raw_text, encoding="utf-8")
            print(f"  Extracted text saved to: {output_txt.name}")
            
            # Show first 400 characters
            print("  PREVIEW (FIRST 400 CHARS):")
            print("  " + "-" * 40)
            preview = raw_text[:400].replace("\n", "\n  ")
            print(f"  {preview}")
            print("  " + "-" * 40)
            
        except Exception as e:
            print(f"❌ Error during extraction of {file_path.name}: {e}")
            import traceback
            traceback.print_exc()
            
        print("=" * 60)

if __name__ == "__main__":
    main()
