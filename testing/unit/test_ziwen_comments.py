from models.komando import Komando, action_count_for_statistics


def test_lookup_cjk_counts_each_payload_item() -> None:
    komando = Komando(
        "lookup_cjk",
        data=[("zh", "注水", False), ("zh", "質疑", False)],
    )

    assert action_count_for_statistics(komando) == 2


def test_lookup_wp_counts_each_payload_item() -> None:
    komando = Komando(
        "lookup_wp",
        data=[("紫禁城", "zh"), ("Eiffel Tower", None)],
    )

    assert action_count_for_statistics(komando) == 2


def test_lookup_wt_counts_each_payload_item() -> None:
    komando = Komando(
        "lookup_wt",
        data=[("eo", "kunulo", True), ("eo", "amiko", True)],
    )

    assert action_count_for_statistics(komando) == 2


def test_non_lookup_command_counts_as_one_action() -> None:
    komando = Komando("identify", data=["zh", "ja"])

    assert action_count_for_statistics(komando) == 1
