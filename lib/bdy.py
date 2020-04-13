import requests
import os
import json
import webbrowser
from datetime import datetime
from util import stream
from model.enum import BaiDu, Env
from model.entity import BDFile, BDMeta, DownloadInfo, TaskInfo
from concurrent.futures import ThreadPoolExecutor
from queue import Queue
from threading import Condition, Lock
import logging

log = logging.getLogger(__name__)

thread_pool = ThreadPoolExecutor(20)
download_lock = Lock()
download_con = Condition(download_lock)
download_map = {}
download_task_queue = Queue()


class BDPanClient:

    def __init__(self):
        self.access_token = None
        self.refresh_token = None
        self.expire_time = 0
        self.cache = {}

    def __store_token(self, access_token, refresh_token, expires_in):
        expire_time = datetime.now().timestamp() + expires_in
        with open(Env.TOKEN_PATH, 'wt') as f:
            f.write(json.dumps({
                'access_token': access_token,
                'refresh_token': refresh_token,
                'expire_time': expire_time
            }))
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.expire_time = expire_time

    def __token(self):
        """
        获取token， 并将token存放于 ~/.bdfs/.access_token 文件中(可以在enum中修改默认值)
        如果token过期时间低于阈值则执行刷新
        :return:
        """
        if self.access_token and self.refresh_token:
            if self.expire_time - datetime.now().timestamp() < BaiDu.TOKEN_EXPIRE_THRESHOLD:
                self.__r_token(self.refresh_token)  # token过期时间低于阈值则执行刷新
            return self.access_token, self.refresh_token
        try:
            with open(Env.TOKEN_PATH, 'r') as f:
                token = f.read()
            if not token:
                access_token, refresh_token, expires_in = self.__req_token(self.__req_code())
                if not access_token or not refresh_token:
                    stream.print_error('access validate failed! please check your code is right, or you can retry '
                                       'otherwise check you internet')
                    exit(0)
                self.__store_token(access_token, refresh_token, expires_in)
            else:
                token = json.loads(token)
                self.access_token = token.get('access_token', None)
                self.refresh_token = token.get('refresh_token', None)
                self.expire_time = token.get('expire_time', 0)
                if not self.access_token or not self.refresh_token:
                    with open(Env.TOKEN_PATH, 'w') as f:
                        f.write('')
                return self.__token()
        except FileNotFoundError as _:
            os.mkdir(Env.TOKEN_DIR)
            f = open(Env.TOKEN_PATH, 'w')
            f.close()
            self.__token()
        return self.access_token, self.refresh_token

    def __req_code(self):
        """
        请求code获取链接，等待用户输入认证code
        :return:
        """
        webbrowser.open(BaiDu.GET_CODE)
        stream.print_info('Waiting for browser to open automatically:\n %s\n If is not open, you may need copy this '
                          'link to your web browser and request it.' % BaiDu.GET_CODE)
        stream.print_info('Please paste access code: \n')
        return input()

    def __req_token(self, code):
        res = self.__do_request(url=BaiDu.GET_ACCESS_KEY, params={
            'grant_type': 'authorization_code',
            'code': code,
            'client_id': BaiDu.CLIENT_ID,
            'client_secret': BaiDu.CLIENT_SECRET,
            'scope=': BaiDu.SCOPE,
            'redirect_uri': 'oob'
        }, method='GET')
        return res.get('access_token', None), res.get('refresh_token', None), res.get('expires_in', 0)

    def __r_token(self, refresh_token):
        res = self.__do_request(url=BaiDu.GET_ACCESS_KEY, params={
            'grant_type': 'refresh_token',
            'refresh_token': refresh_token,
            'client_id': BaiDu.CLIENT_ID,
            'client_secret': BaiDu.CLIENT_SECRET
        }, method='GET')
        access_token = res.get('access_token', None)
        refresh_token = res.get('refresh_token', None)
        expires_in = res.get('expires_in', 0)
        if expires_in == 0:
            stream.print_error('refresh token is failed you can retry reauthorize or remount bdfs.')
            stream.print_info('Retry (Y/N): \n')
            cond = input()
            if str(cond).upper() == 'Y':
                self.__r_token(refresh_token)
            else:
                exit(0)
        else:
            self.__store_token(access_token, refresh_token, expires_in)

    def __request(self, url, params, method='GET', raw=False, headers=None, waterfall=False):
        params['access_token'] = self.__token()[0]
        return self.__do_request(url, params, method, raw, headers, waterfall)

    def __do_request(self, url, params, method='GET', raw=False, headers=None, waterfall=False):
        if headers is None:
            headers = {}
        try:
            headers.update({'User-Agent': 'pan.baidu.com'})
            res = requests.request(method, url, params=params, headers=headers, stream=waterfall)
            if raw:
                return res
            else:
                res = res.json()
                if res.get('error', '') == 'expired_token':
                    stream.print_error('access token is expired or error please reauthorize.')
                    self.access_token = None
                    self.refresh_token = None
                    self.expires_in = 0
                    self.__token()
                    return self.__do_request(url, params, method)
                return res
        except Exception as e:
            log.error(e)

    def dir(self, d='/', inode=None):
        """
        从百度云盘获取文件列表
        :param inode:
        :param d: 路径
        :return:
        """
        res = self.__request(BaiDu.LIST, {'dir': d}, 'GET')
        return BDFile.from_json_list(res.get('list', []), inode)

    def dir_cache(self, d='/', inode=None, expire=BaiDu.DIR_EXPIRE_THRESHOLD):
        """
        根据路径从缓存中获取文件列表，如果缓存中没有或缓存超时，则从百度云盘获取后加入缓存并返回列表
        :param inode:
        :param d: 路径
        :param expire: 缓存过期时间（秒）
        :return:
        """
        res = self.cache.get(d, {})
        items = res.get('items', None)
        _expire = res.get('expire', -1)
        if (_expire != -1 and datetime.now().timestamp() > _expire) or not items:
            self.cache[d] = {
                'items': self.dir(d, inode),
                'expire': -1 if expire == -1 else datetime.now().timestamp() + expire
            }
        return self.cache[d]['items']

    def info(self, path, fsid):
        res = self.__request(BaiDu.INFO, {
            'path': path,
            'fsids': '[%s]' % fsid,
            'thumb': 0,
            'dlink': 1,
            'extra': 0
        })
        res = res.get('list', [])
        return None if res == [] else BDMeta.from_json(res[0])

    def upload(self):
        pass

    def download(self, f, start, size):
        meta = self.info(f.path, f.fs_id)
        return self.__download(meta, start, size)
        # print(meta.dlink)
        # print(meta.filename)
        # print(meta.md5)
        # print(meta.path)
        # print(meta.server_ctime)  # 服务器创建时间
        # print(meta.server_mtime)  # 服务器修改时间
        # pass

    def __download(self, meta, start, size):
        if not meta:
            return b'bdfs: file load failed' + str(datetime.now()).encode('utf-8')
        path = Env.PHYSICS_DIR + meta.path
        download_task_queue.put(TaskInfo(meta, start, size))
        _d = path[:path.rindex('/')]
        if not os.path.isdir(_d):
            os.makedirs(_d)
        try:
            return self.__read_file(path, start, size)
        except FileNotFoundError as _:
            download_con.wait()
            return self.__read_file(path, start, size)

    @staticmethod
    def __read_file(path, start, size):
        with open(path, 'rb') as f:
            while f.seek(start) == -1:
                download_con.wait()
                continue
            return f.read(size)


    def __download_file_direct(self, meta, start, size):
        info = DownloadInfo(block=Env.DEFAULT_BLOCK_SIZE, complete_md5=meta.md5, size=meta.size,
                            touch=datetime.now().timestamp())
        download_map[meta.fs_id] = info
        res = self.__request(url=meta.dlink, params={}, method='GET', raw=True, headers={'Range': 'bytes=%s-%s' % (str(start + 1), str(start + size))}).content
        # r = self.__request(url=meta.dlink, params={}, method='GET', raw=True, waterfall=True, headers={'Range': 'bytes=%s-%s' % (str(start), str(end))})
        # res = bytes()
        # for b in r.iter_content(chunk_size=info.block):
        #     if info.run_able():
        #         info.touch_tmp_size()
        #         res += b
        #     else:
        #         break
        log.info('start: %s, size: %s' % (str(start), str(size)))
        log.info(str(res))
        return res

    def process_download_file(self):
        thread_pool.submit(self.__do_process_download_file)

    def __do_process_download_file(self):
        while True:
            task_info = download_task_queue.get(True)
            meta = task_info.meta
            info = download_map.get(meta.fs_id, None)
            try:
                if not info:
                    info = DownloadInfo(block=Env.DEFAULT_BLOCK_SIZE, complete_md5=meta.md5, size=meta.size,
                                        touch=datetime.now().timestamp())
                    download_map[meta.fs_id] = info
                r = self.__request(url=meta.dlink, params={}, method='GET', raw=True, waterfall=True, headers={'Range': 'bytes=%s-%s' % (str(task_info.start + 1), str(task_info.start + task_info.size))})
                with open(Env.PHYSICS_DIR + meta.path, 'a+b') as f:
                    for b in r.iter_content(chunk_size=info.block):
                        info = download_map.get(meta.fs_id, None)
                        if info.run_able():
                            f.write(b)
                            info.touch_tmp_size()
                            download_con.notifyAll()
                        else:
                            return
            except Exception as e:
                log.error(e)
            finally:
                download_con.notifyAll()

    def quota(self):
        res = self.__request(BaiDu.QUOTA, {}, 'GET')
        return res


if __name__ == '__main__':
    bdy = BDPanClient()
    # print(bdy.dir('/PDF文档'))
    print(bdy.info('/PDF文档', '1113487933785121'))
