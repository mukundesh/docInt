import pytest  # noqa

import docint

docker_config = {
    "post_install_lines": [
        "ENV GOOGLE_APPLICATION_CREDENTIALS /usr/src/app/task_/.secrets/google.token"
    ],
    "delete_container_dir": True,
}


def get_line(page, line_idx):
    return " ".join(page[idx].text for idx in page.arranged_word_lines_idxs[line_idx])


def test_words_arranger(table_rota_path):
    ppln = docint.empty(
        config={
            "docker_pipes": ["gcv_recognizer", "rotation_detector"],
            "docker_config": docker_config,
        }
    )
    # ppln = docint.empty()
    ppln.add_pipe("gcv_recognizer", pipe_config={"bucket": "orgfound"})
    ppln.add_pipe("page_image_builder_raster")
    ppln.add_pipe("num_marker")
    ppln.add_pipe("rotation_detector")
    ppln.add_pipe("words_arranger", pipe_config={"rotate_page": True})

    doc = ppln(table_rota_path)

    assert get_line(doc[0], 3) == "Number Planet Satellites Distance"
    assert get_line(doc[0], 9) == "3 Earth 1 1.0 AU"
    assert get_line(doc[0], 19) == "8 Neptune 14 30.0 AU"

    # for idx, line_idxs in enumerate(doc[0].arranged_word_lines_idxs):
    #     print(idx, ' '.join(doc[0][idx].text for idx in line_idxs))
