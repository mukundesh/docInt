from importlib import import_module

_PDFImpl = None


def set_library(library_name: str):
    global _PDFImpl
    _PDFImpl = load_impl(library_name)


def open(pdf_path, *, password=None, library_name="pypdfium2"):
    set_library(library_name)

    if password:
        return _PDFImpl.open(pdf_path, password)
    else:
        return _PDFImpl.open(pdf_path, password=None)


def load_impl(library_name):
    return import_module(f"docint.pdfwrapper.{library_name}_wrapper")
