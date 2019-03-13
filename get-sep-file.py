'''
Created: 2019-03-09 22:32:21
Author : Beibei
Email : beibei.feng@outlook.com
-----
Description: 
'''
import requests
import bs4
import pandas as pd
import os
import json
pd.set_option('display.max_columns', None)
pd.set_option('display.max_rows', None)
pd.set_option('max_colwidth', 1000)

class GSF:
    def __init__(self, username, password, path, content):
        self.username = username
        self.password = password
        self.path = path
        self.content = content
        self.conn = requests.Session()
        self.course = {}
        self.df = pd.DataFrame()

    def login(self):
        # post表单
        params = {
            'userName': self.username,
            'pwd': self.password,
            'sb': 'sb',
            'rememberMe': 1
        }
        post_url = 'http://sep.ucas.ac.cn/slogin'
        self.conn.post(post_url, data=params, headers={'Host': 'sep.ucas.ac.cn'})
        print('登录成功！\n')

        # 获取课程网站重定向链接
        coursePanel_resp = self.conn.get(
            url = 'http://sep.ucas.ac.cn/portal/site/16/801',
            headers={'Host': 'sep.ucas.ac.cn'},
            verify=False
        )       
        soup = bs4.BeautifulSoup(coursePanel_resp.text, 'lxml')
        coursePanelLink = soup.select('div h4 a')[0].get('href')
        
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
            if link.startswith('http://course.ucas.ac.cn/portal/site/1'):
                self.course[name] = link[-6:]
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

        # 打开所有一级文件夹
        for value in self.course.values():
            open_dir_resp = self.conn.post(
                url=sourceLink+'?panel=Main',
                data={
                    'collectionId': '/group/'+value+'/',
                    'sakai_action': 'doExpand_collection',
                    'sakai_csrf_token': sakai_csrf_token
                },
                headers={'Host': 'course.ucas.ac.cn'}
            )

        # 打开所有二级文件夹
        soup = bs4.BeautifulSoup(open_dir_resp.text, 'lxml')
        for item in soup.select('tr td input'):
            pathID = item.get('value')
            if pathID.endswith('/'):
                open_dir2_resp = self.conn.post(
                    url=sourceLink+'?panel=Main',
                    data={
                        'collectionId': pathID,
                        'sakai_action': 'doExpand_collection',
                        'sakai_csrf_token': sakai_csrf_token
                    },
                    headers={'Host': 'course.ucas.ac.cn'}
                )

        # 获取所有文件下载链接
        soup = bs4.BeautifulSoup(open_dir2_resp.text, 'lxml')
        fileLinkTemp = []
        for item in soup.select('tr th a'):
            link = item.get('href')
            if link.startswith('http://course.ucas.ac.cn/access/content/group'):
                fileLinkTemp.append(link)
        fileLink = fileLinkTemp[::2]

        tables = soup.select('table')
        df_list = []
        for table in tables:
            df_list.append(pd.concat(pd.read_html(table.prettify())))
        self.df = pd.concat(df_list)
        self.df.drop(self.df.columns[[0,1,3,4,5]], axis=1, inplace=True)
        self.df.drop([0,1,2,3],axis=0, inplace=True)
        self.df.columns = ['file', 'author', 'time', 'size']
        self.df.reset_index(drop=True, inplace=True)
        self.df['link'] = 0
        self.df['path'] = 0
        self.df['tag'] = '春季'
        for index in self.df.index:
            if str(self.df.iloc[index, 3]) == 'nan':
                if '秋季' in self.df.iloc[index, 0]:
                    self.df.iloc[index, 6] = '秋季'
                    tag_temp = '秋季'
                else:
                    tag_temp = '春季'
                self.df.iloc[index, 0] = self.df.iloc[index, 0][:-10]
                self.df.iloc[index, 5] = os.path.join(self.path, self.df.iloc[index, 0])
                path_temp = os.path.join(self.path, self.df.iloc[index, 0])
            elif str(self.df.iloc[index, 3])[-1] == '项':
                path_temp = os.path.join(path_temp, self.df.iloc[index, 0])
                self.df.iloc[index, 5] = path_temp
                self.df.iloc[index, 6] = tag_temp
            else:
                self.df.iloc[index, 4] = fileLink.pop(0)
                self.df.iloc[index, 5] = os.path.join(path_temp, self.df.iloc[index, 0])
                self.df.iloc[index, 6] = tag_temp
        if str(self.content).lower != 'all': 
            self.df = self.df[self.df['tag']==self.content]
        self.df.reset_index(drop=True, inplace=True)
        # print(self.df)

    def saveFile(self):
        if os.path.exists(self.path):
            for index in self.df.index:
                if not os.path.exists(self.df.iloc[index, 5]):
                    if str(self.df.iloc[index, 3]) == 'nan' or str(self.df.iloc[index, 3])[-1] == '项':
                        print("新建文件夹：  "+self.df.iloc[index, 5])
                        os.mkdir(self.df.iloc[index, 5])
                        continue
                    else:
                        print("开始下载新的文件：  "+self.df.iloc[index, 5]+"......\n")
                        download_resp = self.conn.get(
                            url=self.df.iloc[index, 4],
                            verify=False
                        )
                        with open(self.df.iloc[index, 5], 'wb') as f:
                            for chunk in download_resp.iter_content(chunk_size=1024):
                                f.write(chunk)
                        print("    "+self.df.iloc[index, 5]+"  下载完成!\n")
        else:
            print("路径不存在！")

if __name__ == "__main__":
    with open('config.json') as f:
        config = json.load(f)
    gsf = GSF(config['username'], config['password'], config['path'], config['content'])
    gsf.login()
    gsf.saveFile()