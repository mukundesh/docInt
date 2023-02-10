import difflib  # noqa F401
import json
import sys
from math import isclose
from pathlib import Path

from docint import pdfwrapper

# pdfplumber run times
# Fri Oct 14 15:01:10 IST 2022
# Fri Oct 14 15:19:13 IST 2022

# pydfium2 run times
# Fri Oct 14 15:28:23 IST 2022
# Fri Oct 14 15:29:03 IST 2022


def test_info_directory(library_name, directory):
    actual_infos = []
    for pdf_path in directory.glob("*.pdf"):
        print(pdf_path.name)
        pdf = pdfwrapper.open(pdf_path, library_name=library_name)
        actual_infos.append((pdf_path.name, pdf.get_info()))
    actual_infos.sort()
    actual_infos = dict(actual_infos)
    return actual_infos


PDF_DIRS = [
    ("cabsec", "/Users/mukund/Orgpedia/cabsec2/flow/doOCR_/input"),
    ("rajpol", "/Users/mukund/Orgpedia/rajpol/flow/analyzeInput_/input"),
    #    ('rajpol-text', '/Users/mukund/Orgpedia/rajpol/flow/R.P.S/text/readPDF_/input'),
]


REL_TOL = 1e-5


def float_eq(a, b):
    if isinstance(a, (list, tuple)) and isinstance(b, (list, tuple)):
        return len(a) == len(b) and all(
            isclose(a1, b1, rel_tol=REL_TOL, abs_tol=REL_TOL) for (a1, b1) in zip(a, b)
        )
    else:
        return isclose(a, b, rel_tol=REL_TOL)


def check(val1, val2, path, field):
    if not float_eq(val1, val2):
        print(f"Mismatch: {path}>{field} {val1} {val2}")


def cmp(pdf_name, info1, info2):
    for idx, (p1, p2) in enumerate(zip(info1["page_infos"], info2["page_infos"])):
        p_path = f"{pdf_name}:pa{idx}"
        [
            check(p1[f], p2[f], p_path, f)
            for f in [
                "width",
                "height",
                "num_words",
                "num_images",
                "has_one_large_image",
            ]
        ]
        for idx, (i1, i2) in enumerate(zip(p1["image_infos"], p2["image_infos"])):
            i_path = f"{p_path}.im{idx}"
            [check(i1[f], i2[f], i_path, f) for f in ["width", "height", "bounding_box"]]


if len(sys.argv) > 2:
    ## Compare the info files and find the difference
    info1_path = Path(sys.argv[1])
    info2_path = Path(sys.argv[2])

    info1_dict, info2_dict = json.loads(info1_path.read_text()), json.loads(info2_path.read_text())

    for pdf_name in info1_dict.keys():
        cmp(pdf_name, info1_dict[pdf_name], info2_dict[pdf_name])

elif len(sys.argv) > 1:
    # compare an individual pdf file across different libraries

    pdf_path = Path(sys.argv[1])
    pdf1 = pdfwrapper.open(pdf_path, library_name="pdfplumber")
    pdf2 = pdfwrapper.open(pdf_path, library_name="pypdfium2")

    for page1, page2 in zip(pdf1.pages, pdf2.pages):
        print(f"#Words: {len(page1.words)} {len(page2.words)}")
        print(
            f"#Word Lengths: {sum([len(w.text) for w in page1.words])} {sum([len(w.text) for w in page2.words])}"
        )

    # This is expensive operation aligns the sequences of strs
    # a = ' '.join(w.text for w in page1.words)
    # b = ' '.join(w.text for w in page2.words)
    # s = difflib.SequenceMatcher(None, a, b)
    # for tag, i1, i2, j1, j2 in s.get_opcodes():
    #     print('{:7}   a[{}:{}] --> b[{}:{}] {!r:>8} --> {!r}'.format(tag, i1, i2, j1, j2, a[i1:i2], b[j1:j2]))
    # for w1, w2 in zip(page1.words, page2.words):
    #     print(f'    {w1.text}|{w2.text}')
    # print('')
else:
    # generate the info files.

    for (name, pdf_dir) in PDF_DIRS:
        pdf_infos = test_info_directory("pypdfium2", Path(pdf_dir))
        Path(f"{name}.info.json").write_text(json.dumps(pdf_infos))
