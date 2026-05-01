import random

from app.services import socratic_filter as socratic_filter_module

from app.services.socratic_filter import SocraticFilter, SocraticResult, get_socratic_filter


def test_short_response_is_exempt():
    filter_service = SocraticFilter()
    result = filter_service.check_response("jelaskan AI", "singkat sekali")
    assert isinstance(result, SocraticResult)
    assert result.is_direct_answer is False
    assert result.reason == "exempt_query_or_short_response"


def test_greeting_query_halo_is_exempt():
    filter_service = SocraticFilter()
    response = "Ini adalah respons yang panjang sekali agar lolos batas minimal panjang namun query tetap salam biasa."
    result = filter_service.check_response("halo", response)
    assert result.is_direct_answer is False
    assert result.reason == "exempt_query_or_short_response"


def test_terima_kasih_query_is_exempt():
    filter_service = SocraticFilter()
    response = "Respons ini panjang dan informatif sehingga bukan karena pendek, tetapi karena query termasuk pola exempt."
    result = filter_service.check_response("terima kasih", response)
    assert result.is_direct_answer is False
    assert result.reason == "exempt_query_or_short_response"


def test_response_with_question_mark_is_already_scaffolded():
    filter_service = SocraticFilter()
    response = "Mari pikirkan ini bersama. Apa hubungan konsep pertama dengan konsep kedua?"
    result = filter_service.check_response("jelaskan konsep", response)
    assert result.is_direct_answer is False
    assert result.reason == "already_scaffolded"


def test_response_with_coba_pikirkan_is_already_scaffolded():
    filter_service = SocraticFilter()
    response = "Coba pikirkan hubungan antara variabel masukan dengan hasil akhir sebelum menyimpulkan jawaban final."
    result = filter_service.check_response("jelaskan konsep", response)
    assert result.is_direct_answer is False
    assert result.reason == "already_scaffolded"


def test_direct_answer_is_detected():
    filter_service = SocraticFilter()
    response = "Jawabannya adalah X. Konsep ini merupakan Y yang digunakan untuk menjelaskan hubungan antar bagian sistem secara menyeluruh."
    result = filter_service.check_response("apa jawabannya", response)
    assert result.is_direct_answer is True
    assert result.reason == "direct_answer_without_scaffolding"
    assert result.confidence >= 0.25


def test_direct_answer_has_scaffolded_response():
    filter_service = SocraticFilter()
    random.seed(42)
    response = "Jawabannya adalah X. Konsep ini merupakan Y yang digunakan untuk menjelaskan hubungan antar bagian sistem secara menyeluruh."
    result = filter_service.check_response("apa jawabannya", response)
    assert result.scaffolded_response is not None
    assert len(result.scaffolded_response) > 0


def test_acceptable_response_is_not_direct_and_not_scaffolded():
    filter_service = SocraticFilter()
    response = "Respons ini cukup panjang untuk diperiksa, namun hanya berisi uraian naratif deskriptif tanpa pola jawaban langsung yang kuat atau pertanyaan balikan eksplisit"
    result = filter_service.check_response("jelaskan konsep", response)
    assert result.is_direct_answer is False
    assert result.reason == "acceptable_response"
    assert result.scaffolded_response is None


def test_is_exempt_query_detects_various_greetings():
    filter_service = SocraticFilter()
    assert filter_service._is_exempt_query("Hai teman") is True
    assert filter_service._is_exempt_query("hello there") is True
    assert filter_service._is_exempt_query("selamat pagi") is True


def test_is_exempt_query_returns_false_for_regular_query():
    filter_service = SocraticFilter()
    assert filter_service._is_exempt_query("jelaskan konsep rekursi") is False


def test_has_scaffolding_detects_various_indicators():
    filter_service = SocraticFilter()
    assert filter_service._has_scaffolding("Menurutmu bagaimana hubungan dua konsep ini") is True
    assert filter_service._has_scaffolding("Hint kecil: fokus pada data input dan output") is True
    assert filter_service._has_scaffolding("Bagaimana jika parameter utamanya berubah total") is True


def test_has_scaffolding_returns_false_for_plain_statement():
    filter_service = SocraticFilter()
    assert filter_service._has_scaffolding("Penjelasan ini bersifat deskriptif panjang tanpa arahan bertanya kepada pembaca sama sekali") is False


def test_is_direct_answer_scoring_detects_strong_answer_pattern():
    filter_service = SocraticFilter()
    score = filter_service._is_direct_answer("Jawabannya adalah X. Konsep ini adalah metode formal untuk analisis struktur sistem.")
    assert score >= 0.25


def test_is_direct_answer_scoring_is_low_for_question_heavy_text():
    filter_service = SocraticFilter()
    score = filter_service._is_direct_answer("Apa itu konsep ini? Mengapa konsep ini penting? Bagaimana konsep ini bekerja?")
    assert score < 0.25


def test_scaffolded_response_contains_template_elements_deterministically():
    filter_service = SocraticFilter()
    random.seed(42)
    response = "Jawabannya adalah X. Konsep ini merupakan Y yang digunakan untuk menjelaskan hubungan antar bagian sistem secara menyeluruh."
    scaffolded = filter_service._generate_scaffolded_response("apa jawabannya", response)
    assert "Konsep ini merupakan Y yang digunakan untuk menjelaskan hubungan antar bagian sistem secara menyeluruh" in scaffolded
    assert "Jawabannya adalah X" in scaffolded
    assert any(marker in scaffolded for marker in ["1.", "Pertama,", "- "])


def test_empty_response_is_exempt():
    filter_service = SocraticFilter()
    result = filter_service.check_response("jelaskan AI", "")
    assert result.is_direct_answer is False
    assert result.reason == "exempt_query_or_short_response"


def test_generate_scaffolded_response_falls_back_to_default_hints_when_needed():
    filter_service = SocraticFilter()
    random.seed(42)
    scaffolded = filter_service._generate_scaffolded_response("apa itu recursion", "Pendek sekali")
    assert "Pikirkan tentang konsep dasar yang terkait dengan 'apa itu recursion'" in scaffolded
    assert "Bagaimana konsep ini berhubungan dengan apa yang sudah kamu pelajari sebelumnya?" in scaffolded


def test_long_direct_answer_without_question_marks_gets_bonus_score():
    filter_service = SocraticFilter()
    response = "Konsep ini adalah pendekatan sistematis untuk memahami hubungan antar komponen dalam arsitektur perangkat lunak. " * 3
    score = filter_service._is_direct_answer(response)
    assert score > 0.25


def test_get_socratic_filter_returns_singleton_instance():
    socratic_filter_module._socratic_filter = None

    instance_one = get_socratic_filter()
    instance_two = get_socratic_filter()

    assert isinstance(instance_one, SocraticFilter)
    assert instance_one is instance_two
