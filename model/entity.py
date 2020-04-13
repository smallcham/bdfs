from datetime import datetime


class BDFile:
    name_pool = {}
    fs_pool = {}
    inode_pool = {}

    def __init__(self, privacy=None, category=None, unlist=None, isdir=None, oper_id=None, server_ctime=None,
                 local_mtime=None, size=None, filename=None, filename_bytes=None, share=None, path=None,
                 local_ctime=None, server_mtime=None,
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
        BDFile.fs_pool[f.fs_id] = f
        BDFile.name_pool[f.filename] = f
        return f

    @staticmethod
    def set_inode(inode, files):
        for f in files:
            BDFile.name_pool[f.filename] = f
            BDFile.fs_pool[f.fs_id] = f
        BDFile.inode_pool[inode] = files

    @staticmethod
    def get_from_name(name):
        return BDFile.name_pool.get((name.decode('utf-8') if isinstance(name, bytes) else name), None)

    @staticmethod
    def get_from_inode(inode):
        return BDFile.inode_pool.get(inode, None)

    @staticmethod
    def get_from_fs_id(fs_id):
        return BDFile.fs_pool.get(fs_id, None)

    @staticmethod
    def from_json_list(items, inode=None):
        res = []
        for item in items:
            f = BDFile.from_json(item)
            res.append(f)
        inode = 1 if not inode else inode
        BDFile.inode_pool[inode] = res
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


class DownloadInfo:
    def __init__(self, block=0, complete_md5=None, size=0, touch=None):
        self.block = block
        self.complete_md5 = complete_md5
        self.tmp_size = 0
        self.size = size
        self.touch = touch
        self.state = 1

    def shutdown(self):
        self.state = 0

    def run_able(self):
        return self.state == 1

    def touch_tmp_size(self):
        self.tmp_size += self.block
        self.touch = datetime.now().timestamp()


class TaskInfo:
    def __init__(self, meta=None, start=0, size=0):
        self.start = start
        self.size = size
        self.meta = meta
