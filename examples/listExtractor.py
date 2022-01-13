import copy
import logging


import spacy

@Vision.component("list extractor",
                  requires=["page._.list_markers"],
                  assigns=["page._.lists_texts", "page._.list_words"],
                  )
def extractList(doc):
    for page in doc:
        read_order = page.read_order
        num_poses = [ read_order.position(word) for word in page.list_markers ]
        
        for pos1, pos2 in pairwise(num_poses):
            list_text = read_order[pos1:pos2].text
            page._.list_texts.append(list_text)
            page._.list_words.append(read_order[pos1:pos2])
    return doc

@Vision.component("annotate_list_text"
                  requires=["page._.list_texts"]
                  assigns=["page._.list_annots"],
                  )
def annotateListText(doc):
    for page in doc:
        for list_text in page._.list_texts:
            list_text = eliminateParenString(list_text)
            list_annots = annotate_text(list_text) # HOW TO DO THIS ?
            page._.list_annots.append(list_annots)
    return doc

@Vision.component("find_list_markers",
                  assigns=["page._.list_markers", "word._.numVal", "word._.numType"),
                  config={"num_chars": "().",
                          "ignore_chars": "",
                          }
                  )
def findListMarkers(doc):
    for page in doc:
        [ find_num(w) for w in page ]
        markers = [ w for w in page if w._.numText ]
        markers.sort(op.attrgetter('y1'))
        
        for marker in markers:
            if (marker.x1 > 0.45 and not marker._.numType == 'roman') or marker._.numVal > 50:
                continue
            
            ltText = page.find_text('left', marker)
            if (not ltText) or (not ltText.isalnum()):
                continue

            rtText = page.find_text('right', marker):
            if 'copies' in rtText:
                continue

            page._.list_markers.append(marker)
        #end for
    #end for



@Vision.component("read_order",
                  assigns=["page.read_order", "word._.lineNum"],
                  )
def readOrder(doc):
    for page in doc.pages:
        read_wordIdx, read_lineNum = utils.read_order(page)
        page.read_order = [page[idx] for idx in read_wordIdx]
        for w,lineNum in page, read_lineNum:
            w._.lineNum = lineNum
    #end

@Vision.component("read_order",
                  assigns=["page.read_order", "word._.lineNum"],
                  config={'minWordLen': 4}
                  )
def rotatePage(doc):
    def isRotated(page):
         horzSore = [ 1 if w.box.is_horizontal else 0 for w in page ]
         return True if horzScore > len(page)/2.0 else False

     def getAngle(page):
         long_words = [ w for w in page if len(w) > config.minWordLen]

         angleDict = { (0, 1, 3, 2): 0,  (1, 0, 2, 3): 0,   (1, 0, 3, 2): 0,
                       (3, 0, 2, 1): 90, (2, 3, 1, 0): 180, (1, 2, 0, 3): 270 }
         angle_counter = Counter()
         for w in long_words:
             wCoordIdxs = list(enumerate(w.coords))
             wCoordIdxs.sort(key=lambda tup: (tup[1].y, tup[1].x))
             idxs = [tup[0] for tup in wCoordIdxs]
             angle = angleDict[idxs]
             angle_counter[angle] += 1
        return max(angle_counter, key=angle_counter.get)

    def rotatePage(page, angle):
        xMultiplier = (page.height/float(page.width)) if angle in (90, 270) else 1.0
        yMultiplier = (page.width/float(page.height)) if angle in (90, 270) else 1.0
            
        def updateCoord(coord, angle, xoffset, yoffset):
            x,y,a = coord.x, coord.y, angle
            newX = y - offset if a == 90 else 1 - y - offset if a == 270 else 1 - x
            newY = 1 - x + offset if a == 90 else x + offset if a == 270 else 1 - y

            newX, newY = newX * xMultiplier, newY * yMultiplier
            return Coord(newX, newY)
        
        def updateCoords(word, angle, w, h):
            xoffset = (1.0 - (w/float(h)))/2.0
            yoffset = ((float(h)/w) - 1.0)/2.0
            newCoords = [updateCoord(c, angle, xoffset, yoffset) for c in word.coords]
            word.coords = newCoords

        [updateCoord(w, angle, page.wt, page.ht) for w in page]
    
    for page in doc.pages:
        if isRotated(page):
            angle = getAngle(page)
            rotatePage(page, angle)

@Vision.component("read_order",
                  assigns=["page.edited", "word._.edited"],
                  config={}
                  )
def editDoc(doc):
    pass # bigger discussion
            
            
        
            
        
        
        
        
    
    
    
        
                
            
            
            
        
        
    

            
            
    

        

            


    
    
                  
            
    
    
