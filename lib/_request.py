import os
from model.enum import BaiDu, Env
from datetime import datetime
import json
import webbrowser
import requests
from util import stream
import logging

log = logging.getLogger(__name__)


def do_request(url, params, data=None, method='GET', raw=False, headers=None, waterfall=False, files=None):
    if headers is None:
        headers = {}
    try:
        headers.update({'User-Agent': 'pan.baidu.com'})
        data = None if not data else data.encode('utf-8')
        res = requests.request(method, url, params=params, data=data,
                               headers=headers, stream=waterfall, files=files)
        if res is not None and res.status_code == 403:
            headers.update({'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Ubuntu Chromium/80.0.3987.163 Chrome/80.0.3987.163 Safari/537.36'})
            res = requests.request(method, url, params=params, data=data,
                                   headers=headers, stream=waterfall, files=files)
        if raw:
            return res
        else:
            res = res.json()
            if res.get('error', '') == 'expired_token' or res.get('error_code', 0) == 31626:
                stream.print_error('access token is expired or error please reauthorize.')
                atoken, rtoken, etime = get_token()
                return do_request(url=url, params=params, method=method, headers={'access_token': atoken}, waterfall=waterfall, files=files)
            return res
    except Exception as e:
        log.error(e)
        return None if raw else {}


def get_token(access_token=None, refresh_token=None, expire_time=None):
    """
    获取token， 并将token存放于 ~/.bdfs/.access_token 文件中(可以在enum中修改默认值)
    如果token过期时间低于阈值则执行刷新
    :return:
    """
    if access_token and refresh_token:
        if expire_time - datetime.now().timestamp() < BaiDu.TOKEN_EXPIRE_THRESHOLD:
            return r_token(refresh_token)  # token过期时间低于阈值则执行刷新
        return access_token, refresh_token, expire_time
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
        if not os.path.isdir(Env.WORK_DIR):
            os.mkdir(Env.WORK_DIR)
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


def request(atoken, rtoken, etime, url, params, data, method='GET', raw=False, headers=None, waterfall=False, files=None):
    params['access_token'] = get_token(atoken, rtoken, etime)[0]
    return do_request(url, params, data, method, raw, headers, waterfall, files)
