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
if __name__=='__main__':unittest.main()
