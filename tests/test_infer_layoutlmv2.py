import docint


# @pytest.mark.skip("This takes a very long time")
def test_infer_layout(layout_paths):
    docker_config = {
        "pre_install_lines": ["RUN pip install transformers[torch]"],
        "post_install_lines": ["ENV PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION python"],
        "do_dry_run": False,
        "delete_container_dir": False,
    }

    ppl = docint.empty(config={"docker_pipes": ["infer_layoutlmv2"], "docker_config": docker_config})
    ppl.add_pipe("pdf_reader")
    ppl.add_pipe("page_image_builder_raster")
    pipe_config = {
        "infer_model_name": "test-layout",
        "model_dir": ".model",
        "batch_size": 5,
    }

    ppl.add_pipe("infer_layoutlmv2", pipe_config=pipe_config)
    docs = ppl.pipe_all(layout_paths)
    docs = list(docs)
