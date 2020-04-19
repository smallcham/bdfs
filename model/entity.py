from model.enum import Env, BaiDu
from datetime import datetime

name_pool = {}
fs_pool = {}
inode_pool = {}
inode_name_pool = {}


class BDFile:

    def __init__(self, privacy=None, category=None, unlist=None, isdir=None, oper_id=None, server_ctime=None,
                 local_mtime=None, size=None, filename=None, filename_bytes=None, share=None, path=None,
                 local_ctime=None, server_mtime=None, p_inode=None,
                 fs_id=None):
        self.privacy = privacy
        self.category = category
        self.unlist = unlist
        self.isdir = isdir
        self.oper_id = oper_id
        self.server_ctime = server_ctime
        self.local_mtime = local_mtime
        self.size = size
        self.filename = filename
        self.filename_bytes = filename_bytes
        self.share = share
        self.path = path
        self.local_ctime = local_ctime
        self.server_mtime = server_mtime
        self.fs_id = fs_id
        self.p_inode = p_inode
        fs_pool[self.fs_id] = self
        name_pool[self.filename] = self

    @staticmethod
    def from_json(res):
        privacy = res.get('privacy')
        category = res.get('category')
        unlist = res.get('unlist')
        isdir = res.get('isdir') == 1
        oper_id = res.get('oper_id')
        server_ctime = res.get('server_ctime')
        local_mtime = res.get('local_mtime')
        size = res.get('size')
        filename = res.get('server_filename')
        filename_bytes = None if not filename else filename.encode('utf-8')
        share = res.get('share')
        path = res.get('path')
        local_ctime = res.get('local_ctime')
        server_mtime = res.get('server_mtime')
        fs_id = res.get('fs_id')
        f = BDFile(privacy=privacy, category=category, unlist=unlist, isdir=isdir, oper_id=oper_id,
                   server_ctime=server_ctime, local_mtime=local_mtime, size=size, filename=filename,
                   filename_bytes=filename_bytes, share=share, path=path, local_ctime=local_ctime,
                   server_mtime=server_mtime, fs_id=fs_id)
        fs_pool[f.fs_id] = f
        name_pool[f.filename] = f
        return f

    @staticmethod
    def set_inode(inode, files):
        for f in files:
            name_pool[f.filename] = f
            fs_pool[f.fs_id] = f
        inode_pool[inode] = files

    @staticmethod
    def get_from_name(name):
        return name_pool.get((name.decode('utf-8') if isinstance(name, bytes) else name), None)

    @staticmethod
    def get_from_inode(inode):
        return inode_pool.get(inode, None)

    @staticmethod
    def get_from_inode_name(inode, name):
        return inode_name_pool.get(str(inode) + (name.decode('utf-8') if isinstance(name, bytes) else name),
                                   None)

    @staticmethod
    def get_from_fs_id(fs_id):
        return fs_pool.get(fs_id, None)

    @staticmethod
    def clear_cache():
        fs_pool.clear()
        name_pool.clear()
        inode_name_pool.clear()
        inode_pool.clear()

    @staticmethod
    def clear_f_cache(p_inode, f):
        fs_pool[f.fs_id] = None
        name_pool[f.filename] = None
        inode_name_pool[str(p_inode) + f.filename] = None

    @staticmethod
    def from_json_list(items, inode=None):
        res = []
        for item in items:
            f = BDFile.from_json(item)
            f.p_inode = inode
            res.append(f)
            inode_name_pool[str(inode) + f.filename] = f
        inode = 1 if not inode else inode
        inode_pool[inode] = res
        return res


class BDMeta:
    def __init__(self):
        self.category = None
        self.dlink = None
        self.filename = None
        self.fs_id = None
        self.isdir = None
        self.md5 = None
        self.oper_id = None
        self.path = None
        self.server_ctime = None
        self.server_mtime = None
        self.size = None

    @staticmethod
    def from_json(res):
        meta = BDMeta()
        meta.category = res.get('category', None)
        meta.dlink = res.get('dlink', None)
        meta.filename = res.get('filename', None)
        meta.fs_id = res.get('fs_id', None)
        meta.isdir = res.get('isdir', None)
        meta.md5 = res.get('md5', None)
        meta.oper_id = res.get('oper_id', None)
        meta.path = res.get('path', None)
        meta.server_ctime = res.get('server_ctime', None)
        meta.server_mtime = res.get('server_mtime', None)
        meta.size = res.get('size', None)
        return meta


class TaskInfo:
    def __init__(self, meta=None, start=0, size=0, block=Env.DEFAULT_BLOCK_SIZE):
        self.start = start
        self.size = size
        self.meta = meta
        self.block = block
        self.state = 1

    def shutdown(self):
        self.state = 0

    def run_able(self):
        return self.state == 1


class BDQuota:
    def __init__(self, total=0, used=0):
        self.total = total
        self.used = used
        self.free = total - used

    @staticmethod
    def from_json(res):
        return BDQuota(res.get('total', None), res.get('used', None))


class BDUser:
    user = None

    def __init__(self, baidu_name=None, netdisk_name=None, avatar_url=None, vip_type=None, uk=None):
        self.baidu_name = baidu_name,
        self.netdisk_name = netdisk_name
        self.avatar_url = avatar_url
        self.vip_type = vip_type  # 0普通用户、1普通会员、2超级会员
        self.uk = uk
        self.etime = datetime.now().timestamp() + BaiDu.DIR_EXPIRE_THRESHOLD

    def is_vip(self):
        return self.vip_type == 1

    def is_svip(self):
        return self.vip_type == 2

    def slice_size(self):
        return 33554432 if self.is_svip() else (16777216 if self.is_vip() else 4194304)

    @staticmethod
    def need_flush():
        return True if not BDUser.user or BDUser.user.etime < datetime.now().timestamp() else False

    @staticmethod
    def get_user():
        return BDUser.user

    @staticmethod
    def from_json(res):
        user = BDUser(res.get('baidu_name', None), res.get('netdisk_name', None), res.get('avatar_url', None),
                      res.get('vip_type', None), res.get('uk', None))
        BDUser.user = user
        return BDUser.user
