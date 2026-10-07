from modoor.engine.query import QueryTerm, match_term_value, parse_query


def test_parse_group_or_marks_terms():
    terms = parse_query(
        {
            "GROUP:OR": {
                "expires.inspection:FTR": "FUTURE_1_MONTH",
                "expires.license:FTR": "FUTURE_1_MONTH",
            }
        }
    )
    assert len(terms) == 2
    assert all(t.group == "or" for t in terms)
    assert all(t.op == "BTW" for t in terms)
    assert {t.field for t in terms} == {"expires.inspection", "expires.license"}


def test_parse_plain_and_has_empty_group():
    terms = parse_query({"basic.plate:EQ": "苏A"})
    assert len(terms) == 1
    assert terms[0].group == ""
    assert terms[0].op == "EQ"


def test_parse_named_or_groups_stay_separate():
    terms = parse_query(
        {
            "GROUP:OR:performance": {
                "basic.performance:EQ": 0,
                "basic.performance:NIL": True,
            },
            "GROUP:OR:total": {
                "extra.total:EQ": 0,
                "extra.total:NIL": True,
            },
        }
    )
    assert {t.group for t in terms} == {"or:performance", "or:total"}
    assert {t.field for t in terms if t.group == "or:performance"} == {"basic.performance"}
    assert {t.field for t in terms if t.group == "or:total"} == {"extra.total"}


def test_in_matches_any_item_of_a_list():
    term = QueryTerm(field="basic.tags", op="IN", value=["night", "cold"])
    assert match_term_value(["night"], term)
    assert match_term_value(["special", "cold"], term)
    assert not match_term_value(["special"], term)
    assert not match_term_value([], term)
    assert match_term_value("night", term)
