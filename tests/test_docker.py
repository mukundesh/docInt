from pathlib import Path

import docint


def test_simple():
    simple_yml_path = Path('tests/docker_simple.yml')

    viz = docint.load(simple_yml_path)
    doc = viz("tests/one_line.pdf")
    print(len(doc.pages))
    assert len(doc.pages) == 1


def test_pipe_all(layout_paths):
    simple_yml_path = Path('tests/docker_simple.yml')
    viz = docint.load(simple_yml_path)
    docs = list(viz.pipe_all(layout_paths))
    assert len(docs) == len(layout_paths)


def test_pipe_all_pipe(layout_paths):
    simple_yml_path = Path('tests/docker_simple2.yml')
    viz = docint.load(simple_yml_path)
    docs = list(viz.pipe_all(layout_paths))
    assert len(docs) == len(layout_paths)
