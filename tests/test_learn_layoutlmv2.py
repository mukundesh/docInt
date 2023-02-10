import pytest

import docint
from docint.doc import Doc


@pytest.mark.skip(
    reason="need to implement this inside docker as datasets.py has lot of dependencies"
)
def test_learn_layout(layout_paths):
    docker_config = {
        "pre_install_lines": ["RUN pip install transformers[torch]"],
        "post_install_lines": ["ENV PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION python"],
        "do_dry_run": False,
    }

    ppl = docint.empty(
        config={"docker_pipes": ["learn_layoutlmv2"], "docker_config": docker_config}
    )
    ppl.add_pipe("pdf_reader")
    ppl.add_pipe("page_image_builder_raster")
    ppl.add_pipe("learn_layoutlmv2", pipe_config={"num_folds": 3})
    docs = ppl.pipe_all(layout_paths)
    docs = list(docs)


@pytest.mark.skip(
    reason="need to implement this inside docker as datasets.py has lot of dependencies"
)
def test_learn_layout_one_fold(layout_paths):
    docker_config = {
        "pre_install_lines": ["RUN pip install transformers[torch]"],
        "post_intall_lines": ["ENV PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION python"],
        "do_dry_run": False,
        "delete_container_dir": False,
    }

    docker_pipes = ["learn_layoutlmv2"]
    ppl = docint.empty(config={"docker_pipes": docker_pipes, "docker_config": docker_config})
    ppl.add_pipe("pdf_reader")
    ppl.add_pipe("page_image_builder_raster")
    ppl.add_pipe("learn_layoutlmv2", pipe_config={"num_folds": 1, "max_steps": 100})
    docs = ppl.pipe_all(layout_paths)
    docs = list(docs)


@pytest.mark.skip(reason="this test case was added to check the dict_list functionality")
def test_learn_layout_word_labels(layout_paths):
    ppl = docint.empty()
    ppl.add_pipe("pdf_reader")
    ppl.add_pipe("page_image_builder_raster")
    ppl.add_pipe("learn_layoutlmv2")

    docs = ppl.pipe_all(layout_paths)
    docs = list(docs)

    docs[0].to_disk("/tmp/doc.json")

    read_doc = Doc.from_disk("/tmp/doc.json")
    assert list(read_doc.pages[0].word_labels.keys()) == [
        "org_name",
        "address",
        "telephone",
        "email",
        "date",
        "to_name",
        "body",
        "person_name",
        "person_desig",
        "person_email",
    ]

    assert list(len(r.words) for r in read_doc.pages[0].word_labels["body"]) == [
        24,
        33,
        38,
        19,
    ]

    # for idx, word in enumerate(layout_docs[0][0].words):
    #     print(f'{word.word_idx}: {word.text} {layout_docs[1][0][idx].text} {layout_docs[2][0][idx].text} {layout_docs[3][0][idx].text} {layout_docs[4][0][idx].text}')
