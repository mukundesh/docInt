import docint

WORD_MAPPING = {
    "Á": "A",
    "jumpèd": "jumped",
    "fóx.": "fox.",
}


def test_ascii_normalizer(unicode_path):
    ppln = docint.empty()
    pipe_config = {
        "script": "ascii",
        "script_mapping": WORD_MAPPING,
    }

    ppln.add_pipe("pdf_reader")
    ppln.add_pipe("script_normalizer", pipe_config=pipe_config)
    doc = ppln(unicode_path)

    print(doc[0].text)

    # doc[0].text == 'A quick brown fox jumped over the lazy fox'


def test_ascii_normalizer_errors(unicode_path):
    ppln = docint.empty()
    pipe_config = {
        "script": "ascii",
        "script_mapping": {},
    }

    ppln.add_pipe("pdf_reader")
    ppln.add_pipe("script_normalizer", pipe_config=pipe_config)
    doc = ppln(unicode_path)

    print(doc[0].text)

    # doc[0].text == 'A quick brown fox jumped over the lazy fox'
