import errno
import stat

import pyfuse3
import trio
import os
import logging
from lib.bdy import BDPanClient, download_map
from model.entity import BDFile

log = logging.getLogger(__name__)

# try:
#     import faulthandler
# except ImportError:
#     pass
# else:
#     faulthandler.enable()


class BDfs(pyfuse3.Operations):
    def init(self):
        super(BDfs).__init__()
        self.fs = BDPanClient()
        self.files = []

    async def lookup(self, parent_inode, name, ctx):
        # if name == '.' or name == '..' or name == '/':
        #     return self.getattr(parent_inode, ctx)
        f = BDFile.get_from_name(name)
        if not f:
            raise pyfuse3.FUSEError(errno.ENOENT)
        return self.getattr(f.fs_id, ctx)
        # return await super().lookup(parent_inode, name, ctx)

    async def forget(self, inode_list):
        return await super().forget(inode_list)

    async def getattr(self, inode, ctx):
        """
        这个方法需要返回文件或文件夹的基本信息，实际上inode为文件或文件夹的索引节点
        因为实现的是网盘文件系统，所以此处虽说物理上不一样，但逻辑上是一样的，在这里我用文件的独立标识fs_id作为inode
        根目录没有inode，默认为1，所以此处判断一下如果inode等于根inode的话，直接将返回设置为目录就好了
        :param inode:
        :param ctx:
        :return:
        """
        entry = pyfuse3.EntryAttributes()
        if inode == pyfuse3.ROOT_INODE:
            entry.st_mode = (stat.S_IFDIR | 0o755)
            entry.st_size = 0
        else:
            f = BDFile.get_from_fs_id(inode)
            entry.st_mode = (stat.S_IFDIR | 0o755) if f.isdir else (stat.S_IFREG | 0o644)
            entry.st_size = f.size
            entry.st_atime_ns = f.server_mtime
            entry.st_ctime_ns = f.server_ctime
            entry.st_mtime_ns = f.server_mtime
            inode = f.fs_id

        entry.st_gid = os.getgid()
        entry.st_uid = os.getuid()
        entry.st_ino = inode
        return entry
        # return await super().getattr(inode, ctx)

    async def setattr(self, inode, attr, fields, fh, ctx):
        return await super().setattr(inode, attr, fields, fh, ctx)

    async def readlink(self, inode, ctx):
        return await super().readlink(inode, ctx)

    async def mknod(self, parent_inode, name, mode, rdev, ctx):
        return await super().mknod(parent_inode, name, mode, rdev, ctx)

    async def mkdir(self, parent_inode, name, mode, ctx):
        return await super().mkdir(parent_inode, name, mode, ctx)

    async def unlink(self, parent_inode, name, ctx):
        return await super().unlink(parent_inode, name, ctx)

    async def rmdir(self, parent_inode, name, ctx):
        return await super().rmdir(parent_inode, name, ctx)

    async def symlink(self, parent_inode, name, target, ctx):
        return await super().symlink(parent_inode, name, target, ctx)

    async def rename(self, parent_inode_old, name_old, parent_inode_new, name_new, flags, ctx):
        return await super().rename(parent_inode_old, name_old, parent_inode_new, name_new, flags, ctx)

    async def link(self, inode, new_parent_inode, new_name, ctx):
        return await super().link(inode, new_parent_inode, new_name, ctx)

    async def open(self, inode, flags, ctx):
        if flags & os.O_RDWR or flags & os.O_WRONLY:
            raise pyfuse3.FUSEError(errno.EPERM)
        return pyfuse3.FileInfo(fh=inode)
        # return await super().open(inode, flags, ctx)

    async def read(self, fh, off, size):
        f = BDFile.fs_pool.get(fh, None)
        if not f:
            return b''
        else:
            return self.fs.download(f, off, size)

    async def write(self, fh, off, buf):

        return await super().write(fh, off, buf)

    async def flush(self, fh):
        return await super().flush(fh)

    async def release(self, fh):
        info = download_map.get(fh, None)
        if info:
            info.shutdown()
            download_map[fh] = None
        else:
            return
        # return await super().release(fh)

    async def fsync(self, fh, datasync):
        return await super().fsync(fh, datasync)

    async def opendir(self, inode, ctx):
        # return await super().opendir(inode, ctx)
        return inode

    async def readdir(self, fh, start_id, token):
        """
        总算搞清楚了，这个方法会一直执行不断的更新目录信息
        所以为了防止百度因为频繁请求封了账号这里加缓存默认1个小时更新保险一点
        缺点就是网页版或者客户端中的更新就不会那么实时了
        因为这个方法会不断的被执行， 所以这里需要加文件列表数量校验
        调试中看来start_id会一直更新，除非切换了inode也就是参数上的fh，（fh逻辑上算是唯一标识，相当于切换了目录的话，start_id就会从0开始）
        需要注意的是这里的inode实际上并不一定是文件系统理解中的inode，但逻辑上是一样的，每个目录和文件都需要有inode。
        此处根目录没有，所以做判断 如果fh(inode) = 根inode 则默认获取根目录列表
        :param fh: fh(inode) 逻辑上的inode，用作文件或文件夹的唯一标识
        :param start_id: start_id会从0开始一直更新 + 1，除非切换了inode也就是参数上的fh
        :param token:
        :return:
        """
        if fh == pyfuse3.ROOT_INODE:
            self.files = self.fs.dir_cache('/', pyfuse3.ROOT_INODE)
            # BDFile.set_inode(pyfuse3.ROOT_INODE, self.files)
        else:
            f = BDFile.get_from_fs_id(fh)
            self.files = self.fs.dir_cache(f.path, fh)
            # BDFile.set_inode(fh, self.files)
        if start_id < len(self.files):
            for f in self.files:
                pyfuse3.readdir_reply(token, f.filename_bytes, await self.getattr(f.fs_id, None), f.fs_id)
        return
        # return await super().readdir(fh, start_id, token)

    async def releasedir(self, fh):
        return await super().releasedir(fh)

    async def fsyncdir(self, fh, datasync):
        return await super().fsyncdir(fh, datasync)

    async def statfs(self, ctx):
        return await super().statfs(ctx)

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
        return await super().access(inode, mode, ctx)

    async def create(self, parent_inode, name, mode, flags, ctx):
        return await super().create(parent_inode, name, mode, flags, ctx)


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
    # fuse_options.discard('default_permissions')
    pyfuse3.init(fs, '/home/wangzhanzhi/test', fuse_options)

    try:
        trio.run(pyfuse3.main)
    except:
        pyfuse3.close(unmount=False)
        raise
    pyfuse3.close()
