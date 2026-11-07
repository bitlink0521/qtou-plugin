#!/usr/bin/env python3
"""Turn a Markdown due-diligence draft into a Word file in the layout of a reference .docx.

The reference is a report already on the qtou site (downloaded via agent_documents_download_url) or, when there is
none, the template shipped with the plugin. Its styles, page setup, headers/footers and section layout are kept; its
body is replaced by the draft. Standard library only.

    python3 dd_report_docx.py draft.md -o 尽调报告.docx --company 公司全称 --title 尽职调查报告 \
        [--org 管理人全称] [--date 2026年11月] [--style reference.docx]

Markdown understood: # / ## / ### / #### headings ("{-}" or 摘要/附录 = unnumbered), paragraphs, "- " and "1. "
items, pipe tables, **bold**, "表n：…" captions and "单位：…" lines.
"""
import argparse
import os
import re
import sys
import zipfile
from xml.sax.saxutils import escape

TEMPLATE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'assets', 'dd-report-template.docx')
UNNUMBERED = ('摘要', '摘  要', '目录', '附录', '附件')
MANUAL_NUMBER = re.compile(r'^(第[一二三四五六七八九十百]+[章节部分]\s*|[一二三四五六七八九十]+[、.．]\s*|（[一二三四五六七八九十\d]+）\s*|\d+(\.\d+)*[、.．]?\s+|\d+(\.\d+)+[、.．]?)')


def read_styles(xml):
    styles = {}
    for match in re.finditer(r'<w:style\b([^>]*)>(.*?)</w:style>', xml, re.S):
        attrs, body = match.groups()
        style_id = re.search(r'w:styleId="([^"]+)"', attrs)
        if not style_id:
            continue
        name = re.search(r'<w:name w:val="([^"]+)"', body)
        outline = re.search(r'<w:outlineLvl w:val="(\d)"', body)
        based = re.search(r'<w:basedOn w:val="([^"]+)"', body)
        kind = re.search(r'w:type="(\w+)"', attrs)
        styles[style_id.group(1)] = {
            'type': kind.group(1) if kind else '',
            'default': 'w:default="1"' in attrs,
            'name': name.group(1) if name else '',
            'outline': int(outline.group(1)) if outline else None,
            'numbered': '<w:numPr>' in body and '<w:numId w:val="0"/>' not in body,
            'based': based.group(1) if based else None,
        }
    return styles


def inherited(styles, style_id, key):
    seen = set()
    while style_id in styles and style_id not in seen:
        seen.add(style_id)
        value = styles[style_id][key]
        if value is not None and value is not False:
            return value
        style_id = styles[style_id]['based']
    return None


def pick_styles(styles, document_xml):
    used = re.findall(r'<w:pStyle w:val="([^"]+)"', document_xml)
    paragraph = {sid: s for sid, s in styles.items() if s['type'] == 'paragraph'}
    body = next((sid for sid, s in paragraph.items() if s['default']), None)
    headings = {}
    for level in range(1, 5):
        candidates = [sid for sid in paragraph if inherited(styles, sid, 'outline') == level - 1
                      and not paragraph[sid]['name'].lower().startswith('toc')]
        candidates += [sid for sid, s in paragraph.items() if s['name'].lower() in ('heading %d' % level, '标题 %d' % level)
                       and sid not in candidates]
        candidates.sort(key=lambda sid: (sid not in used, paragraph[sid]['name'].lower().startswith(('heading', '标题'))))
        if candidates:
            headings[level] = candidates[0]

    def named(*names):
        return next((sid for sid, s in paragraph.items() if s['name'] in names), None)

    return {
        'body': body,
        'headings': headings,
        'cell': named('表内容', 'Table Text', '表格文字'),
        'caption': named('表格图片名', '图表标题', 'caption', 'Caption', '题注'),
        'toc': named('TOC Heading', '目录标题'),
    }


def runs(text, size=None, bold=False):
    out = []
    for index, piece in enumerate(re.split(r'\*\*', text)):
        if not piece:
            continue
        props = ''
        if bold or index % 2 == 1:
            props += '<w:b/><w:bCs/>'
        if size:
            props += '<w:sz w:val="%d"/><w:szCs w:val="%d"/>' % (size, size)
        out.append('<w:r>%s<w:t xml:space="preserve">%s</w:t></w:r>' % ('<w:rPr>%s</w:rPr>' % props if props else '', escape(piece)))
    return ''.join(out)


def paragraph(text, style=None, align=None, extra='', size=None, bold=False, no_indent=False):
    props = ''
    if style:
        props += '<w:pStyle w:val="%s"/>' % style
    props += extra
    if no_indent:
        props += '<w:ind w:firstLine="0" w:firstLineChars="0"/>'
    if align:
        props += '<w:jc w:val="%s"/>' % align
    return '<w:p>%s%s</w:p>' % ('<w:pPr>%s</w:pPr>' % props if props else '', runs(text, size, bold))


def table(rows, picked):
    width = len(rows[0])
    grid = ''.join('<w:gridCol/>' for _ in range(width))
    border = ''.join('<w:%s w:val="single" w:sz="4" w:space="0" w:color="000000"/>' % side
                     for side in ('top', 'left', 'bottom', 'right', 'insideH', 'insideV'))
    out = ['<w:tbl><w:tblPr><w:tblW w:w="5000" w:type="pct"/><w:jc w:val="center"/><w:tblBorders>%s</w:tblBorders>'
           '<w:tblLayout w:type="autofit"/></w:tblPr><w:tblGrid>%s</w:tblGrid>' % (border, grid)]
    for index, row in enumerate(rows):
        cells = (row + [''] * width)[:width]
        out.append('<w:tr>%s' % ('<w:trPr><w:tblHeader/></w:trPr>' if index == 0 else ''))
        for cell in cells:
            shade = '<w:shd w:val="clear" w:color="auto" w:fill="D9D9D9"/>' if index == 0 else ''
            out.append('<w:tc><w:tcPr><w:tcW w:w="0" w:type="auto"/>%s<w:vAlign w:val="center"/></w:tcPr>%s</w:tc>' % (
                shade, paragraph(cell.strip(), picked['cell'] or picked['body'], 'center' if index == 0 else None,
                                 bold=index == 0, no_indent=True, size=None if picked['cell'] else 21)))
        out.append('</w:tr>')
    out.append('</w:tbl>')
    return ''.join(out)


def split_row(line):
    return [cell.strip() for cell in line.strip().strip('|').split('|')]


def body_xml(markdown, picked):
    lines = markdown.splitlines()
    out, buffer, index = [], [], 0

    def flush():
        if buffer:
            out.append(paragraph(' '.join(part.strip() for part in buffer), picked['body']))
            del buffer[:]

    while index < len(lines):
        line = lines[index].rstrip()
        stripped = line.strip()
        heading = re.match(r'^(#{1,4})\s+(.*?)\s*$', stripped)
        if not stripped:
            flush()
        elif heading:
            flush()
            level, text = len(heading.group(1)), heading.group(2)
            unnumbered = text.endswith('{-}') or text.replace(' ', '') in [u.replace(' ', '') for u in UNNUMBERED]
            text = text[:-3].strip() if text.endswith('{-}') else text
            style = picked['headings'].get(level) or picked['headings'].get(max(picked['headings'] or [1]))
            numbered = style and picked['numbered'].get(style)
            if numbered and not unnumbered:
                text = MANUAL_NUMBER.sub('', text, count=1).strip()
            extra = '<w:numPr><w:ilvl w:val="0"/><w:numId w:val="0"/></w:numPr>' if numbered and unnumbered else ''
            out.append(paragraph(text, style, 'center' if unnumbered and level == 1 else None, extra))
        elif stripped.startswith('|') and index + 1 < len(lines) and re.match(r'^\|?\s*:?-{2,}', lines[index + 1].strip()):
            flush()
            rows = [split_row(stripped)]
            index += 2
            while index < len(lines) and lines[index].strip().startswith('|'):
                rows.append(split_row(lines[index]))
                index += 1
            out.append(table(rows, picked))
            continue
        elif re.match(r'^表\s*\d+[：:]', stripped) or re.match(r'^图\s*\d+[：:]', stripped):
            flush()
            out.append(paragraph(stripped, picked['caption'] or picked['body'], 'center', bold=not picked['caption'], no_indent=True))
        elif re.match(r'^(单位|货币单位)[：:]', stripped):
            flush()
            out.append(paragraph(stripped, picked['body'], 'right', no_indent=True))
        elif re.match(r'^[-*]\s+', stripped):
            flush()
            out.append(paragraph('• ' + re.sub(r'^[-*]\s+', '', stripped), picked['body']))
        elif re.match(r'^\d+\.\s+', stripped):
            flush()
            out.append(paragraph(re.sub(r'^(\d+)\.\s+', r'（\1）', stripped), picked['body']))
        else:
            buffer.append(stripped)
        index += 1
    flush()
    return ''.join(out)


def cover_xml(args):
    blank = '<w:p/>'
    parts = [blank * 6, paragraph(args.company, None, 'center', size=44, bold=True, no_indent=True), blank,
             paragraph(args.title, None, 'center', size=44, bold=True, no_indent=True), blank * 10]
    if args.org:
        parts.append(paragraph(args.org, None, 'center', size=32, no_indent=True))
    parts.append(paragraph(args.date, None, 'center', size=32, no_indent=True))
    return ''.join(parts)


def toc_xml(picked):
    field = ('<w:p><w:r><w:fldChar w:fldCharType="begin" w:dirty="true"/></w:r><w:r><w:instrText xml:space="preserve">'
             ' TOC \\o "1-3" \\h \\z \\u </w:instrText></w:r><w:r><w:fldChar w:fldCharType="separate"/></w:r>'
             '<w:r><w:t>（打开文档时选择更新域即可生成目录）</w:t></w:r><w:r><w:fldChar w:fldCharType="end"/></w:r></w:p>')
    return paragraph('目  录', picked['toc'], 'center', size=None if picked['toc'] else 32, bold=not picked['toc'], no_indent=True) + field


def build(args):
    with zipfile.ZipFile(args.style) as source:
        files = {name: source.read(name) for name in source.namelist()}
    document = files['word/document.xml'].decode('utf-8')
    styles = read_styles(files['word/styles.xml'].decode('utf-8'))
    picked = pick_styles(styles, document)
    picked['numbered'] = {sid: bool(inherited(styles, sid, 'numbered')) for sid in picked['headings'].values()}

    head, rest = document.split('<w:body>', 1)
    content, tail = rest.rsplit('</w:body>', 1)
    last = content.rfind('<w:sectPr')
    final_section = content[last:].strip() if last >= 0 and content.rstrip().endswith('</w:sectPr>') else ''
    breaks = re.findall(r'<w:sectPr\b.*?</w:sectPr>', content[:len(content) - len(final_section)], re.S)

    def section_break(xml):
        return '<w:p><w:pPr>%s</w:pPr></w:p>' % xml

    page_break = '<w:p><w:r><w:br w:type="page"/></w:r></w:p>'
    with open(args.markdown, encoding='utf-8') as handle:
        markdown = handle.read()
    parts = [cover_xml(args)]
    parts.append(section_break(breaks[0]) if breaks else page_break)
    parts.append(toc_xml(picked))
    parts.append(section_break(breaks[1]) if len(breaks) > 1 else page_break)
    parts.append(body_xml(markdown, picked))
    files['word/document.xml'] = (head + '<w:body>' + ''.join(parts) + final_section + '</w:body>' + tail).encode('utf-8')

    settings = files['word/settings.xml'].decode('utf-8')
    if '<w:updateFields' not in settings:
        settings = re.sub(r'(<w:settings\b[^>]*>)', r'\1<w:updateFields w:val="true"/>', settings, count=1)
    files['word/settings.xml'] = settings.encode('utf-8')

    rels_name = 'word/_rels/document.xml.rels'
    rels = files[rels_name].decode('utf-8')
    body = files['word/document.xml'].decode('utf-8')
    for rel in re.findall(r'<Relationship\b[^>]*/>', rels):
        rel_id = re.search(r'Id="([^"]+)"', rel).group(1)
        if re.search(r'/(image|hyperlink|oleObject|chart)"', rel) and 'r:id="%s"' % rel_id not in body and 'r:embed="%s"' % rel_id not in body:
            rels = rels.replace(rel, '')
            target = re.search(r'Target="([^"]+)"', rel).group(1)
            still_used = any(target in data.decode('utf-8', 'ignore') for name, data in files.items()
                             if name.endswith('.rels') and name != rels_name)
            if not still_used:
                files.pop('word/' + target, None)
    files[rels_name] = rels.encode('utf-8')

    with zipfile.ZipFile(args.output, 'w', zipfile.ZIP_DEFLATED) as target:
        for name, data in files.items():
            target.writestr(name, data)
    return picked


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('markdown')
    parser.add_argument('-o', '--output', required=True)
    parser.add_argument('--company', required=True, help='公司全称（封面）')
    parser.add_argument('--title', default='尽职调查报告', help='报告名称（封面）')
    parser.add_argument('--org', default='', help='基金或管理人全称（封面，可空）')
    parser.add_argument('--date', default='', help='封面日期，如 2026年11月')
    parser.add_argument('--style', default=TEMPLATE, help='样式来源 .docx，默认用插件自带模板')
    args = parser.parse_args()
    if not args.date:
        import datetime
        today = datetime.date.today()
        args.date = '%d年%d月' % (today.year, today.month)
    if not zipfile.is_zipfile(args.style):
        sys.exit('样式来源不是有效的 .docx：%s' % args.style)
    picked = build(args)
    print('已生成 %s（样式来源：%s；标题样式：%s）' % (args.output, os.path.basename(args.style),
                                             ', '.join('%d→%s' % item for item in sorted(picked['headings'].items()))))


if __name__ == '__main__':
    main()
