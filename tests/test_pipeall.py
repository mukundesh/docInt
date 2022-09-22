import docint


def test_learn_layout(layout_paths):
    ppl = docint.empty()
    ppl.add_pipe('pdf_reader')
    ppl.add_pipe('do_nothing_pipe')

    docs = ppl.pipe_all(layout_paths)
    docs = list(docs)
