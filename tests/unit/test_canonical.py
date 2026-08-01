from requirements_quality_agent.controls.canonical import (
    canonical_json,
    canonical_text,
    domain_digest,
)


def test_canonical_text_normalizes_transport_only() -> None:
    assert canonical_text("\ufeffcafe\u0301\r\nnext") == "caf\u00e9\nnext"


def test_canonical_json_sorts_mapping_keys() -> None:
    assert canonical_json({"b": 2, "a": 1}) == b'{"a":1,"b":2}'


def test_domain_digest_is_order_stable_and_domain_separated() -> None:
    left = domain_digest("review-artifact", {"b": 2, "a": 1})
    right = domain_digest("review-artifact", {"a": 1, "b": 2})
    other = domain_digest("approval-submission", {"a": 1, "b": 2})
    assert left == right
    assert left != other
