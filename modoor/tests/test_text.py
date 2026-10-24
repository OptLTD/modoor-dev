from modoor.support import flag, seqno, text, texts


def test_text_blank_falsy_and_strip():
    assert text(None) == ""
    assert text("") == ""
    assert text(0) == ""
    assert text(False) == ""
    assert text(" fleet ") == " fleet "
    assert text(" fleet ", strip=True) == "fleet"
    assert text(12) == "12"


def test_texts_skips_blank_and_can_dedupe():
    assert texts(None) == []
    assert texts(" bulk ") == ["bulk"]
    assert texts([" a ", "", "a", "b"], unique=True) == ["a", "b"]


def test_flag_reads_yaml_switches():
    assert flag(None) is False
    assert flag(True) is True
    assert flag(0) is False
    assert flag(" YES ") is True
    assert flag("no") is False


def test_seqno_keeps_zero_and_rejects_junk():
    assert seqno(None, 100) == 100
    assert seqno("", 100) == 100
    assert seqno(0, 100) == 0
    assert seqno("12", 100) == 12
    assert seqno("x", 100) == 100
