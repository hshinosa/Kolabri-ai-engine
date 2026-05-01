from app.services.grounding_verifier import GroundingVerifier, GroundingResult


def test_verify_grounding_with_empty_documents_fails():
    verifier = GroundingVerifier()
    result = verifier.verify_grounding("Fakta penting tentang AI.", [])
    assert isinstance(result, GroundingResult)
    assert result.is_grounded is False
    assert result.grounding_ratio == 0.0
    assert result.total_claims == 1


def test_verify_grounding_with_no_extractable_claims_passes():
    verifier = GroundingVerifier()
    result = verifier.verify_grounding("", [{"content": "dokumen pendukung"}])
    assert result.is_grounded is True
    assert result.grounding_ratio == 1.0
    assert result.total_claims == 0


def test_grounded_response_with_high_overlap_passes():
    verifier = GroundingVerifier()
    documents = [{"content": "kucing makan ikan segar setiap pagi di rumah"}]
    response = "kucing makan ikan segar setiap pagi di rumah"
    result = verifier.verify_grounding(response, documents)
    assert result.is_grounded is True
    assert result.grounded_claims == [response]
    assert result.ungrounded_claims == []


def test_ungrounded_response_with_no_overlap_fails():
    verifier = GroundingVerifier()
    documents = [{"content": "kucing makan ikan di dapur"}]
    response = "mesin roket meluncur ke orbit malam ini"
    result = verifier.verify_grounding(response, documents)
    assert result.is_grounded is False
    assert result.grounded_claims == []
    assert result.ungrounded_claims == [response]


def test_extract_claims_question_sentence_can_survive_split_artifact():
    verifier = GroundingVerifier()
    claims = verifier._extract_claims("Apakah kita siap sekarang? Fakta penting tentang sistem ini berjalan stabil")
    assert claims == ["Apakah kita siap sekarang", "Fakta penting tentang sistem ini berjalan stabil"]


def test_extract_claims_filters_maaf_sentences():
    verifier = GroundingVerifier()
    claims = verifier._extract_claims("Maaf saya tidak tahu jawabannya. Sistem ini berjalan setiap hari dengan stabil")
    assert claims == ["Sistem ini berjalan setiap hari dengan stabil"]


def test_extract_claims_filters_mungkin_sentences():
    verifier = GroundingVerifier()
    claims = verifier._extract_claims("Mungkin ini benar untuk kasus tertentu. Sistem ini membutuhkan validasi data yang ketat")
    assert claims == ["Sistem ini membutuhkan validasi data yang ketat"]


def test_extract_claims_filters_silakan_sentences():
    verifier = GroundingVerifier()
    claims = verifier._extract_claims("Silakan coba cek kembali sumbernya. Basis data menyimpan riwayat interaksi pengguna")
    assert claims == ["Basis data menyimpan riwayat interaksi pengguna"]


def test_extract_claims_filters_short_sentences():
    verifier = GroundingVerifier()
    claims = verifier._extract_claims("Singkat. Ini adalah kalimat yang cukup panjang untuk diproses")
    assert claims == ["Ini adalah kalimat yang cukup panjang untuk diproses"]


def test_extract_claims_returns_first_sentence_when_all_are_non_factual_but_long():
    verifier = GroundingVerifier()
    response = "Mungkin asumsi ini perlu diperiksa ulang secara mendalam. Silakan cek kembali dokumen utama sekarang"
    claims = verifier._extract_claims(response)
    assert claims == ["Mungkin asumsi ini perlu diperiksa ulang secara mendalam"]


def test_compute_similarity_identical_texts_is_one():
    verifier = GroundingVerifier()
    similarity = verifier._compute_similarity("alpha beta gamma", "alpha beta gamma")
    assert similarity == 1.0


def test_compute_similarity_no_overlap_is_zero():
    verifier = GroundingVerifier()
    similarity = verifier._compute_similarity("alpha beta", "gamma delta")
    assert similarity == 0.0


def test_compute_similarity_partial_overlap_uses_jaccard_ratio():
    verifier = GroundingVerifier()
    similarity = verifier._compute_similarity("alpha beta", "alpha gamma")
    assert similarity == 1 / 3


def test_compute_similarity_empty_strings_is_zero():
    verifier = GroundingVerifier()
    similarity = verifier._compute_similarity("", "")
    assert similarity == 0.0


def test_custom_thresholds_can_make_partially_grounded_response_pass():
    verifier = GroundingVerifier()
    documents = [{"content": "python digunakan untuk analisis data dan otomasi sistem"}]
    response = "python digunakan untuk analisis data. basis data berjalan di server terpisah"
    result = verifier.verify_grounding(response, documents, threshold=0.5, claim_threshold=0.3)
    assert result.is_grounded is True
    assert result.grounding_ratio == 0.5


def test_documents_can_use_page_content_key():
    verifier = GroundingVerifier()
    response = "sistem ini memproses data transaksi harian dengan cepat"
    documents = [{"page_content": "sistem ini memproses data transaksi harian dengan cepat"}]
    result = verifier.verify_grounding(response, documents)
    assert result.is_grounded is True
    assert result.grounded_claims == [response]


def test_multiple_documents_allow_claim_to_match_one_document():
    verifier = GroundingVerifier()
    response = "mesin pembelajaran mendukung prediksi nilai mahasiswa secara otomatis"
    documents = [
        {"content": "arsitektur sistem menggunakan layanan terpisah untuk logging"},
        {"content": "mesin pembelajaran mendukung prediksi nilai mahasiswa secara otomatis"},
    ]
    result = verifier.verify_grounding(response, documents)
    assert result.is_grounded is True
    assert result.grounded_claims == [response]


def test_confidence_is_capped_at_one_for_large_margin():
    verifier = GroundingVerifier()
    result = verifier.verify_grounding("alpha beta gamma delta epsilon", [{"content": "alpha beta gamma delta epsilon"}], threshold=0.1)
    assert result.confidence == 1.0
