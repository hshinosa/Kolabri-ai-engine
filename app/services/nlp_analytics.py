"""
NLP Analytics Service
=====================
Implements text mining techniques for learning engagement classification:
- Lexical Variety (TTR)
- Higher-Order Thinking (HOT) Detection
- Engagement Type Classification (Cognitive, Behavioral, Emotional)
"""

from typing import Dict, Any, List, Optional
from dataclasses import dataclass
from enum import Enum
import re

from app.core.logging import get_logger
from app.utils.text_processor import normalize_text, clean_for_ttr

logger = get_logger(__name__)


class EngagementType(str, Enum):
    """Types of learning engagement based on research framework."""
    COGNITIVE = "cognitive"      # Analysis, evaluation, critical thinking
    BEHAVIORAL = "behavioral"    # Participation, task completion
    EMOTIONAL = "emotional"      # Motivation, interest, frustration


@dataclass
class EngagementAnalysis:
    """Result of engagement analysis on text."""
    lexical_variety: float           # 0-1 score for vocabulary richness
    engagement_type: EngagementType  # Primary engagement category
    is_higher_order: bool            # Whether HOT is detected
    hot_indicators: List[str]        # Words/phrases that triggered HOT
    word_count: int                  # Total word count
    unique_words: int                # Unique meaningful words
    confidence: float                # Analysis confidence


class EngagementAnalyzer:
    """
    Analyzer for learning engagement using NLP techniques.
    
    Based on research methods using Text Mining and Deep Neural Networks
    for automatic engagement classification from discussion transcripts.
    """
    
    # Higher-Order Thinking (HOT) trigger words (Indonesian)
    # Based on Bloom's taxonomy: Analysis, Synthesis, Evaluation
    # Extended list for Indonesian academic discourse
    HOT_TRIGGERS_ID = [
        # === Causal Reasoning (Penalaran Kausal) ===
        "karena", "sebab", "akibat", "dampak", "pengaruh", "efek",
        "menyebabkan", "mengakibatkan", "berdampak", "berpengaruh",
        "oleh karena itu", "sehingga", "maka dari itu", "akibatnya",
        "konsekuensi", "implikasi", "berimplikasi",
        
        # === Analysis (Analisis - C4) ===
        "analisis", "menganalisis", "menyelidiki", "membedakan",
        "membandingkan", "menguraikan", "menjelaskan", "mengidentifikasi",
        "mengklasifikasi", "mengkategorikan", "memisahkan", "menghubungkan",
        "menemukan", "mendeteksi", "mengamati", "menelaah",
        "aspek", "komponen", "unsur", "elemen", "faktor",
        "struktur", "pola", "hubungan", "keterkaitan", "korelasi",
        
        # === Evaluation (Evaluasi - C5) ===
        "menilai", "mengevaluasi", "menyimpulkan", "kesimpulan",
        "memutuskan", "mengkritisi", "kritik", "menimbang",
        "mempertimbangkan", "menguji", "membuktikan", "memvalidasi",
        "memverifikasi", "mengukur", "memberi penilaian",
        "kelebihan", "kekurangan", "keunggulan", "kelemahan",
        "pro", "kontra", "positif", "negatif", "efektif", "efisien",
        "valid", "reliabel", "akurat", "tepat", "sesuai",
        "berdasarkan", "menurut", "berargumen", "beralasan",
        
        # === Synthesis (Sintesis - C6) ===
        "menggabungkan", "merancang", "menyusun", "menciptakan",
        "mengembangkan", "merumuskan", "mengkonstruksi", "membangun",
        "menghasilkan", "memproduksi", "mendesain", "memodifikasi",
        "mengintegrasikan", "menggeneralisasi", "merangkum",
        "hipotesis", "teori", "model", "kerangka", "konsep",
        "solusi", "alternatif", "inovasi", "usulan", "rekomendasi",
        
        # === Contrasting/Reasoning (Kontras & Penalaran) ===
        "namun", "tetapi", "meskipun", "walaupun", "sebaliknya",
        "berbeda dengan", "di sisi lain", "sementara itu", "padahal",
        "akan tetapi", "kendati", "biarpun", "walau bagaimanapun",
        "bertentangan", "berlawanan", "kontras", "paradoks",
        
        # === Questioning & Inquiry (Bertanya & Inkuiri) ===
        "mengapa", "bagaimana", "apa hubungan", "apa perbedaan",
        "apa persamaan", "apa alasan", "apa tujuan", "apa manfaat",
        "sejauh mana", "sampai dimana", "apakah mungkin", "bagaimana jika",
        "apa yang terjadi jika", "mengapa demikian", "mengapa tidak",
        
        # === Justification (Pembenaran) ===
        "alasan", "alasannya", "argumentasi", "argumen", "bukti",
        "evidensi", "data", "fakta", "logika", "rasional",
        "mendukung", "memperkuat", "membuktikan", "menunjukkan",
        
        # === Metacognitive (Metakognitif) ===
        "menurut saya", "pendapat saya", "saya pikir", "saya rasa",
        "saya yakin", "saya percaya", "menurut pendapat", "dari sudut pandang",
        "perspektif", "pandangan", "interpretasi", "pemahaman"
    ]
    
    # HOT triggers (English) - for bilingual/code-switching support
    HOT_TRIGGERS_EN = [
        # Causal
        "because", "therefore", "hence", "thus", "consequently",
        "as a result", "due to", "leads to", "causes", "affects",
        # Analysis
        "analyze", "examine", "investigate", "distinguish", "compare",
        "contrast", "identify", "classify", "categorize", "relate",
        # Evaluation
        "evaluate", "conclude", "judge", "assess", "critique",
        "argue", "justify", "validate", "prove", "support",
        # Synthesis
        "create", "design", "develop", "propose", "formulate",
        "construct", "integrate", "generalize", "hypothesize",
        # Contrasting
        "however", "although", "whereas", "nevertheless", "on the other hand",
        "in contrast", "despite", "while", "yet", "but",
        # Questioning
        "why", "how", "what if", "what causes", "what would happen",
        # Conclusion
        "in conclusion", "to summarize", "in summary", "overall"
    ]
    
    # Emotional indicators
    EMOTIONAL_INDICATORS = [
        # Positive
        "senang", "tertarik", "semangat", "excited", "interesting",
        "menarik", "bagus", "mantap", "keren",
        # Negative
        "bingung", "sulit", "susah", "frustasi", "tidak mengerti",
        "confused", "difficult", "hard"
    ]
    
    # Indonesian stopwords (common words to exclude from lexical analysis)
    STOPWORDS_ID = {
        "yang", "dan", "di", "ke", "dari", "ini", "itu", "untuk",
        "dengan", "pada", "adalah", "juga", "tidak", "sudah",
        "akan", "bisa", "ada", "atau", "saya", "kami", "kita",
        "mereka", "dia", "nya", "tersebut", "dalam", "oleh",
        "sebagai", "dapat", "lebih", "sama", "saat", "hanya",
        "seperti", "jika", "apa", "siapa", "mana", "kapan"
    }
    
    # Common educational objects/topics for SRL tracking (Indonesian)
    SRL_OBJECT_KEYWORDS = [
        "database", "redis", "caching", "sql", "postgresql", "mongodb",
        "api", "fastapi", "rest", "endpoint", "frontend", "backend",
        "react", "vue", "angular", "javascript", "python", "java",
        "algorithm", "complexity", "big o", "sort", "search",
        "design pattern", "singleton", "factory", "observer",
        "test", "unit test", "integration", "deployment", "docker",
        "kubernetes", "cloud", "aws", "azure", "gcp"
    ]

    def __init__(self):
        """Initialize the engagement analyzer."""
        self.hot_triggers = set(self.HOT_TRIGGERS_ID + self.HOT_TRIGGERS_EN)
        self.emotional_words = set(self.EMOTIONAL_INDICATORS)
        self.srl_keywords = set(self.SRL_OBJECT_KEYWORDS)
        logger.info("engagement_analyzer_initialized")

    def extract_srl_object(self, text: str, default: str = "General_Discussion") -> str:
        """
        Extract the primary learning object from the text.
        
        Simple heuristic: check for technical keywords.
        """
        text_lower = text.lower()
        found = []
        for keyword in self.SRL_OBJECT_KEYWORDS:
            if keyword in text_lower:
                found.append(keyword.capitalize())
        
        if found:
            # Return the first 2 objects found
            return ", ".join(found[:2])
        
        # Fallback: extract capitalized words that aren't at the start (simple proper noun heuristic)
        # Or just return default
        return default
    
    def analyze_interaction(self, text: str) -> EngagementAnalysis:
        """
        Analyze a single text interaction for engagement metrics.
        
        Args:
            text: The text to analyze (message, post, etc.)
            
        Returns:
            EngagementAnalysis with all computed metrics
        """
        # Normalize text first
        text = normalize_text(text)
        
        if not text or not text.strip():
            return EngagementAnalysis(
                lexical_variety=0.0,
                engagement_type=EngagementType.BEHAVIORAL,
                is_higher_order=False,
                hot_indicators=[],
                word_count=0,
                unique_words=0,
                confidence=0.0
            )
        
        text_lower = text.lower()
        
        # Tokenize and clean for Lexical Variety
        ttr_clean_text = clean_for_ttr(text)
        words_for_lexical = self._tokenize(ttr_clean_text)
        
        # Original tokenization for word count
        words = self._tokenize(text_lower)
        word_count = len(words)
        
        # Filter stopwords for lexical analysis
        meaningful_words = [w for w in words_for_lexical if w not in self.STOPWORDS_ID and len(w) > 1]
        unique_words = len(set(meaningful_words))
        
        # 1. Calculate Lexical Variety (Type-Token Ratio)
        lexical_variety = self._calculate_lexical_variety(meaningful_words)
        
        # 2. Detect Higher-Order Thinking
        hot_indicators = self._detect_hot_indicators(text_lower)
        is_higher_order = len(hot_indicators) > 0
        
        # 3. Classify Engagement Type
        engagement_type = self._classify_engagement(
            text_lower, is_higher_order, hot_indicators
        )
        
        # 4. Calculate confidence
        confidence = self._calculate_confidence(word_count, unique_words, is_higher_order)
        
        logger.debug(
            "engagement_analyzed",
            lexical_variety=round(lexical_variety, 2),
            engagement_type=engagement_type.value,
            is_hot=is_higher_order,
            word_count=word_count
        )
        
        return EngagementAnalysis(
            lexical_variety=round(lexical_variety, 3),
            engagement_type=engagement_type,
            is_higher_order=is_higher_order,
            hot_indicators=hot_indicators,
            word_count=word_count,
            unique_words=unique_words,
            confidence=round(confidence, 2)
        )
    
    def analyze_batch(self, texts: List[str]) -> Dict[str, Any]:
        """
        Analyze multiple texts and return aggregated metrics.
        
        Args:
            texts: List of texts to analyze
            
        Returns:
            Aggregated analysis results
        """
        if not texts:
            return {
                "count": 0,
                "avg_lexical_variety": 0.0,
                "hot_percentage": 0.0,
                "engagement_distribution": {},
                "analyses": []
            }
        
        analyses = [self.analyze_interaction(text) for text in texts]
        
        # Aggregate metrics
        avg_lexical = sum(a.lexical_variety for a in analyses) / len(analyses)
        hot_count = sum(1 for a in analyses if a.is_higher_order)
        hot_percentage = (hot_count / len(analyses)) * 100
        
        # Engagement distribution
        engagement_dist = {}
        for a in analyses:
            key = a.engagement_type.value
            engagement_dist[key] = engagement_dist.get(key, 0) + 1
        
        return {
            "count": len(texts),
            "avg_lexical_variety": round(avg_lexical, 3),
            "hot_percentage": round(hot_percentage, 1),
            "engagement_distribution": engagement_dist,
            "analyses": [self._to_dict(a) for a in analyses]
        }
    
    def get_discussion_quality_score(self, texts: List[str]) -> Dict[str, Any]:
        """Expert calculation of discussion quality with SSRL weights."""
        if not texts:
            return {"quality_score": 0.0, "lexical_score": 0.0, "hot_score": 0.0, "cognitive_ratio": 0.0, "recommendation": "Belum ada data diskusi."}
            
        b = self.analyze_batch(texts)
        
        # Weighted metric (30% Lexical, 40% HOT, 30% Cognitive Engagement)
        lex_score = min(b["avg_lexical_variety"] * 100, 100)
        hot_score = b["hot_percentage"]
        cog_ratio = (b["engagement_distribution"].get("cognitive", 0) / b["count"]) * 100
        
        q_score = (lex_score * 0.3) + (hot_score * 0.4) + (cog_ratio * 0.3)
        
        return {
            "quality_score": round(q_score, 1),
            "lexical_score": round(lex_score, 1),
            "hot_score": round(hot_score, 1),
            "cognitive_ratio": round(cog_ratio, 1),
            "recommendation": self._get_quality_recommendation(q_score)
        }
    
    def _tokenize(self, text: str) -> List[str]:
        """Tokenize text into words."""
        # Remove punctuation and split
        cleaned = re.sub(r'[^\w\s]', ' ', text)
        return [w for w in cleaned.split() if w]
    
    def _calculate_lexical_variety(self, words: List[str]) -> float:
        """
        Calculate Type-Token Ratio (TTR) as lexical variety metric.
        
        Higher TTR = richer vocabulary = better discussion quality.
        """
        if not words:
            return 0.0
        
        unique = len(set(words))
        total = len(words)
        
        # Use root TTR for longer texts to normalize
        if total > 50:
            return unique / (total ** 0.5)
        
        return unique / total
    
    def _detect_hot_indicators(self, text: str) -> List[str]:
        """Detect Higher-Order Thinking indicators in text."""
        found = []
        for trigger in self.hot_triggers:
            if trigger in text:
                found.append(trigger)
        return found[:5]  # Limit to top 5 indicators
    
    def _classify_engagement(
        self, 
        text: str, 
        is_hot: bool,
        hot_indicators: List[str]
    ) -> EngagementType:
        """
        Classify the engagement type of the text.
        
        Based on research framework:
        - Cognitive: Analysis, evaluation, critical thinking
        - Behavioral: Task completion, participation
        - Emotional: Feelings, motivation
        """
        # Check for emotional indicators first
        emotional_count = sum(1 for word in self.emotional_words if word in text)
        
        if emotional_count >= 1: # Reduced from 2 for better detection in short text
            return EngagementType.EMOTIONAL
        
        # Cognitive if HOT detected
        if is_hot or len(hot_indicators) > 0:
            return EngagementType.COGNITIVE
        
        # Default to behavioral (participation)
        return EngagementType.BEHAVIORAL
    
    def _calculate_confidence(
        self, 
        word_count: int, 
        unique_words: int,
        is_hot: bool
    ) -> float:
        """Calculate confidence in the analysis."""
        if word_count <= 5: # <= instead of <
            return 0.3
        if word_count <= 15:
            return 0.5
        if word_count <= 50:
            return 0.7
        return 0.9
    
    def _get_quality_recommendation(self, score: float) -> str:
        """Get recommendation based on quality score."""
        if score >= 70:
            return "Diskusi berkualitas tinggi - pertahankan!"
        if score >= 50:
            return "Diskusi cukup baik - coba ajukan pertanyaan 'mengapa' untuk tingkatkan"
        if score >= 30:
            return "Diskusi perlu ditingkatkan - dorong analisis dan evaluasi"
        return "Diskusi dangkal - intervensi diperlukan untuk pemikiran kritis"
    
    def _to_dict(self, analysis: EngagementAnalysis) -> Dict[str, Any]:
        """Convert EngagementAnalysis to dictionary."""
        return {
            "lexical_variety": analysis.lexical_variety,
            "engagement_type": analysis.engagement_type.value,
            "is_higher_order": analysis.is_higher_order,
            "hot_indicators": analysis.hot_indicators,
            "word_count": analysis.word_count,
            "unique_words": analysis.unique_words,
            "confidence": analysis.confidence
        }


# Singleton instance
_analyzer: Optional[EngagementAnalyzer] = None


def get_engagement_analyzer() -> EngagementAnalyzer:
    """Get or create the engagement analyzer singleton."""
    global _analyzer
    if _analyzer is None:
        _analyzer = EngagementAnalyzer()
    return _analyzer
