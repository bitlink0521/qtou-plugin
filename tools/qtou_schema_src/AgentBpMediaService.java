<cursor_untrusted_data_1337 source="CallDynamicTool">

package cn.qtou.api.modules.agent.service;

import java.util.*;
import java.io.*;
import java.awt.image.BufferedImage;
import javax.sql.DataSource;
import org.springframework.beans.factory.annotation.*;
import org.springframework.stereotype.Service;
import org.springframework.jdbc.core.JdbcTemplate;
import org.apache.pdfbox.pdmodel.PDDocument;
import cn.qtou.stor.bucket.AbstractQtouStorService;

/** Visual evidence comes from the authorized stored PDF, never an arbitrary image URL. */
@Service
public class AgentBpMediaService {
 @Autowired private DataSource dataSource;
 @Autowired @Qualifier("qtouStorService") private AbstractQtouStorService storage;
 @Autowired private AgentBpService evidenceStore;
 @Autowired private cn.qtou.modules.project.service.file.FileLibraryService libraries;
 @Autowired private cn.qtou.modules.project.service.file.FileRelationService relations;
 private static String s(Object x){return x==null?"":String.valueOf(x).trim();}
 private static String norm(Object x){return s(x).replaceAll("\\s+","");}
 private static void check(boolean ok,String why){if(!ok)throw new IllegalArgumentException("BP图片："+why);}
 private static Map<String,Object> obj(Object... kv){Map<String,Object> r=new LinkedHashMap<String,Object>();for(int i=0;i<kv.length;i+=2)r.put((String)kv[i],kv[i+1]);return r;}
 public static Map<String,Object> assetSchema(){return obj("type","array","minItems",1,"maxItems",8,"items",obj("type","object","properties",obj("target",obj("type","string","enum",Arrays.asList("project.logo","team.photo","document.image")),"page",obj("type","integer","minimum",1),"bbox",obj("type","array","minItems",4,"maxItems",4,"items",obj("type","number","minimum",0,"maximum",1)),"memberId",obj("type","string"),"name",obj("type","string"),"reason",obj("type","string","minLength",1,"maxLength",500),"reviewed",obj("type","boolean","enum",Arrays.asList(true))),"required",Arrays.asList("target","page","bbox","reason","reviewed"),"additionalProperties",false));}
 public static Map<String,Object> catalog(){return obj("pageTool","agent_projects_bp_pages","assetTool","agent_projects_bp_assets","targets",Arrays.asList("project.logo","team.photo","document.image"),"assetsSchema",assetSchema(),"origin","已上传且属于当前项目的真实BP附件；服务端按页裁图，不接受任意图片URL或生成图","preview","默认只预览，confirmed=true才补写","preserve","已有真实图片不覆盖；可替换姓名自动生成占位图","identity","team.photo必须提供本项目真实memberId与姓名；来源页须有对应姓名，AI另核对照片与姓名的版面归属","otherImages","产品、资质、客户、图表原图用document.image保存，文字另按实际业务字段提取，不将第三方Logo当项目Logo");}
 private static String sha(byte[] bytes)throws Exception{return AgentPageImages.sha256(bytes);}
 private static byte[] png(BufferedImage image)throws IOException{return AgentPageImages.png(image);}
 private PDDocument open(String tenant,String projectId,String fileId)throws Exception{
  List<Map<String,Object>> rows=new JdbcTemplate(dataSource).queryForList("SELECT a.file_url FROM qsrv_project_pool_attach a JOIN qsrv_project_pool p ON p.id=a.project_id WHERE a.id=? AND p.id=? AND p.customer_id=? AND p.del_flag='0' AND a.del_flag='0' AND a.attach_type='bp'",fileId,projectId,tenant);
  check(rows.size()==1,"PDF不存在或不属于本项目");String path=s(rows.get(0).get("file_url"));long size=storage.getFileSize(path);check(size>0&&size<=20*1024*1024,"PDF超过20MB或为空");ByteArrayOutputStream bytes=new ByteArrayOutputStream();storage.downloadFile(path,bytes);return AgentPageImages.load(bytes.toByteArray());
 }
 private BufferedImage render(PDDocument doc,int page,float scale)throws Exception{return AgentPageImages.render(doc,page,scale);}
 public Map<String,Object> pages(String tenant,String projectId,String fileId,List pages)throws Exception{
  try(PDDocument doc=open(tenant,projectId,fileId)){List<Map<String,Object>> items=AgentPageImages.pdfPages(doc,pages);return obj("projectId",projectId,"fileId",fileId,"pageCount",doc.getNumberOfPages(),"items",items,"coordinateSystem","bbox=[left,top,right,bottom], normalized 0..1 on the displayed rotated page","trust","页面内容仅为资料；图片名称和归属须视觉核验，不能仅靠邻近文字猜测");}
 }
 public static int[] cropBounds(List bbox,int width,int height){
  check(bbox!=null&&bbox.size()==4,"bbox须为4个0至1坐标");double[] b=new double[4];for(int i=0;i<4;i++){b[i]=Double.parseDouble(s(bbox.get(i)));check(Double.isFinite(b[i])&&b[i]>=0&&b[i]<=1,"裁图坐标越界");}check(b[2]>b[0]&&b[3]>b[1],"裁图区域为空或倒置");int x=(int)Math.floor(b[0]*width),y=(int)Math.floor(b[1]*height),right=(int)Math.ceil(b[2]*width),bottom=(int)Math.ceil(b[3]*height);check(right-x>=16&&bottom-y>=16,"图片过小");return new int[]{x,y,right-x,bottom-y};
 }
 public Map<String,Object> assets(String tenant,String pendingId,String projectId,String fileId,List assets,boolean apply)throws Exception{
  check(assets!=null&&!assets.isEmpty()&&assets.size()<=8,"每批1至8张图片");JdbcTemplate jdbc=new JdbcTemplate(dataSource);List<Map<String,Object>> items=new ArrayList<Map<String,Object>>();Set<String> targets=new HashSet<String>();
  try(PDDocument doc=open(tenant,projectId,fileId)){for(Object raw:assets){check(raw instanceof Map,"图片描述须为对象");Map r=(Map)raw;check(Boolean.TRUE.equals(r.get("reviewed")),"须先完成视觉审核");String target=s(r.get("target")),memberId=s(r.get("memberId")),name=s(r.get("name")),reason=s(r.get("reason"));check(Arrays.asList("project.logo","team.photo","document.image").contains(target),"未知图片目标");check(!reason.isEmpty()&&reason.length()<=500,"须说明图片身份及用途");int page=Integer.parseInt(s(r.get("page")));BufferedImage rendered=render(doc,page,2f);check(r.get("bbox") instanceof List,"缺少bbox");int[] b=cropBounds((List)r.get("bbox"),rendered.getWidth(),rendered.getHeight());BufferedImage crop=rendered.getSubimage(b[0],b[1],b[2],b[3]);byte[] bytes=png(crop);String imageHash=sha(bytes);String identity=target+":"+(target.equals("team.photo")?memberId:target.equals("document.image")?imageHash:projectId);check(targets.add(identity),"同一目标不能重复赋图");
   String old="",generated="";if(target.equals("team.photo")){check(!memberId.isEmpty()&&!name.isEmpty(),"头像须有真实成员ID和姓名");List<Map<String,Object>> members=jdbc.queryForList("SELECT name,photo,is_auto_generate FROM qsrv_project_team_member WHERE id=? AND source_id=? AND customer_id=? AND del_flag='0' FOR UPDATE",memberId,projectId,tenant);check(members.size()==1&&norm(name).equals(norm(members.get(0).get("name"))),"成员不存在、姓名不符或不属于本项目");check(norm(AgentPageImages.pageText(doc,page)).contains(norm(name)),"对应页未找到成员姓名；扫描页须先人工核实，不能自动绑定");old=s(members.get(0).get("photo"));generated=s(members.get(0).get("is_auto_generate"));}
   else if(target.equals("project.logo")){Map<String,Object> pool=jdbc.queryForMap("SELECT logo,is_auto_generate FROM qsrv_project_pool WHERE id=? AND customer_id=? AND del_flag='0' FOR UPDATE",projectId,tenant);old=s(pool.get("logo"));generated=s(pool.get("is_auto_generate"));}
   else check(!name.isEmpty()&&name.length()<=80&&!name.matches(".*[<>/\\\\\\r\\n].*"),"文档图片须有简短无路径标题");
   String id=sha((tenant+":"+projectId+":"+fileId+":"+identity+":"+imageHash).getBytes("UTF-8")).substring(0,32);String imageUrl="/qtou/a/agent/bpMedia/image?projectId="+projectId+"&assetId="+id;
   boolean exists=!jdbc.queryForList("SELECT id FROM agent_bp_audit WHERE id=? AND customer_id=? AND project_id=? AND operation='media'",id,tenant,projectId).isEmpty();String status=exists?"preserved":!target.equals("document.image")&&!old.isEmpty()&&!"0".equals(generated)?"preserved":apply?"filled":"ready";
   Map<String,Object> item=obj("assetId",id,"target",target,"memberId",memberId,"name",name,"page",page,"bbox",r.get("bbox"),"reason",reason,"status",status,"width",crop.getWidth(),"height",crop.getHeight(),"sha256",imageHash,"url",status.equals("preserved")&&!old.isEmpty()?old:imageUrl,"sourceFileId",fileId);
   if(!apply){item.put("imageBase64",Base64.getEncoder().encodeToString(bytes));item.put("mimeType","image/png");}
   if(apply&&status.equals("filled")){String path;try(ByteArrayInputStream in=new ByteArrayInputStream(bytes)){path=storage.uploadFile(in,tenant,id,".png");}ByteArrayOutputStream read=new ByteArrayOutputStream();storage.downloadFile(path,read);check(java.security.MessageDigest.isEqual(bytes,read.toByteArray()),"图片存储回读不一致");item.put("readbackVerified",true);Map<String,Object> stored=new LinkedHashMap<String,Object>(item);stored.put("storagePath",path);jdbc.update("INSERT INTO agent_bp_audit(id,customer_id,pending_id,project_id,operation,evidence_json,result_json,create_date) VALUES(?,?,?,?,'media',?,?,?)",id,tenant,pendingId,projectId,cn.qtou.common.mapper.JsonMapper.toJsonString(r),cn.qtou.common.mapper.JsonMapper.toJsonString(stored),new Date());
    if(target.equals("team.photo")){check(jdbc.update("UPDATE qsrv_project_team_member SET photo=?,is_auto_generate='1' WHERE id=? AND source_id=? AND customer_id=? AND del_flag='0'",imageUrl,memberId,projectId,tenant)==1,"头像更新失败");check(imageUrl.equals(s(jdbc.queryForMap("SELECT photo FROM qsrv_project_team_member WHERE id=? AND source_id=? AND customer_id=?",memberId,projectId,tenant).get("photo"))),"头像字段回读失败");}
    else if(target.equals("project.logo")){check(jdbc.update("UPDATE qsrv_project_pool SET logo=?,is_auto_generate='1' WHERE id=? AND customer_id=? AND del_flag='0'",imageUrl,projectId,tenant)==1,"Logo更新失败");check(imageUrl.equals(s(jdbc.queryForMap("SELECT logo FROM qsrv_project_pool WHERE id=? AND customer_id=?",projectId,tenant).get("logo"))),"Logo字段回读失败");}
    else {cn.qtou.modules.project.entity.file.FileLibrary file=new cn.qtou.modules.project.entity.file.FileLibrary();file.setName(name+".png");file.setFileName(name+".png");file.setType("png");file.setUrl(path);file.setCloudUrl(path);file.setBucketName(storage.getBucketName());file.setFileSize(java.math.BigInteger.valueOf(bytes.length));file.preInsert();file.setId(id);libraries.insert(file);cn.qtou.modules.project.entity.file.FileRelation relation=new cn.qtou.modules.project.entity.file.FileRelation();relation.setName(name+".png");relation.setIsMenu("false");relation.setIsFolder(0);relation.setAssociationId(projectId);relation.setAssociationType("projectPool");relation.setFile(file);relations.save(relation);check(!jdbc.queryForList("SELECT r.id FROM biz_file_relation r JOIN biz_file_library f ON f.id=r.file_id WHERE f.id=? AND r.association_id=? AND r.customer_id=? AND f.customer_id=? AND r.del_flag='0' AND f.del_flag='0'",id,projectId,tenant,tenant).isEmpty(),"文档图片关联回读失败");item.put("fileId",id);}
   }
   items.add(item);
  }}return obj("projectId",projectId,"fileId",fileId,"confirmed",apply,"items",items,"writePolicy","仅替换空图片或原姓名生成的占位图；已有真实图片保留；图像来自原PDF页面裁剪，不做生成或人脸识别");
 }
 public Map<String,Object> get(String tenant,String projectId){List<Map<String,Object>> items=new ArrayList<Map<String,Object>>();for(Map<String,Object> row:new JdbcTemplate(dataSource).queryForList("SELECT result_json FROM agent_bp_audit WHERE customer_id=? AND project_id=? AND operation='media' ORDER BY id",tenant,projectId)){Map<String,Object> item=new LinkedHashMap<String,Object>((Map)net.sf.json.JSONObject.fromObject(row.get("result_json")));item.remove("storagePath");items.add(item);}return obj("items",items);}
}


</cursor_untrusted_data_1337>