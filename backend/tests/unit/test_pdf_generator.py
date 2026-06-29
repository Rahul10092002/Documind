import unittest
from app.extractors.pdf_generator import generate_analysis_pdf
from app.models import AnalysisResult

class TestPDFGenerator(unittest.TestCase):
    def test_generate_analysis_pdf_empty(self):
        analysis = AnalysisResult(
            extracted_entities={
                "parties": [],
                "obligations": [],
                "amounts": [],
                "dates": []
            },
            risk_flags=[],
            risk_obligation_summary=""
        )
        pdf_bytes = generate_analysis_pdf("test.pdf", analysis)
        self.assertIsInstance(pdf_bytes, bytes)
        self.assertTrue(len(pdf_bytes) > 0)

    def test_generate_analysis_pdf_with_hindi_and_risks(self):
        analysis = AnalysisResult(
            extracted_entities={
                "parties": ["प्रथम पक्ष: राहुल पाटीदार", "द्वितीय पक्ष: डॉकमाइंड एआई"],
                "obligations": ["ठेकेदार ₹2,50,000 का भुगतान 15 मई 2025 तक करेगा।"],
                "amounts": ["₹2,50,000"],
                "dates": ["15 मई 2025"]
            },
            risk_flags=[
                {"level": "CRITICAL", "clause": "विलंब शुल्क", "reason": "प्रतिदिन 1% का जुर्माना लगेगा जो बहुत अधिक है।"}
            ],
            risk_obligation_summary="यह एक हिंदी सारांश है जो कि पीडीएफ जनरेटर का परीक्षण करता है।"
        )
        pdf_bytes = generate_analysis_pdf("hindi_report.pdf", analysis)
        self.assertIsInstance(pdf_bytes, bytes)
        self.assertTrue(len(pdf_bytes) > 0)

if __name__ == "__main__":
    unittest.main()
