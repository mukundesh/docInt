from ..ppln import Component, Pipeline


@Pipeline.register_component(
    assigns="extract_file_name",
    depends=[],
    requires=[],
)
class AddFileName(Component):
    class Config:
        make_upper_case: bool = False

    def __call__(self, file, cfg):
        # file.add_extract_field("extract_file_name", field_type=str)
        # file.extract_file_name = file.get_file_name()
        if cfg.make_upper_case:
            print("MAKING UPPER CASE")
            file.extract_file_name = file.file_name.upper()
        else:
            file.extract_file_name = file.file_name
        return file
