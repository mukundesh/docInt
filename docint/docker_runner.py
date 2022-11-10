import os
import shutil
from pathlib import Path
from subprocess import TimeoutExpired, run
from types import GeneratorType  # TODO: move this to iterable

import yaml
from more_itertools import first

from .doc import Doc
from .errors import Errors
from .util import get_uniq_str, tail

PYTHON_VERSION = "3.7-slim"
WORK_DIR = Path("/usr/src/app")
REPORT_LAST_LINES_COUNT = 3
DEFAULT_OS_PACKAGES = []  # "libmagickwand-dev"]
DEFAULT_PY_PACKAGES = [  # move this to docint
    "PyYaml",
    "more-itertools",
    "polyleven",
    "pydantic",
    "Pillow",
    "python-dateutil",
    "pypdfium2",
    # "wand", # temporary TODO
]

# TODO: define docker_options
# class DockerConfig(BaseModel):
#     python_version: ConSoftwareVersion(min='3.7', max='4.0') = '3.7'
#     pre_install_lines: List[str] = []
#     post_intall_lines: List[str] = []
#

# Directory Layout:

#     do_nothing-6slz67                     # image_dir - name of the image
#     |-- Dockerfile                        # both Dockerfile and reqs.txt are compared
#     |-- reqs.txt                          # to identify image_dir
#     |-- task_-e4db                        # directory mounted per run of container
#     |   |-- conf                          # deleted after running, dir name = name
#     |   |-- docint
#     |   |-- input
#     |   |   `-- one_line.pdf.doc.json
#     |   |-- logs
#     |   |-- output
#     |   |   |-- one_line.pdf.doc.json
#     |   |   `-- pipe.log
#     |   `-- src
#     |       |-- cmd.py
#     |       `-- pipeline.yml
#     `-- task_-mwv2                        # one directory per container run
#         |-- conf
#         ....


class DockerRunner:
    def __init__(self, docker_dir):
        self.docker_dir = docker_dir
        self.docint_dir = "/Users/mukund/Software/swap_pdf/docint"  # TODO: remove this

    def generate_dockerfile(self, depends, docker_config):
        def is_python_package(d):
            return not d.startswith("apt:") and not d.startswith("docker:")

        docker_depends = [d for d in depends if d.startswith("docker:")]
        if len(docker_depends) > 1:
            raise ValueError(Errors.E032, images=",".join(docker_depends))

        has_git_dependency = any("git+http" in d for d in depends)

        if docker_depends:
            docker_image = docker_depends[0][len("docker:") :]
            docker_lines = [f"FROM {docker_image}"]
        else:
            py_version = docker_config.get("python_version", PYTHON_VERSION)
            py_version = py_version.replace("-slim", "") if has_git_dependency else py_version
            docker_lines = [f"FROM python:{py_version}"]

        docker_lines.append("WORKDIR /usr/src/app")

        docker_lines.extend(docker_config.get("pre_install_lines", []))

        apt_depends = DEFAULT_OS_PACKAGES + [d[len("apt:") :] for d in depends if d.startswith("apt:")]
        if apt_depends:
            packages = " ".join(apt_depends)
            docker_lines.append(f"RUN apt-get update && apt-get install {packages} -y")

        py_depends = [d for d in depends if is_python_package(d)]

        reqs_txt = "\n".join(DEFAULT_PY_PACKAGES + py_depends)
        if reqs_txt:
            docker_lines.append("COPY reqs.txt /usr/src/app/")
            docker_lines.append("RUN pip install --no-cache-dir -r reqs.txt")

        docker_lines.extend(docker_config.get("post_install_lines", []))

        docker_lines.append("ENV PYTHONPATH .")
        docker_lines.append("WORKDIR /usr/src/app/task_")
        return "\n".join(docker_lines), reqs_txt

    def write_dockerfile(self, image_dir, dockerfile_str, reqs_str, docker_config):
        reqs_file = image_dir / "reqs.txt"
        reqs_file.write_text(reqs_str)

        completed_process = run(["pip", "--version"], capture_output=True, text=True)
        if completed_process.returncode != 0:
            exit_code = completed_process.returncode
            raise RuntimeError(Errors.E033.format(exit_code=exit_code))

        pip_version = completed_process.stdout.split(" ")[1]
        pip_major_version = int(pip_version.split(".")[0])
        if pip_major_version >= 22 and docker_config.get("do_dry_run", True):
            completed_process = run(
                ["pip", "install", "-r", str(reqs_file), "--dry-run"],
                capture_output=True,
                text=True,
            )
            if completed_process.returncode != 0:
                err_str = completed_process.stderr
                raise RuntimeError(Errors.E034.format(err_str=err_str, image_dir=image_dir))

        # TODO: raise a warning if dry run is not done

        dockerfile = image_dir / "Dockerfile"
        dockerfile.write_text(dockerfile_str)

    def get_image_info(self, name, dockerfile_str, reqs_str):
        def file_match(image_dir, dockerfile_str, reqs_str):
            if not image_dir.is_dir():
                return False

            dockerfile = image_dir / "Dockerfile"
            reqs_file = image_dir / "reqs.txt"
            image_reqs_str = reqs_file.read_text() if reqs_file.exists() else ""
            if dockerfile.exists():
                return dockerfile.read_text() == dockerfile_str and image_reqs_str == reqs_str
            else:
                return False

        def is_loaded(image_name):
            completed_process = run(["docker", "image", "inspect", "--format", " ", image_name])
            return completed_process.returncode == 0

        image_dirs = self.docker_dir.glob(f"{name}-*")
        image_dir = first((d for d in image_dirs if file_match(d, dockerfile_str, reqs_str)), None)

        if image_dir is None:
            return None, False, None  # image_name, image_loaded, image_dir

        image_name = image_dir.name
        image_loaded = is_loaded(image_name)
        return image_name, image_loaded, image_dir

    def build_image(self, name, depends, docker_config):
        dockerfile_str, reqs_str = self.generate_dockerfile(depends, docker_config)
        image_name, image_loaded, image_dir = self.get_image_info(name, dockerfile_str, reqs_str)

        # print(f'** image: {image_name} loaded: {image_loaded} image_dir: {image_dir}')
        if image_name is None:
            image_name = f"{name}-{get_uniq_str()}".lower()
            image_dir = self.docker_dir / image_name
            image_dir.mkdir()
            self.write_dockerfile(image_dir, dockerfile_str, reqs_str, docker_config)

        if not image_loaded:
            docker_cmds = ["docker", "build", "--tag", image_name, str(image_dir)]
            try:
                completed_process = run(docker_cmds, capture_output=True, text=True)
            except TimeoutExpired as e:
                raise RuntimeError(Errors.E030.format(image_dir=str(image_dir))) from e

            if completed_process.returncode != 0:
                (image_dir / "stderr.out").write_text(completed_process.stderr)
                (image_dir / "stdout.out").write_text(completed_process.stdout)
                exit_code = completed_process.returncode
                raise RuntimeError(Errors.E031.format(exit_code=exit_code, image_dir=str(image_dir)))

        return image_name, image_dir

    def cmd_src(self, ppln_path, input_paths, output_paths):
        assert len(input_paths) == len(output_paths)
        all_input_paths_str = ", ".join(f"'{str(p)}'" for p in input_paths)
        all_output_paths_str = ", ".join(f"'{str(p)}'" for p in output_paths)
        s = "import docint\n"
        s += 'if __name__ == "__main__":\n'
        s += f'    viz = docint.load("{str(ppln_path)}")\n'
        s += f"    docs = viz.pipe_all([{all_input_paths_str}])\n"
        s += f"    for doc, output_doc_str in zip(docs, [{all_output_paths_str}]):\n"
        s += "        doc.to_disk(output_doc_str)\n"
        return s

    def build_task_dir(self, image_dir, name, docs, is_recognizer, pipe_config, docker_config):
        task_dir = image_dir / f"task_-{get_uniq_str(4)}".lower()
        task_dir.mkdir()

        # TODO: 1. docint should be imported not mounted
        # TODO: 2. we should be mounting only 1 .docint cache directory
        sub_dirs = [
            "input",
            "output",
            "src",
            "conf",
            "logs",
            "docint",
            ".img",
            ".model",
        ]
        [(task_dir / d).mkdir() for d in sub_dirs]

        input_ctnr_paths, output_ctnr_paths = [], []
        for doc in docs:
            if is_recognizer:
                doc.copy_pdf(task_dir / Path("input") / f"{doc.pdf_name}")
                input_ctnr_paths.append(Path("input") / f"{doc.pdf_name}")
            else:
                doc.to_disk(task_dir / Path("input") / f"{doc.pdf_name}.doc.json")
                input_ctnr_paths.append(Path("input") / f"{doc.pdf_name}.doc.json")
            output_ctnr_paths.append(Path("output") / f"{doc.pdf_name}.doc.json")

        ppln_path = task_dir / Path("src") / "pipeline.yml"
        ppln_dict = {"pipeline": [{"name": name, "config": pipe_config}]}
        ppln_path.write_text(yaml.dump(ppln_dict))

        ppln_ctnr_path = Path("src") / "pipeline.yml"

        cmd_path = task_dir / Path("src") / "cmd.py"
        cmd_str = self.cmd_src(ppln_ctnr_path, input_ctnr_paths, output_ctnr_paths)
        cmd_path.write_text(cmd_str)
        return task_dir

    def get_mounts(self, task_dir, cache_dir, conf_dir, log_dir):
        task_ctnr_dir = WORK_DIR / "task_"
        mnts = []
        task_dir = task_dir.resolve()

        # TODO: can we not just mount task_ dir insted of multiple mounts

        mnts += ["-v", f"{str(task_dir / 'input')}:{str(task_ctnr_dir / 'input')}"]
        mnts += ["-v", f"{str(task_dir / 'output')}:{str(task_ctnr_dir / 'output')}"]
        mnts += ["-v", f"{str(task_dir / 'src')}:{str(task_ctnr_dir / 'src')}"]

        mnts += ["-v", f"{str(self.docint_dir)}:{str(task_ctnr_dir / 'docint')}"]

        mnts += ["-v", f"{str(cache_dir / '.model')}:{str(task_ctnr_dir / '.model')}"]
        mnts += ["-v", f"{str(cache_dir / '.img')}:{str(task_ctnr_dir / '.img')}"]
        mnts += [
            "-v",
            f"{str(cache_dir / '.secrets')}:{str(task_ctnr_dir / '.secrets')}",
        ]

        mnts += ["-v", f"{str(log_dir)}:{str(task_ctnr_dir / 'logs')}"]
        mnts += ["-v", f"{str(conf_dir)}:{str(task_ctnr_dir / 'conf')}"]
        return mnts

    def pipe(self, name, input_docs, depends, is_recognizer, pipe_config, *, docker_config={}):
        docs = list(input_docs) if isinstance(input_docs, (list, GeneratorType)) else [input_docs]
        image_name, image_dir = self.build_image(name, depends, docker_config)

        task_dir = self.build_task_dir(image_dir, name, docs, is_recognizer, pipe_config, docker_config)

        container_name = task_dir.name

        cache_dir = Path(os.getcwd())
        log_dir = cache_dir / "logs"
        conf_dir = cache_dir / "conf"

        docker_cmds = ["docker", "run"]
        docker_cmds += self.get_mounts(task_dir, cache_dir, conf_dir, log_dir)
        docker_cmds += ["--name", container_name]
        docker_cmds += [image_name]
        docker_cmds += ["/bin/sh", "-c", "python src/cmd.py > output/pipe.log 2>&1"]

        # print(docker_cmds)
        completed_process = run(docker_cmds)

        output_dir = task_dir / "output"
        if completed_process.returncode != 0:
            exit_code = completed_process.returncode
            log_path = output_dir / "pipe.log"
            last_lines = tail(log_path, 3) if log_path.exists() else "No file created"
            raise RuntimeError(Errors.E035.format(log_path=str(log_path), exit_code=exit_code, err_str=last_lines))

        output_paths = list(output_dir.glob("*.doc.json"))
        if len(output_paths) != len(docs):
            raise RuntimeError(Errors.E035.format(log_path=str(log_path), exit_code=exit_code, err_str=last_lines))

        # Reading output file and also updating doc.pdffile_path from input_doc
        output_docs = []
        for doc in docs:
            output_path = output_dir / f"{doc.pdf_name}.doc.json"
            output_doc = Doc.from_disk(output_path)
            output_doc.pdffile_path = Path(doc.pdffile_path)
            output_docs.append(output_doc)

        if docker_config.get("delete_container_dir", True):
            shutil.rmtree(task_dir)
        return output_docs if isinstance(input_docs, (list, GeneratorType)) else output_docs[0]


if __name__ == "__main__":
    runner = DockerRunner()
    runner.build_image("test", python_packages=["requests"], app_cmd="ls")
