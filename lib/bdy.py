import requests
import os
import json
import webbrowser
from datetime import datetime
from util import stream
from model.enum import BaiDu, Env
from model.entity import BDFile, BDMeta, DownloadInfo, TaskInfo
from concurrent.futures import ProcessPoolExecutor
from multiprocessing import Queue
import logging

log = logging.getLogger(__name__)

process_pool = ProcessPoolExecutor(2)
download_con = Queue(1)
download_map = {}
download_task_queue = Queue()


def do_request(url, params, method='GET', raw=False, headers=None, waterfall=False):
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
                atoken, rtoken, etime = get_token()
                return do_request(url=url, params=params, method=method, headers={'access_token': atoken})
            return res
    except Exception as e:
        log.error(e)


def get_token(access_token=None, refresh_token=None, expire_time=None):
    """
    获取token， 并将token存放于 ~/.bdfs/.access_token 文件中(可以在enum中修改默认值)
    如果token过期时间低于阈值则执行刷新
    :return:
    """
    if access_token and refresh_token:
        if expire_time - datetime.now().timestamp() < BaiDu.TOKEN_EXPIRE_THRESHOLD:
            return r_token(refresh_token)  # token过期时间低于阈值则执行刷新
        return access_token, refresh_token
    try:
        with open(Env.TOKEN_PATH, 'r') as f:
            token = f.read()
        if not token:
            access_token, refresh_token, expires_in = req_token(req_code())
            if not access_token or not refresh_token:
                stream.print_error('access validate failed! please check your code is right, or you can retry '
                                   'otherwise check you internet')
                exit(0)
            return store_token(access_token, refresh_token, expires_in)
        else:
            token = json.loads(token)
            access_token = token.get('access_token', None)
            refresh_token = token.get('refresh_token', None)
            expire_time = token.get('expire_time', 0)
            if not access_token or not refresh_token:
                with open(Env.TOKEN_PATH, 'w') as f:
                    f.write('')
            return get_token(access_token, refresh_token, expire_time)
    except FileNotFoundError as _:
        os.mkdir(Env.TOKEN_DIR)
        f = open(Env.TOKEN_PATH, 'w')
        f.close()
        get_token(access_token, refresh_token, expire_time)
    return access_token, refresh_token, expire_time


def req_code():
    """
    请求code获取链接，等待用户输入认证code
    :return:
    """
    webbrowser.open(BaiDu.GET_CODE)
    stream.print_info('Waiting for browser to open automatically:\n %s\n If is not open, you may need copy this '
                      'link to your web browser and request it.' % BaiDu.GET_CODE)
    stream.print_info('Please paste access code: \n')
    return input()


def store_token(access_token, refresh_token, expires_in):
    expire_time = datetime.now().timestamp() + expires_in
    with open(Env.TOKEN_PATH, 'wt') as f:
        f.write(json.dumps({
            'access_token': access_token,
            'refresh_token': refresh_token,
            'expire_time': expire_time
        }))
    return access_token, refresh_token, expire_time


def req_token(code):
    res = do_request(url=BaiDu.GET_ACCESS_KEY, params={
        'grant_type': 'authorization_code',
        'code': code,
        'client_id': BaiDu.CLIENT_ID,
        'client_secret': BaiDu.CLIENT_SECRET,
        'scope=': BaiDu.SCOPE,
        'redirect_uri': 'oob'
    }, method='GET')
    return res.get('access_token', None), res.get('refresh_token', None), res.get('expires_in', 0)


def r_token(refresh_token):
    res = do_request(url=BaiDu.GET_ACCESS_KEY, params={
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
            r_token(refresh_token)
        else:
            exit(0)
    else:
        return store_token(access_token, refresh_token, expires_in)


def request(atoken, rtoken, etime, url, params, method='GET', raw=False, headers=None, waterfall=False):
    params['access_token'] = get_token(atoken, rtoken, etime)[0]
    return do_request(url, params, method, raw, headers, waterfall)


class BDPanClient:

    def __init__(self):
        self.access_token = None
        self.refresh_token = None
        self.expire_time = 0
        self.cache = {}

    def __request(self, url, params, method='GET', raw=False, headers=None, waterfall=False):
        return request(atoken=self.access_token, rtoken=self.refresh_token, etime=self.expire_time, url=url, params=params, method=method, raw=raw, headers=headers, waterfall=waterfall)

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

    def quota(self):
        res = self.__request(BaiDu.QUOTA, {}, 'GET')
        return res

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
        # 下载目录不存在则先创建
        path = Env.PHYSICS_DIR + meta.path
        _d = path[:path.rindex('/')]
        if not os.path.isdir(_d):
            os.makedirs(_d)
        ''' 
        如果文件不存在，则直接加入下载队列
        如果文件已经存在，并且服务器修改时间和本地记录一致，则直接读取
        如果需要读取的字节不够则添加至下载队列等待下载，否则直接返回
        '''
        while not os.path.exists(path):
            pass
        return self.__read_file(path, start, size)

    @staticmethod
    def __read_file(path, start, size):
        with open(path, 'rb') as f:
            while f.seek(start) == -1 and os.path.getsize(path) < (start + size - 1):
                pass
            return f.read(size)


def do_process_download_file(atoken, rtoken, etime):
    while True:
        task_info = download_task_queue.get(block=True)
        meta = task_info.meta
        info = download_map.get(meta.fs_id, None)
        try:
            if not info:
                info = DownloadInfo(block=Env.DEFAULT_BLOCK_SIZE, complete_md5=meta.md5, size=meta.size,
                                    touch=datetime.now().timestamp())
                download_map[meta.fs_id] = info
            r = request(atoken=atoken, rtoken=rtoken, etime=etime, url=meta.dlink, params={}, method='GET', raw=True, waterfall=True, headers={
                'Range': 'bytes=%s-%s' % (str(task_info.start + 1), str(task_info.start + task_info.size))})
            with open(Env.PHYSICS_DIR + meta.path, 'a+b') as f:
                for b in r.iter_content(chunk_size=info.block):
                    info = download_map.get(meta.fs_id, None)
                    if info and info.run_able():
                        f.write(b)
                        info.touch_tmp_size()
                        download_con.put('')
                    else:
                        return
        except Exception as e:
            log.error(e)
        finally:
            download_con.put('')


if __name__ == '__main__':
    bdy = BDPanClient()
    # print(bdy.dir('/PDF文档'))
    print(bdy.info('/PDF文档', '1113487933785121'))
