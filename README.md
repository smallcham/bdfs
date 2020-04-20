## **BDFS**（基于百度云盘的虚拟文件系统）![](https://img.shields.io/badge/build-dev--0.1-green)

------

#### **BDFS**是以Python3实现基于百度云盘2.0版本接口的虚拟文件系统，目标是做到与本地文件系统无差别的操作方式。
> 由于百度网盘长时间没有Linux版本，刚没多久发布的Linux版本客户端Bug也很多，登录一次之后再也无法登录。我个人日常会有一些文档需要在家和公司来回倒腾很不方便，所以干脆就实现了这个文件系统，相当于本地多了块好几个T的云硬盘。在实现文件系统的各种功能中对逻辑和速度有一些取舍，而且百度的接口是HTTP的，所以大家对速度不要有太多的幻想，当然会员也会快很多。

------

#### 操作演示视频

[![](https://smallcham.github.io/static/img/bdfs-demo.png)](https://smallcham.github.io/static/video/bdfs-demo.mp4)

------

#### 操作演示截图

![](https://smallcham.github.io/static/img/bdfs-demo2.png)

![](https://smallcham.github.io/static/img/bdfs-demo3.png)

------
#### 注意事项
- 需要注意的是，由于百度接口的限制，无法在 `/apps (/我的应用)` 之外创建文件（创建文件实际上由上传接口抽象过来的，该接口无法上传至根目录），但是你可以操作移动，创建文件夹等操作， apps目录下会有其它的一些应用生成的文件夹，为了整洁的目录结构，我已将权限限制至 `/apps/bdfs/` 你在这个目录下拥有bdfs的所有权限。
- 目录列表的加载我加了缓存，请求过一次的目录一个小时之后才会再次请求百度，一是避免太频繁被百度封了，二是提高响应速度，在文件系统内的操作都会更新缓存，当然你也可以在 `enum.py` 中修改默认值。
- 文件系统默认的配置目录是`~/.bdfs` 默认临时文件目录是 `/tmp/.bdfs` 读取过一次的文件和文件拷贝会在临时文件目录缓存或中转，重启后自动丢失。
- 如果你要用窗体文件管理器打开文件，请使用列表视图，因为文件管理器会尝试读取文件的部分字节获取缩略图等等信息，这将会导致多个文件的读取（下载）被触发，相当的慢。

------

## 使用方法
1. 首先你需要编译 [libfuse](https://github.com/libfuse/libfuse) ，编译方法里面都有, bdfs 是基于fuse实现的虚拟文件系统，所以你必须编译fuse库。
2. 下载bdfs项目 `git clone https://github.com/smallcham/bdfs.git`
3. 进入到项目目录安装项目依赖执行 `pip3 install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple/` 参数 -i 指定为清华的源，因为国内连pypi实在太慢了
4. 建立软链接 `sudo ln -s /项目路径/mnt.py /usr/bin/bdfs && sudo chmod +x /usr/bin/bdfs`
5. 挂载 `bdfs mount 挂载路径` 例如： bdfs mount ~/baidupan

> 执行这些安装命令的时候可能会提示找不到libfuse.so库，遇到了不要紧张，使用命令 `whereis libfuse` 找到编译好的`so`文件 如：`libfuse3.so`，将其链接到提示找不到的目录就好了。

- **Q: 如何后台启动?**
- **A: `nohup bdfs mount 挂载路径 &`**

- **Q: 如何取消挂载？**
- **A: `bdfs umount 挂载路径`** 

------

### 目前已实现的功能（普通文件操作基本已经实现，应该能满足大部分情况下的正常使用）
    读、写、删除、重命名、移动、复制、创建文件夹、创建文件

### 尚未实现的功能
    权限（目前权限默认是755）
    软链接（你可以从bdfs外部与bdfs建立软链接，内部软链接暂未实现）
        
### 尚未修复的问题
    1. 文件修改后回写正常，但是读取内容有问题，重新挂载后为正常修改后的值。
    > 这个问题是由于百度网盘上传文件后文件的唯一标识会改变，与当前文件系统的整体的设计稍有冲突，该问题尚待解决。