import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import urllib.error
import enrich

COMPANY = '示例科技有限公司'
QUOTE = COMPANY + '主营工业软件研发与技术服务，为企业提供生产管理系统。'

def source(url='https://example.com/profile'):
    return {'id':'S1','url':url,'title':'公司资料','content':QUOTE,
            'retrievedAt':'2026-10-29T10:00:00+08:00'}

def proposal(field='introduction', value='工业软件研发服务企业', **kw):
    item={'field':field,'value':value,'status':'supported','evidence':[{'sourceId':'S1','quote':QUOTE}]}
    item.update(kw)
    return {'companyName':COMPANY,'entityMatched':True,'fields':[item]}

class ReviewTests(unittest.TestCase):
    def test_existing_values_preserved_including_zero_false(self):
        for old in ('已有简介',0,False):
            d=enrich.review(COMPANY,proposal(),[source()],{'introduction':old})
            self.assertEqual(d['fields'][0]['status'],'preserved')
            self.assertEqual(d['fields'][0]['existingValue'],old)
            self.assertEqual(d['missingOnlyPatch'],{})
        self.assertIn('introduction',enrich.review(COMPANY,proposal(),[source()],{'introduction':' '})['missingOnlyPatch'])

    def test_entity_mismatch_never_patches(self):
        for key,value in [('companyName','另一家有限公司'),('entityMatched',False)]:
            p=proposal();p[key]=value
            self.assertEqual(enrich.review(COMPANY,p,[source()],{})['missingOnlyPatch'],{})
        row=source();row['content']=QUOTE.replace(COMPANY,'另一家有限公司')
        self.assertEqual(enrich.review(COMPANY,proposal(),[row],{})['missingOnlyPatch'],{})

    def test_quote_must_be_contiguous_real_and_in_bounds(self):
        for quote in ('不存在的连续摘录'*5,'短引文','字'*201):
            p=proposal(evidence=[{'sourceId':'S1','quote':quote}])
            self.assertEqual(enrich.review(COMPANY,p,[source()],{})['missingOnlyPatch'],{})
        p=proposal(evidence=[{'sourceId':'missing','quote':QUOTE}])
        self.assertEqual(enrich.review(COMPANY,p,[source()],{})['missingOnlyPatch'],{})

    def test_legal_requires_authoritative_host(self):
        p=proposal('legalRepresentative','测试法人')
        legal_source=source('https://www.cninfo.com.cn/doc'); legal_source['content']=QUOTE+'法定代表人为测试法人。'
        p['fields'][0]['evidence'][0]['quote']=QUOTE+'法定代表人为测试法人。'
        self.assertEqual(enrich.review(COMPANY,p,[source()],{})['missingOnlyPatch'],{})
        self.assertIn('legalRepresentative',enrich.review(COMPANY,p,[legal_source],{})['missingOnlyPatch'])
        self.assertFalse(enrich.authoritative('https://cninfo.com.cn.evil.example/doc'))

    def test_duplicate_unknown_conflict_fields_not_writable(self):
        p=proposal();p['fields']*=2
        with self.assertRaises(enrich.EnrichmentError):enrich.review(COMPANY,p,[source()],{})
        with self.assertRaises(enrich.EnrichmentError):enrich.review(COMPANY,proposal('investmentHighlight'),[source()],{})
        self.assertEqual(enrich.review(COMPANY,proposal(status='conflict'),[source()],{})['missingOnlyPatch'],{})

    def test_bp_append_only_supported_fields(self):
        text='项目名称：原项目\n公司名称：'+COMPANY
        out=enrich.patch_bp(text,{'website':'https://example.com','city':'杭州','introduction':'缺失简介','industryLabel':'软件','teamBackground':'团队事实'})
        self.assertTrue(out.startswith(text+'\n'))
        self.assertIn('项目简介：缺失简介',out)
        self.assertIn('行业：软件',out)
        self.assertIn('团队背景：团队事实',out)
        self.assertNotIn('https://',out);self.assertNotIn('杭州',out)

    def test_legal_value_must_be_supported_by_authoritative_quote(self):
        d=enrich.review(COMPANY,proposal('legalRepresentative','无关法人'),[source('https://www.cninfo.com.cn/doc')],{})
        self.assertEqual(d['missingOnlyPatch'],{})

    def test_bp_original_trailing_whitespace_preserved(self):
        text='项目名称：原项目  \n\n'
        self.assertEqual(enrich.patch_bp(text,{}),text)
        self.assertTrue(enrich.patch_bp(text,{'introduction':'简介'}).startswith(text))

    def test_city_requires_explicit_location_not_one_of_several_bases(self):
        quote=COMPANY+'目前拥有北京、广州、成都、宁波四大产业基地。'
        row=source();row['content']=quote
        p=proposal('city','宁波',evidence=[{'sourceId':'S1','quote':quote}])
        self.assertEqual(enrich.review(COMPANY,p,[row],{})['missingOnlyPatch'],{})
        quote=COMPANY+'注册地址位于浙江省宁波市，提供工业软件服务。'
        row['content']=quote;p['fields'][0]['evidence'][0]['quote']=quote
        self.assertEqual(enrich.review(COMPANY,p,[row],{})['missingOnlyPatch']['city'],'宁波')

class BoundaryTests(unittest.TestCase):
    def test_source_company_and_timezone(self):
        b={'companyName':'错误公司','sources':[source()]}
        with self.assertRaises(enrich.EnrichmentError):enrich.validate_sources(COMPANY,b)
        r=source();r['retrievedAt']='2026-10-29T10:00:00'
        with self.assertRaises(enrich.EnrichmentError):enrich.validate_sources(COMPANY,{'companyName':COMPANY,'sources':[r]})

    def test_http_errors_never_echo_request_or_server_secret(self):
        sentinel='TEST_SENTINEL_NOT_A_CREDENTIAL'
        for error in (urllib.error.HTTPError('https://example.com',401,sentinel,{},io.BytesIO(sentinel.encode())),RuntimeError(sentinel)):
            def opener(*args,**kw):raise error
            with self.assertRaises(enrich.EnrichmentError) as caught:
                enrich.request_json('https://example.com',{},sentinel,'GROK',opener)
            self.assertNotIn(sentinel,str(caught.exception))

    def test_main_bp_uses_original_fields_and_no_writes(self):
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory);text='项目名称：原项目\n公司名称：'+COMPANY+'\n项目简介：已有简介'
            (p/'bp.txt').write_text(text);(p/'parsed.json').write_text(json.dumps({'companyName':COMPANY,'introduction':'已有简介'}));(p/'sources.json').write_text(json.dumps({'companyName':COMPANY,'sources':[source()]}))
            argv=['enrich.py','--company',COMPANY,'--bp-text-file',str(p/'bp.txt'),'--parsed-bp-file',str(p/'parsed.json'),'--sources-file',str(p/'sources.json'),'--output',str(p/'out.json')]
            with patch('sys.argv',argv),patch.object(enrich,'grok_config',return_value=('placeholder','https://example.com','grok-test')),patch.object(enrich,'synthesize',return_value=(proposal(),{})),patch.object(enrich,'parse_local_bp',side_effect=AssertionError('unexpected MCP')),contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(enrich.main(),0)
            d=json.loads((p/'out.json').read_text());self.assertEqual(d['businessWrites'],0);self.assertEqual(d['missingOnlyPatch'],{});self.assertEqual(d['patchedBpText'],text)
            self.assertEqual((p/'out.json').stat().st_mode & 0o777,0o600)

if __name__=='__main__':unittest.main()
