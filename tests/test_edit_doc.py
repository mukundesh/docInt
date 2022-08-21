import pytest


def test_wrong_command(one_word_doc):
    doc = one_word_doc
    with pytest.raises(Exception) as e:
        doc.edit(["replaceSt pa0.wo0 One Two"], file_path="stdin", line_nums=[1])
    assert e.type == ValueError
    assert str(e.value) == "stdin:1: No function replaceSt found in doc."


def test_check_path(one_word_doc):
    doc = one_word_doc
    with pytest.raises(Exception) as e:
        doc.edit(["replaceStr 2 <all> One"], file_path="stdin", line_nums=[1])
    assert e.type == ValueError
    # assert str(e.value) == ""


def test_replaceStr(one_word_doc):
    doc = one_word_doc
    edit_args_exp = [("One Two", "Two"), ("<all> One", "One"), ("O T", "Tne")]
    for (args, exp) in edit_args_exp:
        edits = [f"replaceStr pa0.wo0 {args}"]
        doc.edit(edits)
        assert doc[0][0].text == exp

    with pytest.raises(Exception) as e:
        doc.edit(["replaceStr pa0.wo0 <all>"], file_path="stdin", line_nums=[1])
    assert e.type == TypeError
    # -58 is needed for py310 as the format has changed
    assert str(e.value)[-58:] == "replaceStr() missing 1 required positional argument: 'new'"


def test_new_word(two_lines_doc):
    doc = two_lines_doc

    assert len(doc[0].words) == 13

    edits = ["newWord NEW pa0.wo6 pa0.wo12"]
    doc.edit(edits)
    assert doc[0][-1].text == "NEW"

    rt_region = doc.pages[0].words_to("right", doc[0][-2])
    assert rt_region.words[0].text == "NEW"
