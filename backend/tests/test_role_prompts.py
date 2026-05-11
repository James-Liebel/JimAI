from config import role_prompts


def test_house_preamble_present_in_all_roles():
    for name in (
        "JUDGE", "RESEARCH", "SYNTHESIZE", "WRITING_BASE",
        "SELF_IMPROVE_GENERATOR", "SELF_IMPROVE_CRITIC", "SELF_IMPROVE_STRENGTHEN",
        "SELF_IMPROVE_ARCHITECT", "SELF_IMPROVE_CODER", "SELF_IMPROVE_VERIFIER",
    ):
        body = getattr(role_prompts, name)
        assert isinstance(body, str) and len(body) > 200, f"{name} too short"
        assert role_prompts.HOUSE_PREAMBLE.split("\n", 1)[0] in body, f"{name} missing preamble"


def test_judge_prompt_specifies_json_schema():
    assert '"verdict"' in role_prompts.JUDGE
    assert '"scores"' in role_prompts.JUDGE


def test_self_improve_generator_specifies_candidate_schema():
    assert '"candidates"' in role_prompts.SELF_IMPROVE_GENERATOR
    assert '"acceptance"' in role_prompts.SELF_IMPROVE_GENERATOR


def test_critic_demands_overall_and_verdict():
    assert '"overall"' in role_prompts.SELF_IMPROVE_CRITIC
    assert '"verdict"' in role_prompts.SELF_IMPROVE_CRITIC


def test_classify_failure_table():
    cases = {
        "Read timed out after 30s": "timeout",
        "json.decoder.JSONDecodeError: Expecting value": "parse",
        "permission denied for tool shell": "tool",
        "AssertionError: expected 5 got 3": "assertion",
        "uncategorized weirdness": "unknown",
    }
    for text, expected in cases.items():
        assert role_prompts.classify_failure(text) == expected, f"{text!r} -> {expected}"


def test_recovery_suggestions_for_each_class_returns_three():
    for err in ("timed out", "json parse error", "tool failed", "assertion", "other"):
        sugg = role_prompts.recovery_suggestions_for(err)
        assert len(sugg) == 3
        assert all(isinstance(s, str) and s for s in sugg)
