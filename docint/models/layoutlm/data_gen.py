import json

from PIL import Image


def get_layoutlm_json(doc, page_idx):
    page = doc[page_idx]
    newWh, newHt = int((page.width * 1000.0) / page.height), 1000

    def flatten_box(box):
        top, bot = box.top, box.bot
        return [top.x * newWh, top.y * newHt, bot.x * newWh, bot.y * newHt]

    def build_word(word):
        return {"text": word.text, "box": flatten_box(word.box)}

    start_idx, entities = 0, []
    for label, region in doc[page_idx].layoutlm:
        entity = {
            "id": start_idx,
            "text": region.line_text,
            "box": flatten_box(region.shape),
            "label": label,
            "linking": [],
            "words": [],
        }

        entity["words"] = [build_word(w) for w in region.iter_words()]
        entities.append(entity)

    layout_dict = {"form": entities}
    return json.dumps(layout_dict)


def write_layoutlm_image(doc, page_idx, image_path):
    page = doc.pages[page_idx]
    newWh, newHt = int((page.width * 1000.0) / page.height), 1000

    # page_image = doc.page_images[page_idx]
    img = Image.open(doc.get_image_path(page_idx))
    img = img.resize((newWh, newHt), Image.ANTIALIAS)
    img.save(image_path)
