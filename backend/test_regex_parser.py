from app.utils.regex_parser import extract_dates, extract_currencies, extract_entities_via_regex


def test_numerical_dates_english():
    text = "The agreement date is 15/08/2025, and another date is 2024-12-31. We should also catch 01.01.2023 and short year 15/08/25."
    dates = extract_dates(text)
    
    assert "15/08/2025" in dates
    assert "2024-12-31" in dates
    assert "01.01.2023" in dates
    assert "15/08/25" in dates


def test_numerical_dates_devanagari():
    text = "यह दिनांक १५/०८/२०२५ को हस्ताक्षरित है और ३१-१२-२०२४ तक वैध है।"
    dates = extract_dates(text)
    
    assert "१५/०८/२०२५" in dates
    assert "३१-१२-२०२४" in dates


def test_textual_dates_english():
    text = "Important dates: 15th August 2025, 15 August 2025, August 15, 2025, and 15-Jan-2025."
    dates = extract_dates(text)
    
    assert "15th August 2025" in dates
    assert "15 August 2025" in dates
    assert "August 15, 2025" in dates
    assert "15-Jan-2025" in dates


def test_textual_dates_hindi():
    text = "दिनांक १५ अगस्त २०२५ को काम होगा। 15 जनवरी 2025 को बैठक है। दिनांक २५-१२-२०२३ को अवकाश था।"
    dates = extract_dates(text)
    
    assert "१५ अगस्त २०२५" in dates
    assert "15 जनवरी 2025" in dates
    assert "२५-१२-२०२३" in dates or "दिनांक २५-१२-२०२३" in dates


def test_currencies_english_prefix():
    text = "The amount is ₹12,000. Other charges: Rs. 50,000, Rs 500, and INR 1,00,000.00. Large: ₹ 1.5 Crore or ₹ 5 Lakh."
    currencies = extract_currencies(text)
    
    assert any("₹12,000" in c or "₹12000" in c for c in currencies)
    assert any("Rs. 50,000" in c or "Rs 50,000" in c for c in currencies)
    assert any("Rs 500" in c for c in currencies)
    assert any("INR 1,00,000.00" in c or "INR 1,00,000" in c for c in currencies)
    assert any("1.5 Crore" in c for c in currencies)
    assert any("5 Lakh" in c for c in currencies)


def test_currencies_english_suffix():
    text = "Payments of 50,000 rupees and 12,000 Rupees are due."
    currencies = extract_currencies(text)
    
    assert any("50,000 rupees" in c or "50,000 Rupees" in c for c in currencies)
    assert any("12,000 Rupees" in c for c in currencies)


def test_currencies_hindi():
    text = "कुल राशि ₹५०,००० है, जिसमें से ५०,००० रुपये (या १० लाख रुपये) अग्रिम भुगतान है। ५० हजार रुपये बकाया हैं।"
    currencies = extract_currencies(text)
    
    assert any("₹५०,०००" in c for c in currencies)
    assert any("५०,००० रुपये" in c for c in currencies)
    assert any("१० लाख रुपये" in c for c in currencies)
    assert any("५० हजार रुपये" in c or "५० हजार" in c for c in currencies)


def test_extract_entities_via_regex():
    text = "Agreement signed on 15/08/2025 for a sum of ₹1,00,000."
    entities = extract_entities_via_regex(text)
    
    assert "15/08/2025" in entities["dates"]
    assert any("₹1,00,000" in c for c in entities["amounts"])
    assert entities["parties"] == []
    assert entities["obligations"] == []


if __name__ == "__main__":
    print("Running Regex Parser Test Suite...")
    test_numerical_dates_english()
    print("- test_numerical_dates_english: PASSED")
    test_numerical_dates_devanagari()
    print("- test_numerical_dates_devanagari: PASSED")
    test_textual_dates_english()
    print("- test_textual_dates_english: PASSED")
    test_textual_dates_hindi()
    print("- test_textual_dates_hindi: PASSED")
    test_currencies_english_prefix()
    print("- test_currencies_english_prefix: PASSED")
    test_currencies_english_suffix()
    print("- test_currencies_english_suffix: PASSED")
    test_currencies_hindi()
    print("- test_currencies_hindi: PASSED")
    test_extract_entities_via_regex()
    print("- test_extract_entities_via_regex: PASSED")
    print("ALL TESTS PASSED SUCCESSFULLY!")

