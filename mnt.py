import errno
import stat

import pyfuse3
import trio
import os
import logging
import random
from datetime import datetime
from lib.bdy import BDPanClient, download_map
from model.entity import BDFile
from model.enum import Env

log = logging.getLogger(__name__)

# try:
#     import faulthandler
# except ImportError:
#     pass
# else:
#     faulthandler.enable()

tmp_suffix = ['~', '.swo', '.swp', 'swx']


class BDfs(pyfuse3.Operations):
    def init(self):
        super(BDfs).__init__()
        self.fs = BDPanClient()

    async def lookup(self, parent_inode, name, ctx):
        # if name == '.' or name == '..' or name == '/':
        #     return self.getattr(parent_inode, ctx)
        f = BDFile.get_from_inode_name(parent_inode, name)
        if not f:
            raise pyfuse3.FUSEError(errno.ENOENT)
        return await self.getattr(f.fs_id, ctx)
        # return await super().lookup(parent_inode, name, ctx)

    async def forget(self, inode_list):
        return await super().forget(inode_list)

    async def getattr(self, inode, ctx):
        """
        这个方法需要返回文件或文件夹的基本信息，实际上inode为文件或文件夹的索引节点
        因为实现的是网盘文件系统，所以此处虽说物理上不一样，但逻辑上是一样的，在这里我用文件的独立标识fs_id作为inode
        根目录没有inode，默认为1，所以此处判断一下如果inode等于根inode的话，直接将返回设置为目录
        :param inode:
        :param ctx:
        :return:
        """
        entry = pyfuse3.EntryAttributes()
        entry.generation = 0
        entry.entry_timeout = 300
        entry.attr_timeout = 300
        if inode == pyfuse3.ROOT_INODE:
            entry.st_mode = (stat.S_IFDIR | 0o755)
            entry.st_nlink = 0
            entry.st_size = 0
        else:
            f = BDFile.get_from_fs_id(inode)
            entry.st_mode = (stat.S_IFDIR | 0o755) if f.isdir else (stat.S_IFREG | 0o755)
            entry.st_size = f.size
            entry.st_nlink = 1
            entry.st_atime_ns = int(f.server_mtime * 1e9)
            entry.st_ctime_ns = int(f.server_ctime * 1e9)
            entry.st_mtime_ns = int(f.server_mtime * 1e9)
            inode = f.fs_id

        entry.st_rdev = 0
        entry.st_blksize = 512
        entry.st_blocks = 1
        entry.st_gid = os.getgid()
        entry.st_uid = os.getuid()
        entry.st_ino = inode
        return entry

    async def setattr(self, inode, attr, fields, fh, ctx):
        f = BDFile.get_from_fs_id(inode)
        if fields.update_size:
            f.size = attr.st_size
        if fields.update_mode:
            pass
        if fields.update_uid:
            pass
        if fields.update_gid:
            pass
        if fields.update_atime:
            f.server_atime = datetime.now().timestamp()
        if fields.update_mtime:
            f.server_mtime = datetime.now().timestamp()
        if fields.update_ctime:
            f.server_ctime = datetime.now().timestamp()
        return await self.getattr(inode, ctx)

    async def readlink(self, inode, ctx):
        return await super().readlink(inode, ctx)

    async def mknod(self, parent_inode, name, mode, rdev, ctx):
        _inode = BDFile.get_from_fs_id(parent_inode)
        if not _inode:
            path = '/'
        else:
            path = _inode.path + '/'
        if Env.CLOUD_HOME not in path:
            raise pyfuse3.FUSEError(errno.EACCES)
        if not os.path.isdir(Env.PHYSICS_DIR + path):
            os.makedirs(Env.PHYSICS_DIR + path)
        name_bytes = name
        name = name.decode('utf-8')

        file_path = Env.PHYSICS_DIR + path + name
        if is_tmp(name):
            with open(file_path, 'wb') as f:
                f.write(b'')
            inode = random.randint(0, 9999999999999999999)
            ns = (datetime.now().timestamp() * 1e9)
            self.fs.cache[path]['items'].append(
                BDFile(isdir=False, server_ctime=ns, server_mtime=ns, local_ctime=ns, local_mtime=ns, fs_id=inode,
                       path=path if path == '/' else _inode.path, filename=name, filename_bytes=name_bytes, size=0))
            return await self.getattr(inode, ctx)

        with open(file_path, 'wb') as f:
            f.write(b'bdfs tmp file')
        fs_id = self.fs.upload(parent_inode, file_path, path + name)
        if fs_id:
            return await self.getattr(fs_id, ctx)
        raise pyfuse3.FUSEError(errno.EAGAIN)

    async def mkdir(self, parent_inode, name, mode, ctx):
        if parent_inode == pyfuse3.ROOT_INODE:
            path = '/'
        else:
            f = BDFile.get_from_fs_id(parent_inode)
            path = f.path
        inode = self.fs.mkdir(parent_inode, path, name.decode('utf-8'))
        if not inode:
            raise pyfuse3.FUSEError(errno.EEXIST)
        return await self.getattr(inode, ctx)

    async def unlink(self, parent_inode, name, ctx):
        self.__rm(parent_inode, name)

    async def rmdir(self, parent_inode, name, ctx):
        self.__rm(parent_inode, name)

    async def symlink(self, parent_inode, name, target, ctx):
        return await super().symlink(parent_inode, name, target, ctx)

    async def rename(self, parent_inode_old, name_old, parent_inode_new, name_new, flags, ctx):
        name_new = name_new.decode('utf-8')
        name_old = name_old.decode('utf-8')
        if parent_inode_old == parent_inode_new:
            self.fs.rename(parent_inode_old, name_old, name_new)
        else:
            self.fs.mv(parent_inode_old, name_old, parent_inode_new, name_new)

    async def link(self, inode, new_parent_inode, new_name, ctx):
        return await super().link(inode, new_parent_inode, new_name, ctx)

    async def open(self, inode, flags, ctx):
        # if flags & os.O_RDWR or flags & os.O_WRONLY:
        #     raise pyfuse3.FUSEError(errno.EPERM)
        return pyfuse3.FileInfo(fh=inode)

    async def read(self, fh, off, size):
        f = BDFile.get_from_fs_id(fh)
        if not f:
            return b''
        else:
            res = self.fs.download(f, off, size)
            return res

    async def write(self, fh, off, buf):
        node = BDFile.get_from_fs_id(fh)
        file_path = Env.PHYSICS_DIR + node.path
        while True:
            return await self.__do_write(node, file_path, off, buf)

    async def __do_write(self, node, file_path, off, buf):
        with open(file_path, 'wb') as f:
            f.seek(off)
            f.write(buf)
        # if buf[len(buf):] == '':
        #     self.fs.upload(node.p_inode, file_path, node.path)
        return len(buf)

    async def flush(self, fh):
        return await super().flush(fh)

    async def release(self, fh):
        download_map[fh] = None

    async def fsync(self, fh, datasync):
        return await super().fsync(fh, datasync)

    async def opendir(self, inode, ctx):
        return inode

    async def readdir(self, fh, start_id, token):
        """
        读取目录信息，这个方法会被频繁调用
        所以为了防止百度因为频繁请求封了账号这里加缓存默认1个小时更新保险一点，默认值在entity.Env里可以调整
        缺点就是网页版或者客户端中的更新就不会那么实时了
        因为这个方法会不断的被执行， 所以这里需要加文件列表数量校验
        调试中看来start_id会一直更新，除非切换了inode也就是参数上的fh，（fh逻辑上算是唯一标识，相当于切换了目录的话，start_id就会从0开始）
        需要注意的是这里的inode实际上并不一定是文件系统理解中的inode，但逻辑上是一样的，每个目录和文件都需要有inode。
        此处根目录没有，所以做判断 如果fh(inode) = 根inode 则默认获取根目录列表
        :param fh: fh(inode) 逻辑上的inode，用作文件或文件夹的唯一标识
        :param start_id: start_id 是 pyfuse3.readdir_reply 的最后一个参数，会作为未来的readdir调用参数传入， 应当用作读取区间的标识，
        上层不会一次性读取所有的值， 而是会分多次调用readdir，传入start_id 取不同的区间，实现上需要从start_id开始读取到目录最大下标， 需要注意这点
        :param token:
        :return:
        """
        f = BDFile.get_from_fs_id(fh)
        files = self.fs.dir_cache('/' if not f else f.path, pyfuse3.ROOT_INODE if not f else f.fs_id)
        max_len = len(files)
        for i in range(start_id, max_len):
            pyfuse3.readdir_reply(token, files[i].filename_bytes, await self.getattr(files[i].fs_id, None), i + 1)

    async def releasedir(self, fh):
        return await super().releasedir(fh)

    async def fsyncdir(self, fh, datasync):
        return await super().fsyncdir(fh, datasync)

    async def statfs(self, ctx):
        stat_ = pyfuse3.StatvfsData()
        quota = self.fs.quota()
        stat_.f_bsize = 512  # 块大小
        stat_.f_frsize = 512  # 碎片块大小
        size = quota.total
        stat_.f_blocks = size // stat_.f_frsize  # 块总数
        stat_.f_bfree = quota.free // stat_.f_bsize  # 剩余块数
        stat_.f_bavail = stat_.f_bfree  # 非特权用户可使用的块数

        inodes = quota.free / 512
        stat_.f_files = inodes  # 索引节点总数
        stat_.f_ffree = max(inodes, 100)  # 可产生索引节点数
        stat_.f_favail = stat_.f_ffree  # 非特权用户可产生索引节点数
        return stat_

    def stacktrace(self):
        super().stacktrace()

    async def setxattr(self, inode, name, value, ctx):
        return await super().setxattr(inode, name, value, ctx)

    async def getxattr(self, inode, name, ctx):
        return await super().getxattr(inode, name, ctx)

    async def listxattr(self, inode, ctx):
        return await super().listxattr(inode, ctx)

    async def removexattr(self, inode, name, ctx):
        return await super().removexattr(inode, name, ctx)

    async def access(self, inode, mode, ctx):
        return True

    async def create(self, parent_inode, name, mode, flags, ctx):
        return await super().create(parent_inode, name, mode, flags, ctx)

    def __rm(self, p_inode, name):
        self.fs.rm(p_inode, name)

def is_tmp(name):
    for suffix in tmp_suffix:
        if name.endswith(suffix):
            return True
    return False

def init_logging(debug=False):
    formatter = logging.Formatter('%(asctime)s.%(msecs)03d %(threadName)s: '
                                  '[%(name)s] %(message)s', datefmt="%Y-%m-%d %H:%M:%S")
    handler = logging.StreamHandler()
    handler.setFormatter(formatter)
    root_logger = logging.getLogger()
    if debug:
        handler.setLevel(logging.DEBUG)
        root_logger.setLevel(logging.DEBUG)
    else:
        handler.setLevel(logging.INFO)
        root_logger.setLevel(logging.INFO)
    root_logger.addHandler(handler)


if __name__ == '__main__':
    init_logging(debug=True)
    fs = BDfs()
    fuse_options = set(pyfuse3.default_options)
    fuse_options.add('fsname=bdfs')
    fuse_options.discard('default_permissions')
    pyfuse3.init(fs, '/home/wangzhanzhi/test', fuse_options)

    try:
        trio.run(pyfuse3.main)
    except Exception as e:
        pyfuse3.close(unmount=False)
        raise
    pyfuse3.close()
