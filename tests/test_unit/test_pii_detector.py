import pytest

from app.services.pii_detector import PIIDetector


@pytest.fixture
def detector():
    return PIIDetector()


def test_no_pii_returns_clean_result(detector):
    text = "Diskusi ini membahas algoritma sorting dan kompleksitas waktu."
    result = detector.detect(text)

    assert result.has_pii is False
    assert result.labels == []
    assert result.masked_text == text


def test_email_is_detected(detector):
    result = detector.detect("Hubungi user@example.com untuk informasi lebih lanjut")

    assert result.has_pii is True
    assert result.labels == ["email"]


def test_phone_with_plus_62_is_detected(detector):
    result = detector.detect("Nomor saya +6281234567890")

    assert "phone" in result.labels


def test_phone_with_zero_prefix_is_detected(detector):
    result = detector.detect("Nomor saya 081234567890")

    assert result.labels == ["phone"]


def test_plain_sixteen_digit_number_detects_id_and_credit_card(detector):
    result = detector.detect("NIK saya 1234567890123456")

    assert "id_number" in result.labels
    assert "credit_card" in result.labels


def test_credit_card_with_dashes_is_detected(detector):
    result = detector.detect("Kartu 1234-5678-9012-3456 digunakan untuk simulasi")

    assert result.labels == ["credit_card"]


def test_multiple_pii_types_are_all_detected(detector):
    text = "Email user@example.com, telepon 081234567890, dan kartu 1234-5678-9012-3456"
    result = detector.detect(text)

    assert result.has_pii is True
    assert result.labels == ["email", "phone", "credit_card"]


def test_mask_replaces_email(detector):
    masked = detector.mask("Email user@example.com sudah tercatat")

    assert masked == "Email [EMAIL] sudah tercatat"


def test_mask_replaces_phone(detector):
    masked = detector.mask("Silakan hubungi 081234567890 sekarang")

    assert masked == "Silakan hubungi [PHONE] sekarang"


def test_mask_replaces_id_number_before_credit_card(detector):
    masked = detector.mask("NIK 1234567890123456")

    assert masked == "NIK [ID_NUMBER]"


def test_mask_replaces_credit_card(detector):
    masked = detector.mask("Kartu 1234-5678-9012-3456 perlu disamarkan")

    assert masked == "Kartu [CREDIT_CARD] perlu disamarkan"


def test_mask_returns_same_text_when_no_pii(detector):
    text = "Tidak ada data sensitif di kalimat ini."

    assert detector.mask(text) == text


def test_multiple_emails_are_all_masked(detector):
    masked = detector.mask("a@example.com dan b@example.org sedang diuji")

    assert masked.count("[EMAIL]") == 2


def test_short_numbers_are_not_detected_as_phone_or_id(detector):
    result = detector.detect("Kode kelas 12345 dan nomor meja 87654321")

    assert result.has_pii is False
    assert result.labels == []


def test_phone_regex_rejects_invalid_eight_series(detector):
    result = detector.detect("Nomor 080123456789 tidak valid untuk pola ini")

    assert result.has_pii is False


def test_masked_text_from_detect_matches_mask_method(detector):
    text = "Kontak user@example.com atau 081234567890"
    result = detector.detect(text)

    assert result.masked_text == detector.mask(text)
