from ..ppln import Component, Pipeline


@Pipeline.register_component(
    assigns="extract_file_name",
    depends=[],
    requires=[],
)
class AddFileName(Component):
    class Config:
        make_lower_case: bool = False

    def __call__(self, file):
        file.add_extract_field("extract_file_name", field_type=str)
        file.extract_file_name = file.get_file_name()
        return file
