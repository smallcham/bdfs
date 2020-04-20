import os
from lib._request import *
from datetime import datetime
from model.enum import BaiDu, Env
from model.entity import BDFile, BDMeta, TaskInfo, BDQuota, BDUser
import uuid
import logging
import hashlib
from urllib3 import encode_multipart_formdata
import json

log = logging.getLogger(__name__)

download_map = {}


class BDPanClient:

    def __init__(self):
        self.access_token, self.refresh_token, self.expire_time = get_token()
        self.cache = {}
        self.meta_cache = {}

    def __request(self, url, params, data=None, method='GET', raw=False, headers=None, waterfall=False, files=None):
        return request(atoken=self.access_token, rtoken=self.refresh_token, etime=self.expire_time, url=url,
                       params=params, data=data, method=method, raw=raw, headers=headers, waterfall=waterfall,
                       files=files)

    def uinfo(self):
        return BDUser.user if not BDUser.need_flush() else BDUser.from_json(self.__request(BaiDu.UINFO, {}))

    def dir(self, d='/', inode=None):
        """
        从百度云盘获取文件列表
        :param inode:
        :param d: 路径
        :return:
        """
        res = self.__request(BaiDu.LIST, {'dir': d}, 'GET')
        return BDFile.from_json_list(res.get('list', []), inode)

    def dir_cache(self, d='/', inode=None, expire=BaiDu.DIR_EXPIRE_THRESHOLD, force=False):
        """
        根据路径从缓存中获取文件列表，如果缓存中没有或缓存超时，则从百度云盘获取后加入缓存并返回列表
        :param force: 强制刷新缓存
        :param inode:
        :param d: 路径
        :param expire: 缓存过期时间（秒）
        :return:
        """
        res = {} if force else self.cache.get(d, {})
        items = res.get('items', None)
        _expire = res.get('expire', -1)
        if (_expire != -1 and datetime.now().timestamp() > _expire) or not items:
            self.cache[d] = {
                'items': self.dir(d, inode),
                'expire': -1 if expire == -1 else datetime.now().timestamp() + expire
            }
        return self.cache[d]['items']

    def info_cache(self, path, fsid, force=False):
        res = None if force else self.meta_cache.get(path, None)
        if not res:
            res = self.info(path, fsid)
            self.meta_cache[path] = res
        return res

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

    def upload(self, p_inode, file_path, upload_path):
        f_size = os.path.getsize(file_path)
        if f_size == 0:
            return False
        slice_size = self.uinfo().slice_size()
        file_md5s = []
        with open(file_path, 'rb') as f:
            res = f.read(slice_size)
            while res != b'':
                file_md5 = hashlib.md5(res).hexdigest()
                file_md5s.append(file_md5)
                f.seek(f.tell())
                res = f.read(slice_size)
        block_list = '["' + '","'.join(file_md5s) + '"]'
        res = self.__request(BaiDu.PRE_UPLOAD, {}, data='path=%s&size=%s&isdir=0&autoinit=1&rtype=3&block_list=%s' % (
            upload_path, f_size, block_list), method='POST')
        if res.get('errno', -1) != 0:
            return False
        if res.get('return_type', -1) == 2:
            return True
        fs_id = self.__upload_slice(f_size, file_path, slice_size, upload_path, res.get('block_list', []),
                                    res.get('uploadid', None))
        if not fs_id:
            return False
        self.dir_cache(upload_path[:upload_path.rindex('/')], p_inode, force=True)
        return fs_id

    def __upload_slice(self, f_size, file_path, slice_size, upload_path, block_list, uploadid):
        md5s = []
        block_list = [0] if len(block_list) == 0 else block_list
        for block in block_list:
            with open(file_path, 'rb') as f:
                res = self.__request(BaiDu.UPLOAD_SLICE, {
                    'method': 'upload',
                    'type': 'tmpfile',
                    'path': upload_path,
                    'uploadid': uploadid,
                    'partseq': block
                }, files={'file': f.read(slice_size)}, method='POST')
                f.seek(f.tell())
                _md5 = res.get('md5', None)
                if not _md5:
                    return False
                md5s.append(res.get('md5', None))
        res = self.__request(BaiDu.UPLOAD, params={},
                             data='path=%s&isdir=0&size=%s&rtype=3&block_list=["%s"]' % (
                             upload_path, f_size, '","'.join(md5s)),
                             method='POST')
        return res.get('fs_id', False)

    def mkdir(self, p_inode, path, name):
        res = self.__request(BaiDu.UPLOAD, params={}, data='path=%s&isdir=1&rtype=3&block_list=[]' % (path + name),
                             method='POST')
        self.dir_cache(path, p_inode, force=True)
        return res.get('fs_id', None)

    def rm(self, p_inode, name):
        f = BDFile.get_from_inode_name(p_inode, name)
        if not f:
            return
        self.__rm_with_path(f.path)
        BDFile.clear_f_cache(p_inode, f)
        rdx = f.path.rindex('/')
        path = '/' if rdx == 0 else f.path[:rdx]
        self.dir_cache(path, p_inode, force=True)

    def __rm_with_path(self, *files):
        _files = 'async=0&filelist=["' + '","'.join(files) + '"]'
        return self.__opera('delete', _files)

    def rename(self, p_inode_old, name_old, name_new):
        f = BDFile.get_from_inode_name(p_inode_old, name_old)
        path = '/' if p_inode_old == 1 else f.path + '/'
        self.__rename(path + name_old, name_new)
        BDFile.clear_f_cache(p_inode_old, f)
        self.dir_cache(path, p_inode_old, force=True)

    def __rename(self, path, new_name):
        return self.__opera('rename',
                            'async=0&filelist=[{"path":"%s","dest":"%s","newname":"%s","ondup":"newcopy"}]' % (
                                path, path[path.rindex('/'):], new_name))

    def mv(self, p_inode_old, name_old, p_inode_new, name_new):
        old_f = BDFile.get_from_inode_name(p_inode_old, name_old)
        new_path = '/'
        if p_inode_new == 1:
            self.__mv_with_path(old_f.path, new_path, name_new)
        else:
            new_f = BDFile.get_from_fs_id(p_inode_new)
            if new_f is not None:
                new_path = new_f.path
                self.__mv_with_path(old_f.path, new_path, name_new)
            BDFile.clear_f_cache(p_inode_new, new_f)
        BDFile.clear_f_cache(p_inode_old, old_f)
        rdx = old_f.path.rindex('/')
        path = '/' if rdx == 0 else old_f.path[:rdx]
        self.dir_cache(path, p_inode_old, force=True)
        self.dir_cache(new_path, p_inode_new, force=True)

    def __mv_with_path(self, path, new_path, new_name=None):
        return self.__opera('move',
                            'async=0&filelist=[{"path":"%s","dest":"%s","newname":"%s","ondup":"newcopy"}]' % (
                                path, new_path, new_name if new_name else path[path.rindex('/'):]
                            ))

    def __opera(self, opera, files):
        res = self.__request(BaiDu.OPERA, {
            'opera': opera
        }, data=files, method='POST')
        return res.get('errno', -1) == 0

    def quota(self):
        return BDQuota.from_json(self.__request(BaiDu.QUOTA, {}, 'GET'))

    '''
    从百度云按字节数下载文件
    如果size为 -1 则表示从start开始下载到最后
    '''
    def download(self, f, start, size):
        meta = self.info_cache(f.path, f.fs_id)
        return self.__download(meta, start, size)

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
        info = TaskInfo(meta=meta, start=start, size=size)
        download_map[meta.fs_id] = info
        return self.__do_download_file(info)

    def __do_download_file(self, task_info):
        info = download_map.get(task_info.meta.fs_id, None)
        _real_path = Env.PHYSICS_DIR + task_info.meta.path
        try:
            if not info:
                return b''
            '''
            文件大小已经足够,则直接返回需要读取的字节区间
            '''
            # need_flush(task_info.meta.fs_id, task_info.meta.server_mtime)
            f_size = os.path.getsize(_real_path)
            if f_size >= task_info.meta.size or f_size >= task_info.start + task_info.size:
                download_map[task_info.meta.fs_id] = None
            else:
                self.__do_block_download(_real_path, task_info, f_size)
            return read_file(_real_path, task_info.start, task_info.size)
        except FileNotFoundError as _:
            self.__do_block_download(_real_path, task_info, 0)
            return read_file(_real_path, task_info.start, task_info.size)

    def __do_block_download(self, real_path, task_info, f_size):
        meta = task_info.meta
        with open(real_path, 'a+b') as f:
            '''
            文件起始大小足够,但是要取的size位不足, 则偏移后再进行下载
            此处需要处理客户端程序有多线程读取的情况，如果读取的字节有间隔的情况，此处会偏移至已下载文件的最大值，然后开始下载
            '''
            if f_size < task_info.start:
                _real_start = f_size
                _real_end = task_info.start + (task_info.block if task_info.size < task_info.block else task_info.size)
            else:
                _real_start = f_size if (task_info.start < f_size < task_info.size) else task_info.start
                _real_end = _real_start + (task_info.block if task_info.size < task_info.block else task_info.size)
            if task_info.size == -1:
                _real_end = ''
            try:
                r = self.__request(url=meta.dlink, params={}, method='GET', raw=True, waterfall=True, headers={
                    'Range': 'bytes=%s-%s' % (str(_real_start), str(_real_end))})
                if not r:
                    return
            except Exception as e:
                log.error(str(e))
                return
            for b in r.iter_content(chunk_size=task_info.block):
                info = download_map.get(meta.fs_id, None)
                if info and info.run_able():
                    if os.path.getsize(real_path) < _real_end:
                        f.write(b)
                    else:
                        break
                else:
                    download_map[meta.fs_id] = None
                    break


# def need_flush(fs_id, mtime):
#     try:
#         with open(Env.META_PATH, 'w+t') as f:
#             res = f.read()
#             if not res:
#                 f.write(json.dumps({str(fs_id): mtime}))
#                 return False
#             res = json.loads(res)
#             _mtime = res.get(str(fs_id), None)
#             if not _mtime:
#                 res[str(fs_id)] = mtime
#                 f.write(json.dumps(res))
#                 return False
#             if _mtime < mtime:
#                 res[str(fs_id)] = mtime
#                 f.write(json.dumps(res))
#                 node = BDFile.get_from_fs_id(fs_id)
#                 os.remove(Env.PHYSICS_DIR + '/' + node.filename)
#                 return True
#             return False
#     except FileNotFoundError:
#         os.makedirs(Env.PHYSICS_WORK_DIR)
#         need_flush(fs_id, mtime)


def read_file(real_path, start, size):
    with open(real_path, 'rb') as f:
        f.seek(start)
        return f.read(size)


if __name__ == '__main__':
    client = BDPanClient()
    # print(client.mkdir('/awdad'))
    # print(client.rm('/aaa.ser'))
    # print(client.rename('/haha.ser', 'payload.ser'))
    client.upload('/home/wangzhanzhi/work_temp/IMG_20191018_160034.png', '/apps/bdfs/aaa.png')
