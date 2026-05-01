import math

from app.services.logic_listener import LogicListener


class TestGiniNormalization:
    def setup_method(self):
        self.listener = LogicListener()

    def test_gini_normalized_by_group_size(self):
        distribution = {"user_a": 10, "user_b": 1, "user_c": 1}

        raw_gini = self.listener._calculate_gini_coefficient(list(distribution.values()))
        normalized_gini = self.listener._calculate_normalized_gini(distribution)

        expected_normalized = raw_gini * math.sqrt(len(distribution))

        assert abs(normalized_gini - expected_normalized) < 0.01

    def test_cold_start_protection(self):
        distribution = {"user_a": 4, "user_b": 1}

        should_intervene = self.listener._should_intervene_participation(distribution, total_messages=5)

        assert should_intervene is False

    def test_intervention_triggers_above_threshold(self):
        distribution = {"user_a": 15, "user_b": 1, "user_c": 1, "user_d": 1}
        total = sum(distribution.values())

        should_intervene = self.listener._should_intervene_participation(distribution, total_messages=total)

        assert should_intervene is True
        assert total > 10

    def test_equal_participation_no_intervention(self):
        distribution = {"user_a": 5, "user_b": 5, "user_c": 5, "user_d": 5}
        total = sum(distribution.values())

        should_intervene = self.listener._should_intervene_participation(distribution, total_messages=total)

        assert should_intervene is False
