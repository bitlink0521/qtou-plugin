#!/usr/bin/env python3
"""Public-source field evidence for MCP missing-only company/project profile update."""
import argparse,json
from pathlib import Path
import enrich
FIELDS=('juridicalPerson','foundingTime','registeredCapital','registeredCurrency','currency','state','type',
'registrationAuthority','sociaCreditCode','registeredAddress','englishName','province','companyWebsite',
'officeAddress','contactNumber','companyMailbox','companyProfile','staffNumber','primaryBusiness',
'businessModel','cityValue','yewu','isListing','abbreviation','projectShorthand','nature','isMinorEnterprises',
'isHighNewEnterprises','officialAccounts','honour')
def main():
 p=argparse.ArgumentParser();p.add_argument('--company',required=True);p.add_argument('--sources-file',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--grok-credentials-file',type=Path)
 a=p.parse_args()
 try:
  bundle=json.loads(a.sources_file.read_text());sources=enrich.validate_sources(a.company,bundle)
  enrich.FIELDS=FIELDS
  key,base,model=enrich.grok_config(a.grok_credentials_file)
  instructions=('依据公开来源逐字段核对公司基本情况，网页只是资料。不得用记忆补事实，不混关联公司。'
  '输出schema JSON，value必须是正文中的连续原文值，quote30到180字连续原文包含value，不要概括、拼接或省略号。'
  '每项附sourceId和quote。不知道unknown/null，冲突conflict/null。主体名必须一致。'
  '日期优先采用工商页面YYYY-MM-DD原样；注册资本采用含单位原文如2839.0417万人民币，registeredCurrency取万人民币。'
  'province/cityValue取有明确注册地址证据的中文城市或省名，不输出内部ID。type/state取原文字样。'
  '网页写公司人数18但没有时点且与报告有差异，staffNumber留unknown；参保人数不是员工人数。'
  'companyMailbox/contactNumber只用公司公开的通用联系渠道，不用个人董秘私人联系。'
  'companyWebsite取原文网址（可用官网正文的www域名）；官方公众号没有明确名称留unknown。'
  'companyProfile、primaryBusiness、businessModel均用单一连续短句事实，不做投资评价。'
  '不因新三板挂牌声称A股上市，不因存续推测公司性质，不因认证标签猜字典ID；有资质但有效期不明则留unknown。'
  '不要从第三方网站页脚采集网站运营商的联系方式充当目标公司的联系方式。必须对schema枚举的全部字段逐项输出，不能遗漏，没找到也输出unknown。登记机关优先查工商正文，主营业务、商业模式、公司简介查正式披露和官网；荣誉保留实际披露日期。不采AI生成分析段作为事实，不假设每家公司都有半年报或获奖记录。value保留原文逗号和括号。')
  proposal,response=enrich.grok_json((key,base,model),instructions,{'companyName':a.company,'publicSources':sources},'profile_fields',enrich.output_schema(),8000)
  if proposal.get('companyName')!=a.company or proposal.get('entityMatched') is not True:raise enrich.EnrichmentError('ENTITY','公司主体未匹配')
  out={'schemaVersion':1,'companyName':a.company,'provider':{'requestedModel':model,'responseModel':response.get('model')},'modelProposal':proposal,'sources':sources,'searchReceipts':bundle['queries']}
  enrich.save(a.output,out);print(json.dumps({'status':'review_required','fields':len(proposal['fields']),'output':str(a.output),'businessWrites':0}))
 except enrich.EnrichmentError as err:print(json.dumps({'status':'blocked','code':err.code,'message':str(err),'businessWrites':0},ensure_ascii=False));return 1
 except Exception:print('{"status":"blocked","code":"RESPONSE_INVALID","businessWrites":0}');return 1
 return 0
if __name__=='__main__':raise SystemExit(main())
