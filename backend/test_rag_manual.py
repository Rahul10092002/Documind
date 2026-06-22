import os
import sys
from dotenv import load_dotenv

# Ensure the backend directory is in python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Load environment variables
load_dotenv()

from app.utils.rag import answer_question


def run_rag_test(doc_id: int, filename: str, tests: list[dict]):
    print(f"\n==================================================================")
    print(f" TESTING RAG ON DOCUMENT {doc_id}: '{filename}'")
    print(f"==================================================================")

    for idx, test in enumerate(tests, 1):
        print(f"\nQuery {idx}: '{test['question']}'")
        print("Retrieving context and generating answer...")
        try:
            answer = answer_question(document_id=doc_id, question=test["question"])
            print("-" * 65)
            print("ANSWER:")
            print(answer)
            print("-" * 65)

            # Assert expected keywords are in the generated answer
            for keyword in test.get("expected_keywords", []):
                assert keyword.lower() in answer.lower(), (
                    f"Assertion failed: Expected answer to contain '{keyword}'"
                )
            # Assert forbidden keywords are NOT in the generated answer
            for forbidden in test.get("forbidden_keywords", []):
                assert forbidden.lower() not in answer.lower(), (
                    f"Assertion failed: Expected answer NOT to contain '{forbidden}'"
                )
            print("Status: PASSED")
        except AssertionError as ae:
            print(f"Status: FAILED - {ae}")
            raise ae
        except Exception as e:
            print(f"Status: ERROR - {e}")
            raise e


def main():
    print("Starting Manual Verification on Uploaded Documents (Doc 10 & Doc 11)...")

    # Ensure GROQ_API_KEY is configured
    if not os.getenv("GROQ_API_KEY"):
        print("[ERROR]: GROQ_API_KEY is not configured in the environment.")
        return

    # 1. Document 10 Tests (Rahul Patidar's Resume)
    doc10_id = 10
    doc10_filename = "Rahul_Patidar_Resume.pdf"
    doc10_tests = [
        {
            "question": "Where did Rahul Patidar complete or study his Master of Computer Applications?",
            "expected_keywords": ["Devi Ahilya Vishwavidyalaya"],
            "forbidden_keywords": ["Virtual DOM", "Facebook"]
        },
        {
            "question": "What company did Rahul Patidar work for as a Software Developer Intern?",
            "expected_keywords": ["Teconico"],
            "forbidden_keywords": ["Facebook", "React"]
        }
    ]

    # 2. Document 11 Tests (React Notes)
    doc11_id = 11
    doc11_filename = "React Notes.pdf"
    doc11_tests = [
        {
            "question": "What is React and who created it?",
            "expected_keywords": ["library", "Facebook"],
            "forbidden_keywords": ["Patidar", "Teconico"]
        },
        {
            "question": "How does React work?",
            "expected_keywords": ["Virtual DOM"],
            "forbidden_keywords": ["Holkar", "Intern"]
        },
        # Isolation test: Ask a Document 10 question on Document 11
        {
            "question": "Where did Rahul Patidar study his Master of Computer Applications?",
            "expected_keywords": ["cannot find", "provided document context"],
            "forbidden_keywords": ["Devi Ahilya Vishwavidyalaya"]
        }
    ]

    try:
        run_rag_test(doc10_id, doc10_filename, doc10_tests)
        run_rag_test(doc11_id, doc11_filename, doc11_tests)
        print("\n==================================================================")
        print(" SUCCESS: RAG verified successfully on 2 real documents!")
        print(" Results are correct, grounded, and isolated per document.")
        print(" Definition of Done is fully met!")
        print("==================================================================")
    except Exception as e:
        print(f"\n[TEST FAILURE]: Verification failed during test run: {e}")


if __name__ == "__main__":
    main()
