import os


class Env:
    USER_DIR = os.path.expanduser('~')
    LOGIC_WORK_DIR = '/.bdfs'
    TOKEN_DIR = USER_DIR + LOGIC_WORK_DIR
    PHYSICS_DIR = '/tmp' + LOGIC_WORK_DIR + '/.data'
    TOKEN_FILE = '.access_token'
    TOKEN_PATH = TOKEN_DIR + '/' + TOKEN_FILE
    DEFAULT_BLOCK_SIZE = 5242880  # 必须是512的倍数
    READ_BLOCK_TIME_OUT = 60  # 读取一个块大小的超时时间（秒）
    BLOCK_DOWNLOAD_CHECK_TIME = 0.5  # 块下载校验间隔时间（秒）


class BaiDu:
    _BASE_AUTH_URL = 'https://openapi.baidu.com/oauth/2.0/'

    TOKEN_EXPIRE_THRESHOLD = 86400
    DIR_EXPIRE_THRESHOLD = 3600

    CLIENT_ID = 'Hut06o3KHN8GMGB0gRE0mEWW'
    CLIENT_SECRET = 'sLncjFUE84Xflm0LhGUTF8N4VyM5XNav'
    GET_ACCESS_KEY = _BASE_AUTH_URL + 'token'
    SCOPE = 'basic,netdisk'
    GET_CODE = _BASE_AUTH_URL + 'authorize?client_id=' + CLIENT_ID + '&response_type=code&redirect_uri=oob&scope=basic,netdisk'

    _BASE_API_URL = 'https://pan.baidu.com/'
    LIST = _BASE_API_URL + 'rest/2.0/xpan/file?method=list'
    INFO = _BASE_API_URL + 'rest/2.0/xpan/multimedia?method=filemetas'
    PRE_UPLOAD = _BASE_API_URL + 'rest/2.0/xpan/file?method=precreate'
    UPLOAD = _BASE_API_URL + 'rest/2.0/xpan/file?method=create'
    OPERA = _BASE_API_URL + 'rest/2.0/xpan/file?method=filemanager'
    QUOTA = _BASE_API_URL + 'api/quota'
