import io,json,unittest
from mcp_client import LocalMcpClient,McpError
class ClientTests(unittest.TestCase):
 def test_remote_denied(self):
  for url in ['https://qtou.cn/api','ftp://127.0.0.1/api/v1/agent/mcp','http://u:p@localhost:8081/api/v1/agent/mcp','http://127.0.0.1:8081/api/v1/agent/mcp?x=1']:
   with self.assertRaises(McpError): LocalMcpClient(url)
 def test_server_allowed(self):
  for url in ['http://113.250.189.74:18081/api/v1/agent/mcp','https://qtou.example.com/api/v1/agent/mcp','http://127.0.0.1:8081/api/v1/agent/mcp']:
   LocalMcpClient(url)
 def test_env_token(self):
  import os,mcp_client
  os.environ['QTOU_CONNECTOR_TOKEN']='qtpat_x'
  try:self.assertEqual(mcp_client.local_token(),'qtpat_x')
  finally:del os.environ['QTOU_CONNECTOR_TOKEN']
 def test_env_token_rejected(self):
  import os,mcp_client
  os.environ['QTOU_CONNECTOR_TOKEN']='bad'
  try:
   with self.assertRaises(McpError):mcp_client.local_token()
  finally:del os.environ['QTOU_CONNECTOR_TOKEN']
 def test_success(self):
  def op(req,timeout):
   body=json.loads(req.data);return io.BytesIO(json.dumps({'id':body['id'],'result':{'structuredContent':{'ok':True}}}).encode())
  self.assertEqual(LocalMcpClient(token_provider=lambda:'secret',opener=op).call('agent_health'),{'ok':True})
 def test_no_secret_error(self):
  def op(*a,**k):raise RuntimeError('secret')
  with self.assertRaises(McpError) as c:LocalMcpClient(token_provider=lambda:'secret',opener=op).call('agent_health')
  self.assertNotIn('secret',str(c.exception))
 def test_tool_error(self):
  def op(req,timeout):return io.BytesIO(json.dumps({'id':1,'result':{'isError':True,'structuredContent':{'error':{'code':'NOT_FOUND','message':'secret'}}}}).encode())
  with self.assertRaises(McpError) as c:LocalMcpClient(token_provider=lambda:'secret',opener=op).call('x')
  self.assertEqual(c.exception.code,'NOT_FOUND');self.assertNotIn('secret',str(c.exception))
class PagingTests(unittest.TestCase):
 def test_all_items_follows_has_more(self):
  import mcp_client
  class Pager:
   calls=[]
   def call(self,tool,args):
    self.calls.append(args['page']);start=(args['page']-1)*2
    return {'items':list(range(5))[start:start+2],'hasMore':start+2<5}
  p=Pager();self.assertEqual(mcp_client.all_items(p,'agent_portfolio_list',{'afterInvestOnly':True}),[0,1,2,3,4]);self.assertEqual(p.calls,[1,2,3])
 def test_all_items_accepts_unpaged_list(self):
  import mcp_client
  class Old:
   def call(self,tool,args):return [{'id':'a'}]
  self.assertEqual(mcp_client.all_items(Old(),'x'),[{'id':'a'}])
if __name__=='__main__':unittest.main()
