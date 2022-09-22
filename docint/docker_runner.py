import os
from pathlib import Path
from subprocess import call

# from more_itertools import partition

DEFAULT_REGISTRY = "https://ghcr.io"


class DockerRunner:
    def __init__(self, registry=DEFAULT_REGISTRY):
        self.registry = registry
        self.docker_dir = '.docker'
        self.docint_dir = '/Users/mukund/Software/docInt/docint'

    def write_and_check_requirements(self, temp_dir, req_file_name, python_packages):
        req_path = Path(temp_dir) / req_file_name
        req_path.write_text("\n".join(python_packages))

        # dry_run_path = Path(temp_dir) / 'dry_run.out'
        # dry_run_f = open(dry_run_path, 'w')

        # currently commenting as it is impossible to add torch to a list of requirements where git exists
        # status = call(["pip", "install", "-r", str(req_path), "--dry-run"], stdout=dry_run_f)
        # if status != 0:
        #     raise ValueError(f"Incorrect package description: {python_packages}")
        return req_path

    def write_dockerfile(self, temp_dir, packages, python_packages, app_cmd):
        def is_src_package(p):
            return "git" in p

        docker_lines = ["FROM python:3.7", "WORKDIR /usr/src/app"]

        # reg_packages, src_packages = partition(is_src_package, python_packages)
        # reg_packages, src_packages = list(reg_packages), list(src_packages)

        src_packages, reg_packages = [], python_packages

        print(f'** OS_PACKAGES: {packages}')
        for package in packages:
            docker_lines.append(f'RUN apt-get update && apt-get install {package} -y')

        docker_lines.append('RUN pip install transformers[torch]')

        if src_packages:
            self.write_and_check_requirements(temp_dir, "reqs1.txt", src_packages)
            docker_lines.append("COPY reqs1.txt ./")
            docker_lines.append("RUN pip install --no-cache-dir -r reqs1.txt")

        if reg_packages:
            self.write_and_check_requirements(temp_dir, "reqs2.txt", reg_packages)
            docker_lines.append("COPY reqs2.txt /usr/src/app/")
            docker_lines.append("RUN pip install --no-cache-dir -r reqs2.txt")

        docker_lines.append("COPY task_ /usr/src/app/task_")
        docker_lines.append("WORKDIR task_")
        docker_lines.append("ENV PYTHONPATH .")
        docker_lines.append("ENV PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION python")

        # docker_lines.append(f'CMD [ "pwd" ]')
        # docker_lines.append(f'CMD [ "ls", "-laR", "/usr/src/app/"]')
        # docker_lines.append(f'CMD [ "python", "{app_cmd}" ]')
        docker_lines.append(f'CMD ["/bin/sh", "-c", "python {app_cmd} > output/server.log 2>&1"]')
        # docker_lines.append(f'RUN python {app_cmd} > output/out.txt 2> output/err.txt')

        dockerfile_path = Path(temp_dir) / "Dockerfile"
        dockerfile_path.write_text("\n".join(docker_lines))
        print(f'Dockerfile: {str(dockerfile_path)}')
        return dockerfile_path

    def build_image(self, image_name, *, packages=[], python_packages=[], app_cmd, **kwargs):
        pipe_dir = Path(self.docker_dir) / image_name
        self.write_dockerfile(pipe_dir, packages, python_packages, app_cmd)

        docker_cmds = ["docker", "build", "--tag", image_name]
        docker_cmds.append(str(pipe_dir))

        print(" ".join(docker_cmds))
        call(docker_cmds)

    def run(self, image_name):
        docker_cmds = ["docker", "run"]
        pipe_dir = Path(self.docker_dir) / image_name

        self.host_output_dir = Path(os.getcwd()) / pipe_dir / Path('task_') / 'output'
        self.host_conf_dir = Path(os.getcwd()) / 'conf'
        self.host_img_dir = Path(os.getcwd()) / '.img'
        self.host_model_dir = Path(os.getcwd()) / '.model'

        self.guest_output_dir = '/usr/src/app/task_/output'
        self.guest_conf_dir = '/usr/src/app/task_/conf'
        self.guest_img_dir = '/usr/src/app/task_/.img'
        self.guest_model_dir = '/usr/src/app/task_/.model'
        self.guest_docint_dir = '/usr/src/app/task_/docint'

        docker_cmds += ["-v", f'{str(self.host_output_dir)}:{str(self.guest_output_dir)}']
        docker_cmds += ["-v", f'{str(self.host_conf_dir)}:{str(self.guest_conf_dir)}']
        docker_cmds += ["-v", f'{str(self.host_img_dir)}:{str(self.guest_img_dir)}']
        docker_cmds += ["-v", f'{str(self.host_model_dir)}:{str(self.guest_model_dir)}']
        docker_cmds += ["-v", f'{str(self.docint_dir)}:{str(self.guest_docint_dir)}']

        docker_cmds += [image_name]
        print(" ".join(docker_cmds))
        call(docker_cmds)
        return self.host_output_dir.glob('*.json')

    def run_cmd(self, image_name, cmd):
        pass

    def image_exists(self, image_name):
        pass


if __name__ == "__main__":
    runner = DockerRunner()
    runner.build_image("test", python_packages=["requests"], app_cmd="ls")
