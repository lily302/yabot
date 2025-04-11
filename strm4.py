#!/usr/local/bin/python3

from webdav3.client import Client
import sys,os,time,requests

def list_files(webdav_url1, username, password):
	# 创建WebDAV客户端
	options = {
		'webdav_hostname': webdav_url1,
		'webdav_login': username,
		'webdav_password': password
	}
	
	client = Client(options)
	mulu=[]
	wenjian=[]
	q=1
	files = []
	while q<5:
		try:		   
		   # 获取WebDAV服务器上的文件列表
			print("获取", webdav_url1.replace(webdav_url,''), flush=True)
			files = client.list()
		except:
			q+=1
			print('连接失败，2秒后重试...')
		else:
			if q>1:
				print('重连成功...')
			break

	for file in files[1:]:
		if file[-1]=='/':
			mulu.append(file)
		else:
			wenjian.append(file)
	return mulu,wenjian


# 输入WebDAV地址、用户名和密码
webdav_url = "DOCKER_ADDRESS" + "/dav" + "SCAN_PATH" + "/"   #alist webdav 地址 记得最后要加 /
webdav_url_final = "http://xiaoya.host:5678" + "/d" + "SCAN_PATH" + "/"
save_mulu=r'/media/strm' + "SCAN_PATH".replace("%20"," ") + "/"  #输出路径 例如 /mnt/media/xiaoya/电影/ 记得最后要加 /
username = "USERNAME"  #用户名
password = "PASSWORD"  #密码

l_0, l_1=list_files(webdav_url, username, password)
#scan_result_file = "scan_result"+ save_mulu.replace("/",".").replace(":\\","_").replace("\\","_").replace(" ","_").replace("__","_") + "txt"
current_timestamp = time.time()
time_string = time.strftime("%Y-%m-%d_%H-%M-%S", time.localtime(current_timestamp))
scan_result_file = time_string + ".txt"
if not os.path.exists(scan_result_file):
    url_1=[webdav_url]
    url_2=[]
    url_3=[]
    url_4=[]    
    url_5=[]     
    wenjian_1=[webdav_url + str(k) for k in l_1]
    wenjian_2=[]
    wenjian_3=[]
    wenjian_4=[]    
    wenjian_5=[]     
    if l_0 !=[]:
        for u in l_0:
            url_2.append(webdav_url+u)
            wenjian_2+=[webdav_url+u+str(i) for i in list_files(webdav_url+u, username, password)[1]]
        for x in url_2:
            l_x=list_files(x, username, password)[0]
            if l_x !=[]:
                for y in l_x:
                    url_3.append(x+y)
                    wenjian_3+=[x+y+str(j) for j in list_files(x+y, username, password)[1]]
                    L_y = list_files(x+y, username, password)[0]
                    if L_y !=[]:
                        for z in L_y:
                            url_4.append(x+y+z)
                            wenjian_4+=[x+y+z+str(j) for j in list_files(x+y+z, username, password)[1]]
                            L_z = list_files(x+y+z, username, password)[0]
                            if L_z !=[]:
                                for v in L_z:
                                    url_5.append(x+y+z+v)
                                    wenjian_5+=[x+y+z+v+str(j) for j in list_files(x+y+z+v, username, password)[1]]
    url=url_1+url_2+url_3+url_4+url_5
    wenjian_all=wenjian_1+wenjian_2+wenjian_3+wenjian_4+wenjian_5
    with open(scan_result_file, "w") as f:
        for item in wenjian_all:
            f.write(item + "\n")
            f.flush()
else:
    with open(scan_result_file, "r") as f:
    	wenjian_all=[line.strip() for line in f.readlines()]
    f.close()	

for b in wenjian_all:
	prefix = ".".join(b.replace(webdav_url,'').split(".")[0:-1])
	ext = b.replace(webdav_url,'').split(".")[-1]
	strm_file_temp = save_mulu + prefix.replace('%20'," ")
	if len(strm_file_temp) > 245:
           strm_file = strm_file_temp[:245] + "_xxx" + "." + 'strm'
	else:
           strm_file = strm_file_temp + "." + 'strm'
	if ext.upper() in ['MP4','MKV','ISO','FLV','AVI','TS','WMV','MOV','RM','RMVB','WEBM','WAV','MP3','FLAC','APE','WV','ALAC','M4A','AAC','WMA']:
		if not os.path.exists(strm_file):
			print('正在处理：'+b.replace(webdav_url,''), flush=True)
			try:
				os.makedirs(os.path.dirname(strm_file),exist_ok=True)
				with open(strm_file,"w",encoding='utf-8') as f:
					f.write(b.replace(webdav_url,webdav_url_final))
			except:
				try:
					os.makedirs(os.path.dirname(strm_file.replace('：','.')),exist_ok=True)
					translation_table = str.maketrans({ ':': ".",  '|': ".",  '$': ".",  '%': ".",  '&': "_", '#':'.', '+':'_', '\\':'.', '{':'.', '}':'.', '\'':'.'})
					with open(strm_file.translate(translation_table),"w",encoding='utf-8') as f:
						f.write(b.replace('/dav','/d').replace(" ","%20"))
				except:
					print(b.replace(webdav_url,'')+'处理失败，文件名包含特殊符号，建议重命名！', flush=True)
		else:
			print('文件已存在：'+strm_file, flush=True)	
print('处理完毕, 检查处理结果....')

def check_strm_files(directory):
    for root, dirs, files in os.walk(directory):
        for file in files:
            if file.endswith(".strm"):
                return True
    return False

def print_directories_without_strm(directory):
    for root, dirs, files in os.walk(directory):
        if not check_strm_files(root):
            print("此目录找不到strm文件：",root)

directory_to_check =r'/media/strm' + "SCAN_PATH"

print_directories_without_strm(directory_to_check)
sys.exit(0)
