import docint
import pathlib
from docint.vision import Vision
from docint.shape import Coord

if __name__ == '__main__':
    
    viz = docint.load('test_page_image.yml')
    doc = viz('hello.pdf')

    first_page = doc.pages[0]
    gst_word = first_page.words[44]
    gst_doc_coord = gst_word.coords[0]
    page_image = first_page.page_image

    print('\n> Test image coords')
    gst_img_coord = page_image.get_image_coord(gst_doc_coord)
    print(f'doc: {gst_doc_coord} img:{gst_img_coord}')
    assert gst_img_coord.x == 138.0 and gst_img_coord.y == 371.0

    doc_coord = page_image.get_doc_coord(gst_img_coord)
    print(f'doc:{doc_coord}')
    assert str(doc_coord) == '0.0541:0.1124'

    w, h = first_page.width, first_page.height
    top, bot = Coord(x=20/w, y=65/h), Coord(x=300/w, y=155/h)
    img_top = page_image.get_image_coord(top)

    print(f'\n>Test crop')
    print(f'\ttop: {top} img_top: {img_top}')
    page_image.crop(top, bot)    
    gst_img_coord = page_image.get_image_coord(gst_doc_coord)
    print(f'img:{gst_img_coord}')
    assert gst_img_coord.x == 55.0 and gst_img_coord.y == 100.0
    
    doc_coord = page_image.get_doc_coord(gst_img_coord)
    print(f'doc:{doc_coord}')
    assert str(doc_coord) == '0.0541:0.1124'
    page_image.clear_transforms()
    

    print(f'\n>Test rotate')    
    page_image.rotate(45)
    print('\tangle: 45')
    gst_img_coord = page_image.get_image_coord(gst_doc_coord)
    print(f'img:{gst_img_coord}')
    assert gst_img_coord.x == 2171.0 and gst_img_coord.y == 361.0
    
    doc_coord = page_image.get_doc_coord(gst_img_coord)
    print(f'doc:{doc_coord}')
    assert str(doc_coord) == '0.0541:0.1124'
    page_image.clear_transforms()    
    


    print(f'\n>Test crop rotate')    
    page_image.crop(top, bot)
    page_image.rotate(45)
    gst_img_coord = page_image.get_image_coord(gst_doc_coord)
    print(f'img:{gst_img_coord}')
    assert gst_img_coord.x == 235.0 and gst_img_coord.y == 111.0
    doc_coord = page_image.get_doc_coord(gst_img_coord)
    print(f'doc:{doc_coord}')
    assert str(doc_coord) == '0.0541:0.1124'    
    page_image.clear_transforms()        
    


    
    
    

    
