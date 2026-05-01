from app.services.pii_detector import PIIDetector, PIIDetectionResult


def test_no_pii_returns_false_and_empty_labels():
    result = PIIDetector().detect("Mari belajar struktur data bersama.")

    assert isinstance(result, PIIDetectionResult)
    assert result.has_pii is False
    assert result.labels == []
    assert result.masked_text == "Mari belajar struktur data bersama."


def test_detects_email_address():
    result = PIIDetector().detect("Email saya user@example.com")

    assert result.has_pii is True
    assert result.labels == ["email"]
    assert result.masked_text == "Email saya [EMAIL]"


def test_detects_phone_with_plus62_prefix():
    result = PIIDetector().detect("+6281234567890")

    assert result.has_pii is True
    assert result.labels == ["phone"]
    assert result.masked_text == "+[PHONE]"


def test_detects_phone_with_zero_prefix():
    result = PIIDetector().detect("081234567890")

    assert result.has_pii is True
    assert result.labels == ["phone"]
    assert result.masked_text == "[PHONE]"


def test_detects_phone_with_62_prefix():
    result = PIIDetector().detect("6281234567890")

    assert result.has_pii is True
    assert result.labels == ["phone"]
    assert result.masked_text == "[PHONE]"


def test_detects_exact_sixteen_digit_id_number():
    result = PIIDetector().detect("1234567890123456")

    assert result.has_pii is True
    assert "id_number" in result.labels
    assert result.masked_text == "[ID_NUMBER]"


def test_detects_credit_card_with_dashes():
    result = PIIDetector().detect("1234-5678-9012-3456")

    assert result.has_pii is True
    assert result.labels == ["credit_card"]
    assert result.masked_text == "[CREDIT_CARD]"


def test_detects_credit_card_with_spaces():
    result = PIIDetector().detect("1234 5678 9012 3456")

    assert result.has_pii is True
    assert result.labels == ["credit_card"]
    assert result.masked_text == "[CREDIT_CARD]"


def test_detects_multiple_pii_types_in_one_text():
    text = "Kontak user@example.com, 081234567890, dan 1234-5678-9012-3456"
    result = PIIDetector().detect(text)

    assert result.has_pii is True
    assert result.labels == ["email", "phone", "credit_card"]
    assert result.masked_text == "Kontak [EMAIL], [PHONE], dan [CREDIT_CARD]"


def test_mask_replaces_email_placeholder():
    masked = PIIDetector().mask("user@example.com")

    assert masked == "[EMAIL]"


def test_mask_replaces_phone_placeholder():
    masked = PIIDetector().mask("081234567890")

    assert masked == "[PHONE]"


def test_mask_replaces_id_number_placeholder():
    masked = PIIDetector().mask("1234567890123456")

    assert masked == "[ID_NUMBER]"


def test_mask_replaces_credit_card_placeholder():
    masked = PIIDetector().mask("1234-5678-9012-3456")

    assert masked == "[CREDIT_CARD]"


def test_partial_id_number_with_fifteen_digits_does_not_match():
    result = PIIDetector().detect("123456789012345")

    assert result.has_pii is False
    assert result.labels == []
    assert result.masked_text == "123456789012345"


def test_incomplete_credit_card_does_not_match():
    result = PIIDetector().detect("1234-5678-9012")

    assert result.has_pii is False
    assert result.labels == []
    assert result.masked_text == "1234-5678-9012"


def test_invalid_phone_prefix_does_not_match():
    result = PIIDetector().detect("071234567890")

    assert result.has_pii is False
    assert result.labels == []
    assert result.masked_text == "071234567890"


def test_empty_string_returns_no_pii():
    result = PIIDetector().detect("")

    assert result.has_pii is False
    assert result.labels == []
    assert result.masked_text == ""


def test_numbers_without_pii_pattern_stay_unmasked():
    result = PIIDetector().detect("Nilai 123 dan 4567 bukan data pribadi")

    assert result.has_pii is False
    assert result.labels == []
    assert result.masked_text == "Nilai 123 dan 4567 bukan data pribadi"


def test_sixteen_digits_overlap_with_credit_card_label():
    result = PIIDetector().detect("1234567890123456")

    assert result.labels == ["id_number", "credit_card"]
    assert result.masked_text == "[ID_NUMBER]"
