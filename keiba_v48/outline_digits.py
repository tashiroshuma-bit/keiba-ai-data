"""Recover outlined numeric glyphs by exact normalized font-outline matching.

Unlike OCR this uses the embedded font paths themselves. Unmatched outlines
are left untouched; unknown contours are never guessed into numbers.
"""
from io import BytesIO
import unicodedata

from fontTools.cffLib import CFFFontSet
from fontTools.pens.recordingPen import RecordingPen
from pypdf import PdfReader
from pdfminer.cmapdb import CMapDB


def signature(path):
    points = [point for item in path for point in item[1:]]
    if not points:
        return None
    xs, ys = zip(*points)
    x0, y0, x1, y1 = min(xs), min(ys), max(xs), max(ys)
    if x1 - x0 < .001 or y1 - y0 < .001:
        return None
    if path[0][0] != 'm':
        return None
    start = path[0][1]
    body = list(path[1:])
    if body and body[-1][-1] != start:
        body.append(('l', start))
    reversed_body = []
    previous = start
    for item in body:
        if item[0] == 'c':
            reversed_body.append(('c', item[2], item[1], previous))
        elif item[0] == 'l':
            reversed_body.append(('l', previous))
        else:
            return None
        previous = item[-1]
    variants = []
    for direction in (body, list(reversed(reversed_body))):
        normalized = tuple((item[0], *[(round((x-x0)/(x1-x0), 2), round((y-y0)/(y1-y0), 2)) for x, y in item[1:]]) for item in direction)
        variants.extend(normalized[n:]+normalized[:n] for n in range(len(normalized)))
    return min(variants) if variants else None


def font_templates(path):
    reader = PdfReader(path)
    templates = {}
    visited = set()
    mapping = CMapDB.get_unicode_map('Adobe-Japan1').cid2unichr
    for page in reader.pages:
        for obj in page['/Resources'].get('/Font', {}).values():
            font = obj.get_object()
            if '/DescendantFonts' not in font:
                continue
            descriptor = font['/DescendantFonts'][0].get_object().get('/FontDescriptor', {}).get_object()
            if '/FontFile3' not in descriptor:
                continue
            stream = descriptor['/FontFile3'].get_object()
            reference = getattr(stream, 'indirect_reference', None)
            key = reference.idnum if reference else id(stream)
            if key in visited:
                continue
            visited.add(key)
            cff = CFFFontSet()
            cff.decompile(BytesIO(stream.get_data()), None)
            embedded = cff[cff.fontNames[0]]
            for name in embedded.CharStrings.charStrings:
                if not name.startswith('cid'):
                    continue
                cid = int(name[3:])
                text = str(cid-9872) if 9872 <= cid <= 9881 else unicodedata.normalize('NFKC', mapping.get(cid, ''))
                if text not in list('0123456789.,:'):
                    continue
                pen = RecordingPen()
                embedded.CharStrings[name].draw(pen)
                contour = []
                for operation, points in pen.value:
                    if operation == 'moveTo':
                        contour = [('m', *[(x, -y) for x, y in points])]
                    elif operation == 'lineTo':
                        contour.append(('l', *[(x, -y) for x, y in points]))
                    elif operation == 'curveTo':
                        contour.append(('c', *[(x, -y) for x, y in points]))
                    elif operation == 'closePath':
                        sig = signature(contour)
                        if sig:
                            templates.setdefault(sig, set()).add(text)
    return {key: next(iter(values)) for key, values in templates.items() if len(values) == 1}


def recover(page, templates):
    chars = []
    for curve in page.curves:
        if curve['height'] > 16 or curve['width'] > 16:
            continue
        shape = [tuple(item) for item in curve.get('path', []) if item[0] != 'h']
        sig = signature(shape)
        text = templates.get(sig)
        if text is None and sig:
            matches = set()
            for candidate, value in templates.items():
                if len(candidate) != len(sig) or any(a[0] != b[0] for a, b in zip(candidate, sig)):
                    continue
                differences = [abs(x-y) for a,b in zip(candidate,sig) for p,q in zip(a[1:],b[1:]) for x,y in zip(p,q)]
                if differences and max(differences) <= .021 and sum(differences)/len(differences) <= .004:
                    matches.add(value)
            if len(matches) == 1:
                text = next(iter(matches))
        if text is None:
            continue
        if text in '.,:' and (curve['width'] > 2 or curve['height'] > 3):
            continue
        # Prefer the enclosing contour; avoid the same glyph's interior contours.
        if any(c['text'] == text and abs(c['x0']-curve['x0']) < 1 and abs(c['top']-curve['top']) < 2 for c in page.chars):
            continue
        chars.append({'text': text, 'x0': curve['x0'], 'x1': curve['x1'],
                      'top': curve['top'], 'bottom': curve['bottom'],
                      'doctop': curve['top'], 'upright': True, 'height': curve['height'],
                      'width': curve['width'], 'fontname': 'matched-embedded-outline',
                      'size': curve['height']})
    exterior = []
    for c in chars:
        if any(p is not c and p['x0'] <= c['x0']+.02 and p['x1'] >= c['x1']-.02
               and p['top'] <= c['top']+.02 and p['bottom'] >= c['bottom']-.02
               and p['width']*p['height'] > c['width']*c['height']*1.1 for p in chars):
            continue
        exterior.append(c)
    digits = [c for c in exterior if c['text'].isdigit()]
    for c in exterior:
        if c['text'] in '.,:':
            nearby = [p for p in digits if abs(p['x0']-c['x0']) < 7 and 0 <= c['top']-p['top'] < 10]
            if nearby:
                c['top'] = min(nearby, key=lambda p: abs(p['x0']-c['x0']))['top']
    return exterior
