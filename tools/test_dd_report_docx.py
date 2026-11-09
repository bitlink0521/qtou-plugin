import os
import re
import subprocess
import sys
import tempfile
import unittest
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, 'dd_report_docx.py')
TEMPLATE = os.path.join(os.path.dirname(HERE), 'assets', 'dd-report-template.docx')

HEADER = ('<w:hdr xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:p>'
          '<w:r><w:rPr><w:sz w:val="18"/></w:rPr><w:t>投资建议书 芯达科技</w:t></w:r></w:p></w:hdr>')
FOOTER = ('<w:ftr xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:p>'
          '<w:r><w:t>第</w:t></w:r><w:r><w:fldChar w:fldCharType="begin"/></w:r>'
          '<w:r><w:instrText> PAGE </w:instrText></w:r><w:r><w:fldChar w:fldCharType="separate"/></w:r>'
          '<w:r><w:t>7</w:t></w:r><w:r><w:fldChar w:fldCharType="end"/></w:r><w:r><w:t>页</w:t></w:r>'
          '<w:r><w:t>沈阳芯达科技有限公司</w:t></w:r></w:p></w:ftr>')
NOTES = ('<w:footnotes xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
         '<w:footnote w:type="separator" w:id="-1"><w:p/></w:footnote>'
         '<w:footnote w:id="1"><w:p><w:r><w:t>芯达2021年审计报告</w:t></w:r></w:p></w:footnote></w:footnotes>')


def text_of(xml):
    return ''.join(re.findall(r'<w:t\b[^>]*>([^<]*)</w:t>', xml))


class ReferenceLeakTests(unittest.TestCase):
    def setUp(self):
        self.work = tempfile.TemporaryDirectory()
        self.style = os.path.join(self.work.name, 'style.docx')
        with zipfile.ZipFile(TEMPLATE) as source, zipfile.ZipFile(self.style, 'w') as target:
            for name in source.namelist():
                data = source.read(name)
                if name == 'word/header1.xml':
                    data = HEADER.encode('utf-8')
                elif name == 'word/footer1.xml':
                    data = FOOTER.encode('utf-8')
                elif name == 'docProps/core.xml':
                    data = re.sub(rb'<dc:creator>.*?</dc:creator>', '<dc:creator>芯达项目组</dc:creator>'.encode('utf-8'), data)
                target.writestr(name, data)
            target.writestr('word/footnotes.xml', NOTES)
            target.writestr('word/comments.xml', '<w:comments xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
                                                 '<w:comment w:id="0"><w:p><w:r><w:t>芯达估值再核</w:t></w:r></w:p></w:comment></w:comments>')
        self.markdown = os.path.join(self.work.name, 'r.md')
        with open(self.markdown, 'w', encoding='utf-8') as out:
            out.write('# 摘要\n东来涂料。\n')
        self.output = os.path.join(self.work.name, 'out.docx')

    def tearDown(self):
        self.work.cleanup()

    def test_reference_company_wording_does_not_reach_the_new_report(self):
        subprocess.run([sys.executable, SCRIPT, self.markdown, '-o', self.output, '--company', '东来涂料技术（上海）股份有限公司',
                        '--title', '投资建议书', '--style', self.style], check=True, capture_output=True)
        with zipfile.ZipFile(self.output) as docx:
            everything = ''.join(docx.read(name).decode('utf-8', 'ignore') for name in docx.namelist() if name.endswith('.xml'))
            header, footer = docx.read('word/header1.xml').decode('utf-8'), docx.read('word/footer1.xml').decode('utf-8')
            self.assertNotIn('word/comments.xml', docx.namelist())
        self.assertNotIn('芯达', everything)
        self.assertEqual(text_of(header), '投资建议书　东来涂料技术（上海）股份有限公司')
        self.assertIn('<w:sz w:val="18"/>', header)
        self.assertEqual(text_of(footer), '第7页')
        self.assertIn('PAGE', footer)


if __name__ == '__main__':
    unittest.main()
