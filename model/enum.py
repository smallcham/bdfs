import os


class Env:
    USER_DIR = os.path.expanduser('~')
    LOGIC_WORK_DIR = '/.bdfs'
    WORK_DIR = USER_DIR + LOGIC_WORK_DIR
    PHYSICS_DIR = '/tmp' + LOGIC_WORK_DIR + '/.data'
    PHYSICS_WORK_DIR = '/tmp' + LOGIC_WORK_DIR
    TOKEN_FILE = '.access_token'
    META_FILE = '.file_meta'
    CLOUD_HOME = '/apps/bdfs'
    TOKEN_PATH = WORK_DIR + '/' + TOKEN_FILE
    META_PATH = PHYSICS_WORK_DIR + '/' + META_FILE
    PID_PATH = WORK_DIR + '/' + '.pid'
    DEFAULT_BLOCK_SIZE = 5242880  # 必须是512的倍数
    DEFAULT_UPLOAD_BLOCK_SIZE = 5242880
    READ_BLOCK_TIME_OUT = 60  # 读取一个块大小的超时时间（秒）
    BLOCK_DOWNLOAD_CHECK_TIME = 0.5  # 块下载校验间隔时间（秒）
    EMPTY_FILE_FLAG = b'btf'


class BaiDu:
    _BASE_AUTH_URL = 'https://openapi.baidu.com/oauth/2.0/'

    TOKEN_EXPIRE_THRESHOLD = 86400
    DIR_EXPIRE_THRESHOLD = 3600

    CLIENT_ID = 'Hut06o3KHN8GMGB0gRE0mEWW'
    CLIENT_SECRET = 'sLncjFUE84Xflm0LhGUTF8N4VyM5XNav'
    # CLIENT_ID = 'uFBSHEwWE6DD94SQx9z77vgG'
    # CLIENT_SECRET = '7w6wdSFsTk6Vv586r1W1ozHLoDGhXogD'
    GET_ACCESS_KEY = _BASE_AUTH_URL + 'token'
    SCOPE = 'basic,netdisk'
    GET_CODE = _BASE_AUTH_URL + 'authorize?client_id=' + CLIENT_ID + '&response_type=code&redirect_uri=oob&scope=basic,netdisk'

    _BASE_API_URL = 'https://pan.baidu.com/'
    LIST = _BASE_API_URL + 'rest/2.0/xpan/file?method=list'
    INFO = _BASE_API_URL + 'rest/2.0/xpan/multimedia?method=filemetas'
    PRE_UPLOAD = _BASE_API_URL + 'rest/2.0/xpan/file?method=precreate'
    UPLOAD = _BASE_API_URL + 'rest/2.0/xpan/file?method=create'
    UPLOAD_SLICE = 'https://d.pcs.baidu.com/rest/2.0/pcs/superfile2'
    OPERA = _BASE_API_URL + 'rest/2.0/xpan/file?method=filemanager'
    UINFO = _BASE_API_URL + 'rest/2.0/xpan/nas?method=uinfo'
    QUOTA = _BASE_API_URL + 'api/quota'
