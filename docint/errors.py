import warnings  # noqa: F401


class Warnings:
    W001 = "Spans start/end in SPACE span_str: {span_str}"


class Errors:
    E001 = "Unable to read the file at {path}."
    E002 = (
        "Can't write to frozen dictionary. This is likely an internal "
        "error. Are you writing to a default function argument?"
    )
    E003 = (
        "Can't write to frozen list. This is likely an internal "
        "error. Are you writing to a default function argument?"
    )
    E004 = "'{name}' already exists in pipeline. Existing names: {opts}"
    E005 = "Factory '{factory_name}' does not exist in names: {opts}"
    E006 = (
        "Invalid constraints for adding pipeline component. You can only "
        "set one of the following: before (component name or index), "
        "after (component name or index), first (True) or last (True). "
        "Invalid configuration: {args}. Existing components: {opts}"
    )
    E007 = "No component '{name}' found in pipeline. Available names: {opts}"
    E008 = "Can't insert component {dir} index {idx}. Existing components: {opts}"
    E009 = (
        "Can't restore disabled pipeline component '{name}' because it "
        "doesn't exist in the pipeline anymore. If you want to remove "
        "components from the pipeline, you should do it before calling "
        "`viz.select_pipes` or after restoring the disabled components."
    )

    E020 = "{line_num}: No function {function} found in doc."

    E030 = "docker build timeout expired, check: {image_dir}"
    E031 = "docker build failed with exit code: {exit_code} check: {image_dir}"
    E032 = "docker build failed multiple docker images given: {images}"
    E033 = "docker pip --version failed with exit code: {exit_code}"
    E034 = "docker pip --dry-run failed {image_dir} error: {err_str}"
    E035 = "docker run failed check: {log_path} exit_code:{exit_code} err_str: {err_str}"
    E109 = "task name: {name} failed with keyError and {error_str}"
