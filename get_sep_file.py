# _*_ coding: utf-8 _*_
'''
Created: 2019-03-09 22:32:21
Author : Beibei
Email : beibei.feng@outlook.com
-----
Description:
'''
import re
import requests
import bs4
import pandas as pd
import os
import json
from PIL import Image
import time
import sys
import nltk
import datetime

pd.set_option('display.max_columns', None)
pd.set_option('display.max_rows', None)
pd.set_option('max_colwidth', 1000)
requests.packages.urllib3.disable_warnings()
class GSF:
    def __init__(self, username, password, path, content):
        self.username = username
        self.password = password
        self.path = os.path.abspath(path)
        self.content = content
        self.conn = requests.Session()
        self.course = {}
        self.course_ = {}
        self.df = pd.DataFrame()

    def login(self):
        temp_login = self.conn.post(
            url='http://sep.ucas.ac.cn',
            headers={'Host': 'sep.ucas.ac.cn'},
            verify=False
        )

        soup = bs4.BeautifulSoup(temp_login.text, 'lxml')
        verifyText = soup.select('div label')[-1].getText()
        if verifyText == '验证码':
            verify = self.conn.get(
                url = 'http://sep.ucas.ac.cn/changePic',
                headers={'Host': 'sep.ucas.ac.cn'},
                verify=False
            )
            with open('verify.jpg', 'wb') as fd:
                for chunk in verify.iter_content(chunk_size=1024):
                    fd.write(chunk)
            img = Image.open('verify.jpg')
            img.show()
            verify_code = input("验证码:")
            # post表单
            test = self.conn.post(
                url = 'http://sep.ucas.ac.cn/slogin',
                data={
                    'userName': self.username,
                    'pwd': self.password,
                    'certCode': verify_code,
                    'sb': 'sb',
                    'rememberMe': 1
                },
                headers={'Host': 'sep.ucas.ac.cn'}
            )
        else:
            print("校园网好啊，不用花流量啊，也不用输验证码呀~")
            # post表单
            self.conn.post(
                url = 'http://sep.ucas.ac.cn/slogin',
                data={
                    'userName': self.username,
                    'pwd': self.password,
                    'sb': 'sb',
                    'rememberMe': 1
                },
                headers={'Host': 'sep.ucas.ac.cn'}
            )

        # 获取课程网站重定向链接
        coursePanel_resp = self.conn.get(
            url = 'http://sep.ucas.ac.cn/portal/site/16/801',
            headers={'Host': 'sep.ucas.ac.cn'},
            verify=False
        )
        try:
            soup = bs4.BeautifulSoup(coursePanel_resp.text, 'lxml')
            coursePanelLink = soup.select('div h4 a')[0].get('href')
            print("登录成功！ \n")
        except:
            print("验证码有误，请重试~")
            exit()

        # 获取资源页面链接
        courseLinks_resp = self.conn.get(
            url = coursePanelLink,
            headers={'Host': 'course.ucas.ac.cn'},
            verify=False
        )

        # 获取所有课程ID
        soup = bs4.BeautifulSoup(courseLinks_resp.text, 'lxml')
        for item in soup.select('ul div a'):
            link = item.get('href')
            name = item.get('title')
            if link.startswith('https://course.ucas.ac.cn/portal/site/1') and name.find(self.content) > -1:
                self.course[name[:-7]] = name[-2:]
                self.course_[link[-6:]] = name[:-7]


        # 获取资源按钮链接
        sourceLink = soup.find('a', attrs={'title':'资源 - 上传、下载课件，发布文档，网址等信息'}).get('href')
        source_resp = self.conn.get(
            url = sourceLink,
            headers={'Host': 'course.ucas.ac.cn'},
            verify=False
        )

        soup = bs4.BeautifulSoup(source_resp.text, 'lxml')
        # 获取collectionId
        collectionId = soup.find('a', attrs={'class': 'Mrphs-userNav__drop-btn Mrphs-userNav__submenuitem--profilepicture'}).get('style').split('/')[-3]
        # print(collectionId)
        # 获取csrf_token
        sakai_csrf_token = soup.find('input', attrs={'name': 'sakai_csrf_token'}).get('value')

        self.conn.post(
            url=sourceLink,
            data={
                'collectionId': '/user/'+collectionId,
                'sakai_action': 'doShowOtherSites',
                'sakai_csrf_token': sakai_csrf_token
            },
            headers={'Host': 'course.ucas.ac.cn'}
        )

        print('开始下载...')
        # 打开所有一级文件夹
        for key in self.course_.keys():
            open_dir_resp = self.conn.post(
                url=sourceLink+'?panel=Main',
                data={
                    'collectionId': '/group/'+key+'/',
                    'sakai_action': 'doExpand_collection',
                    'sakai_csrf_token': sakai_csrf_token
                },
                headers={'Host': 'course.ucas.ac.cn'}
            )

        # 打开所有文件夹
        pathset = set()
        path = []
        while True:
            addset = set()
            soup = bs4.BeautifulSoup(open_dir_resp.text, 'lxml')
            for item in soup.select('tr td input'):
                pathID = item.get('value')
                if pathID.endswith('/') and pathID not in pathset:
                    addset.add(pathID)
            if addset:
                pathset = pathset.union(addset)
                for pathID in addset:
                    open_dir_resp = self.conn.post(
                        url=sourceLink+'?panel=Main',
                        data={
                            'collectionId': pathID,
                            'sakai_action': 'doExpand_collection',
                            'sakai_csrf_token': sakai_csrf_token
                        },
                        headers={'Host': 'course.ucas.ac.cn'}
                    )
            else:
                for item in soup.select('tr td input'):
                    pathID = item.get('value')
                    if pathID.startswith('/group'):
                        path.append(str(self.course_[pathID[7:13]]+pathID[13:]))
                break

        # 获取所有文件下载链接
        soup = bs4.BeautifulSoup(open_dir_resp.text, 'lxml')
        fileLinkTemp = []
        for item in soup.select('tr th a'):
            link = item.get('href')
            if link != None:
                if link.startswith('https://course.ucas.ac.cn/access/content/group'):
                    fileLinkTemp.append(link)
        fileLink = fileLinkTemp[::2]

        tables = soup.select('table')
        df_list = []
        for table in tables:
            df_list.append(pd.concat(pd.read_html(table.prettify())))
        self.df = pd.concat(df_list)
        # print(self.df.index)
        if len(self.df.columns) == 12:
            # python3.6
            self.df = self.df.loc[:, ['标题', '创建者', '最后修改时间', '大小']]
        elif len(self.df.columns) == 9:
            # python3.7
            self.df = self.df.loc[:, [2,6,7,8]]
            self.df.columns = ['标题', '创建者', '最后修改时间', '大小']
        else:
            print("python版本可能不支持！")
            exit()
        self.df['link'] = 0
        self.df['path'] = 0
        self.df['tag'] = '秋季'
        self.df.dropna(inplace=True)
        # path_temp = None
        for index in self.df.index:
            # for p in path:
            #     found = True
            #     if(len(p.split('/')[-1]) == 0):
            #         continue
            #     for idx in range(len(p.split('/')[-1])):
            #         # print(p.split('/')[-1][idx],self.df.loc[index,'标题'][idx])
            #         if p.split('/')[-1][idx] != self.df.loc[index,'标题'][idx] and p.split('/')[-1][idx] != '_':
            #             found = False
            #             break
            #     # input()
            #     if found:
            #         path_temp = p
            #         break
            # if path_temp is None:
            #     print('!!!!!!!!',self.df.loc[index,'标题'])
            #     continue
            # print(self.df.loc[index,'标题'])
            if str(self.df.loc[index, '大小']).endswith('B'):
                path_temp = path.pop(0)
                self.df.loc[index, 'link'] = fileLink.pop(0)
                self.df.loc[index, 'path'] = os.path.join(self.path, path_temp)
            elif str(self.df.loc[index, '大小']).endswith('项'):
                path_temp = path.pop(0)
                self.df.loc[index, 'path'] = os.path.join(self.path, path_temp)
            else:
                self.df.drop(index, axis=0, inplace=True)
                # path_temp = None
                continue
            self.df.loc[index, 'tag'] = self.course[path_temp.strip().split('/')[0]]
            # path_temp = None
        # exit(0)
        # print(self.df.index,str(self.content).lower())
        if str(self.content).lower() != 'all':
            self.df = self.df[self.df['tag']==self.content]

        self.df.reset_index(drop=True, inplace=True)

    def saveFile(self):
        if os.path.exists(self.path):
            cur_course = ''
            for index in self.df.index:
                temp = self.df.iloc[index, 5][len(self.path) + 1:].split('/')[0]
                if temp != cur_course:
                    print(temp + ':')
                    cur_course = temp
                cur_file = self.df.iloc[index, 5][len(self.path) + 1 + len(cur_course) + 1:]
                if not os.path.exists(self.df.iloc[index, 5]):
                    if str(self.df.iloc[index, 3])[-1] == 'B':
                        if not os.path.exists(os.path.split(self.df.iloc[index, 5])[0]):
                            os.makedirs(os.path.split(self.df.iloc[index, 5])[0])
                            print("\t新建文件夹：  "+os.path.split(self.df.iloc[index, 5])[0])
                        print("\t下载新文件\t "+cur_file,end='')
                        sys.stdout.flush()
                        download_resp = self.conn.get(
                            url=self.df.iloc[index, 4],
                            verify=False
                        )
                        with open(self.df.iloc[index, 5], 'wb') as f:
                            for chunk in download_resp.iter_content(chunk_size=1024):
                                f.write(chunk)
                        print("\t下载完成")
                else:
                    print('\t文件已存在\t',cur_file)
                time.sleep(0.01)
            print("所有的文件已同步至最新！")
        else:
            print("路径不存在！")

    def init_homework(self):
        self.hw_main_link = {}
        self.hw_link = {}
        for c_id in self.course_.keys():
            self.hw_link[c_id] = []
        #获取所有课程的作业主界面链接
        for c_id in self.course_.keys():
            # print('https://course.ucas.ac.cn/portal/site/' + str(c_id))
            course_content = self.conn.get(
                url = 'https://course.ucas.ac.cn/portal/site/' + str(c_id),
                headers={'Host': 'course.ucas.ac.cn'},
                verify=False
            )
            course_soup = bs4.BeautifulSoup(course_content.text, 'lxml')
            self.hw_main_link[c_id] = course_soup.find('a', attrs={'title':'作业 - 在线发布、提交和批改作业'}).get('href')
            # print(self.hw_main_link[c_id])
            #获取每个作业链接
            course_hw_content = self.conn.get(
                url = self.hw_main_link[c_id],
                headers={'Host': 'course.ucas.ac.cn'},
                verify=False
            )
            bsObj = bs4.BeautifulSoup(course_hw_content.text, 'lxml')
            all_links = bsObj.find_all('a')
            hw_links = []
            for t in all_links:
                l = t.get('href')
                if l.find('assignmentReference') > -1 or l.find('submissionId') > -1:
                    hw_links.append(l)
            self.hw_link[c_id] = hw_links

    def save_homework(self):
        self.unfinished_homework = {}
        print('抓取作业链接...')
        self.init_homework()
        print('开始下载作业文件...')
        if os.path.exists(self.path):
            for c_id in self.course_.keys():
                print(self.course_[c_id],':')
                hw_path = os.path.join(self.path,self.course_[c_id])
                hw_path = os.path.join(hw_path,'homework')
                if not os.path.exists(hw_path):
                    os.makedirs(hw_path)
                for hw_link in self.hw_link[c_id]:
                    hw_content = self.conn.get(
                        url = hw_link,
                        headers={'Host': 'course.ucas.ac.cn'},
                        verify=False
                    )
                    soup = bs4.BeautifulSoup(hw_content.text, 'lxml')
                    if hw_link.find('submissionId') > -1:
                        attr = soup.find_all(name='div', attrs={'class' :'portletBody'})
                        title = attr[0].select('h3')
                        # print(title[0])
                        title = title[0].text.split('-')

                        print('\t  ',title[1].strip()+'：',title[0].strip())
                        continue
                    #作业信息
                    attr_names = soup.find_all(name='div', attrs={'class' :'itemSummaryHeader'})
                    attrs = soup.find_all(name='div', attrs={'class' :'itemSummaryValue'})
                    try:
                        title = attrs[0].getText().strip().replace('\n','').replace('\r','').replace('\t','')
                    except:
                        attr = soup.find_all(name='div', attrs={'class' :'portletBody'})
                        title = attr[0].select('h3')
                        # print(title[0])
                        title = title[0].text.split('-')
                        if(len(title) > 1):
                            print('\t  ',title[1].strip()+'：',title[0].strip())
                        else:
                            print('\t  ',title[0].strip())
                        continue
                    info = '作业信息\n'
                    submited = True
                    for attr_name,attr in zip(attr_names,attrs):
                        info += attr_name.getText().strip() + '\t' + attr.getText().strip() + '\n'
                        if(attr_name.getText().strip().find('截止') > -1):
                            due_time = attr.getText().strip()
                        if(attr_name.getText().strip().find('状态') > -1):
                            if(attr.getText().strip().find('未提交') > -1 or attr.getText().strip().find('进行中') > -1):
                                submited = False
                                self.unfinished_homework[self.course_[c_id]+' '+title] = due_time
                    attr = soup.find(name='div', attrs={'class':'textPanel'})
                    info += '\n指导\n'
                    attr_text = str(attr).replace("<br/>","\n")
                    attr_text = attr_text.replace("</p>","\n\n")

                    while True:
                        index_begin = attr_text.find("<")
                        index_end = attr_text.find(">",index_begin + 1)
                        if index_begin == -1:
                            break
                        attr_text = attr_text.replace(attr_text[index_begin:index_end+1],"")

                    info += attr_text
                    cur_path = os.path.join(hw_path,title)
                    if not os.path.exists(cur_path):
                        print('\t \033[1;31m 新作业:',title,'截止日期:',due_time,'\033[0m')
                        self.unfinished_homework[self.course_[c_id]+' '+title] = due_time
                        os.makedirs(cur_path)
                    else:
                        if not submited:
                            print('\t \033[1;31m 未提交：',title,'截止日期:',due_time,'\033[0m')
                        else:
                            print('\t ',title)
                    with open(cur_path + '/info.txt','w',encoding='utf8') as f:
                        f.write(info)
                    #附件
                    attachment_text = soup.find(name='ul',attrs={'class' :'attachList indnt1'})
                    if attachment_text is not None:
                        attachment_links = attachment_text.find_all('a')
                        for link in attachment_links:
                            # print(link.attrs['href'],link.get_text())
                            file_name = link.get_text()
                            file_dir = os.path.join(cur_path,file_name)
                            if not os.path.exists(file_dir):
                                print("\t\t下载新附件\t "+file_name,end='')
                                sys.stdout.flush()
                                download_resp = self.conn.get(
                                    url=link.attrs['href'],
                                    verify=False
                                )
                                with open(file_dir, 'wb') as f:
                                    for chunk in download_resp.iter_content(chunk_size=1024):
                                        f.write(chunk)
                                print("\t\t下载完成")
                                time.sleep(0.05)
                            else:
                                print('\t\t附件已存在\t',file_name)

                    submition_text = soup.find(name='table',attrs={'class' :'attachList listHier indnt1 centerLines'})
                    if submition_text is not None:
                        submition_path = os.path.join(cur_path,'submition')
                        if not os.path.exists(submition_path):
                            os.makedirs(submition_path)
                        submition_links = submition_text.find_all('a')
                        for link in submition_links:
                            if link.attrs['href'].find('attachment') == -1:
                                continue
                            # print(link.attrs['href'],link.get_text())
                            file_name = link.get_text()
                            file_dir = os.path.join(submition_path,file_name)
                            if not os.path.exists(file_dir):
                                print("\t\t下载提交的作业\t "+file_name,end='')
                                sys.stdout.flush()
                                download_resp = self.conn.get(
                                    url=link.attrs['href'],
                                    verify=False
                                )
                                with open(file_dir, 'wb') as f:
                                    for chunk in download_resp.iter_content(chunk_size=1024):
                                        f.write(chunk)
                                print("\t\t下载完成")
                                time.sleep(0.05)
                            else:
                                print('\t\t提交的作业已存在\t',file_name)
        self.homework_summary()

    def homework_summary(self):
        if len(self.unfinished_homework.keys()) > 0:
            print('\033\n[1;31m','*********未完成的作业***********')
            print('一共' + str(len(self.unfinished_homework.keys())) + '个')
            for k in self.unfinished_homework.keys():
                date = re.search(r"(\d{4}-\d{1,2}-\d{1,2})",self.unfinished_homework[k]).group(0)

                date = datetime.datetime.strptime(date, '%Y-%m-%d')
                today = datetime.datetime.today()
                delta = date - today
                print('\t',k,'\t',self.unfinished_homework[k],'\t还有' + str(delta.days + 1) + '天')
            print('\033[0m')

if __name__ == "__main__":
    with open('config.json',encoding='utf-8') as f:
        config = json.load(f)
    gsf = GSF(config['username'], config['password'], config['path'], config['content'])
    gsf.login()
    gsf.saveFile()
    gsf.save_homework()
