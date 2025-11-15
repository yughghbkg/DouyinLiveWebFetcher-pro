#!/usr/bin/python
# coding:utf-8

# @FileName:    liveMan.py
# @Time:        2024/1/2 21:51
# @Author:      bubu
# @Project:     douyinLiveWebFetcher

import codecs
import gzip
import hashlib
import random
import re
import string
import subprocess
import threading
import time
from datetime import datetime
import os
import sys
import execjs
import urllib.parse
from contextlib import contextmanager
from unittest.mock import patch

import requests
import websocket
from py_mini_racer import MiniRacer

from ac_signature import get__ac_signature
from protobuf.douyin import *

from urllib3.util.url import parse_url





def resource_path(relative_path: str) -> str:
    """
    获取资源文件的实际路径，兼容 PyInstaller 打包后的环境
    """
    if hasattr(sys, '_MEIPASS'):
        # PyInstaller 解包后的临时目录
        base_path = sys._MEIPASS
    else:
        # 源码模式：当前文件所在目录
        base_path = os.path.dirname(__file__)

    return os.path.join(base_path, relative_path)

def execute_js(js_file: str):
    """
    执行 JavaScript 文件
    :param js_file: JavaScript 文件路径（相对名）
    """
    js_path = resource_path(js_file)
    with open(js_path, 'r', encoding='utf-8') as file:
        js_code = file.read()

    ctx = execjs.compile(js_code)
    return ctx


@contextmanager
def patched_popen_encoding(encoding='utf-8'):
    original_popen_init = subprocess.Popen.__init__
    
    def new_popen_init(self, *args, **kwargs):
        kwargs['encoding'] = encoding
        original_popen_init(self, *args, **kwargs)
    
    with patch.object(subprocess.Popen, '__init__', new_popen_init):
        yield


def generateSignature(wss, script_file='sign.js'):
    """
    出现gbk编码问题则修改 python模块subprocess.py的源码中Popen类的__init__函数参数encoding值为 "utf-8"
    """
    params = ("live_id,aid,version_code,webcast_sdk_version,"
              "room_id,sub_room_id,sub_channel_id,did_rule,"
              "user_unique_id,device_platform,device_type,ac,"
              "identity").split(',')
    wss_params = urllib.parse.urlparse(wss).query.split('&')
    wss_maps = {i.split('=')[0]: i.split("=")[-1] for i in wss_params}
    tpl_params = [f"{i}={wss_maps.get(i, '')}" for i in params]
    param = ','.join(tpl_params)
    md5 = hashlib.md5()
    md5.update(param.encode())
    md5_param = md5.hexdigest()
    
    script_path = resource_path(script_file)
    with codecs.open(script_path, 'r', encoding='utf8') as f:
        script = f.read()
    
    ctx = MiniRacer()
    ctx.eval(script)
    
    try:
        signature = ctx.call("get_sign", md5_param)
        return signature
    except Exception as e:
        print(e)
    
    # 以下代码对应js脚本为sign_v0.js
    # context = execjs.compile(script)
    # with patched_popen_encoding(encoding='utf-8'):
    #     ret = context.call('getSign', {'X-MS-STUB': md5_param})
    # return ret.get('X-Bogus')


def generateMsToken(length=182):
    """
    产生请求头部cookie中的msToken字段，其实为随机的107位字符
    :param length:字符位数
    :return:msToken
    """
    random_str = ''
    base_str = string.ascii_letters + string.digits + '-_'
    _len = len(base_str) - 1
    for _ in range(length):
        random_str += base_str[random.randint(0, _len)]
    return random_str


class DouyinLiveWebFetcher:
    
    def __init__(self, live_id, abogus_file='a_bogus.js', log_dir='logs'):
        """
        直播间弹幕抓取对象
        :param live_id: 直播间的直播id，打开直播间web首页的链接如：https://live.douyin.com/261378947940，
                        其中的261378947940即是live_id
        """
        self.abogus_file = abogus_file
        self.__ttwid = None
        self.__room_id = None
        self.session = requests.Session()
        self.live_id = live_id
        self.host = "https://www.douyin.com/"
        self.live_url = "https://live.douyin.com/"
        self.user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36 Edg/140.0.0.0"
        self.headers = {
            'User-Agent': self.user_agent
        }
        self._running = False
        self._disconnect_count = 0    # 断联次数
        self._mail_sent = False       # 是否已经发过告警邮件
        self.log_dir = log_dir              # 日志目录，可配置
        os.makedirs(self.log_dir, exist_ok=True)
        self._log_file = None               # 当前这场直播对应的文件句柄
        self._log_session_start = None      # 当前直播第一次消息时间（字符串）

    def _ensure_log_file(self, now_str: str):
        """
        确保当前有一个打开的日志文件：
        - 如果没有，就以 now_str 生成一个新文件名
        """
        if self._log_file is None:
            # 用“直播开始第一条消息时间”做文件名：YYYY-MM-DD_HH-MM-SS.txt
            safe_name = now_str.replace(":", "-").replace(" ", "_")
            filename = f"{safe_name}.txt"
            full_path = os.path.join(self.log_dir, filename)

            # 行缓冲写入，避免数据长时间在缓冲区
            self._log_file = open(full_path, "a", encoding="utf-8", buffering=1)
            self._log_session_start = now_str
            print(f"【日志】本场直播日志文件: {full_path}")

    def _log(self, line: str, now_str: str = None):
        """
        写一行日志到当前直播文件
        :param line: 已经格式化好的字符串
        :param now_str: 这条消息的时间字符串，用于第一次创建文件
        """
        try:
            if now_str is None:
                now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self._ensure_log_file(now_str)
            if self._log_file:
                self._log_file.write(line + "\n")
        except Exception as e:
            # 写日志失败不要影响主流程
            print(f"【日志写入失败】{e}")

    def _close_log_file(self):
        """关闭当前这场直播的日志文件"""
        if self._log_file:
            try:
                self._log_file.close()
            except Exception:
                pass
        self._log_file = None
        self._log_session_start = None
    
    def start(self, retry_interval=5):
        """
        启动并自动重连 WebSocket
        :param retry_interval: 断线后重连间隔秒数
        """
        self._running = True
        while self._running:
            try:
                self._connectWebSocket()   # 里面的 run_forever 会阻塞，直到连接关闭
            except Exception as e:
                # 这里的异常一般是网络异常 / run_forever 出错
                if not self._running:
                    # 如果是我们主动 stop() 导致的，就别再重连了
                    break
                print(f"【X】WebSocket异常: {e}")
            
            # 能走到这里，说明连接已经结束（正常关闭或异常退出）
            if self._running:
                self._disconnect_count += 1
                print(f"【!】连接已断开，第 {self._disconnect_count} 次，{retry_interval} 秒后尝试重连...")

                # 断联超过 5 次且还没发过告警邮件 → 触发一次
                if self._disconnect_count > 5 and not self._mail_sent:
                    self._notify_disconnect()

                time.sleep(retry_interval)

    def _notify_disconnect(self):
        """
        断联次数超过阈值时触发一次邮件通知
        """
        self._mail_sent = True
        try:
            base_dir = os.path.dirname(os.path.abspath(__file__))
            script_path = os.path.join(base_dir, 'send_mail.py')

            # 用当前 Python 解释器调用 send_mail.py
            subprocess.Popen(
                [sys.executable, script_path],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            print("【!】断联次数超过 5 次，已触发邮件通知脚本 send_mail.py")
        except Exception as e:
            print("【X】触发邮件通知失败: ", e)

    
    def stop(self):
        """
        主动停止抓取：关闭重连循环 + 关闭当前 WebSocket + 关闭当前日志文件
        """
        self._running = False

        # 新增：关闭日志文件
        self._close_log_file()

        try:
            if hasattr(self, "ws") and self.ws:
                self.ws.close()
        except Exception:
            pass

    
    @property
    def ttwid(self):
        """
        产生请求头部cookie中的ttwid字段，访问抖音网页版直播间首页可以获取到响应cookie中的ttwid
        :return: ttwid
        """
        if self.__ttwid:
            return self.__ttwid
        headers = {
            "User-Agent": self.user_agent,
        }
        try:
            response = self.session.get(self.live_url, headers=headers)
            response.raise_for_status()
        except Exception as err:
            print("【X】Request the live url error: ", err)
        else:
            self.__ttwid = response.cookies.get('ttwid')
            return self.__ttwid
    
    @property
    def room_id(self):
        """
        根据直播间的地址获取到真正的直播间roomId，有时会有错误，可以重试请求解决
        :return:room_id
        """
        if self.__room_id:
            return self.__room_id
        url = self.live_url + self.live_id
        headers = {
            "User-Agent": self.user_agent,
            "cookie": f"ttwid={self.ttwid}&msToken={generateMsToken()}; __ac_nonce=0123407cc00a9e438deb4",
        }
        try:
            response = self.session.get(url, headers=headers)
            response.raise_for_status()
        except Exception as err:
            print("【X】Request the live room url error: ", err)
        else:
            match = re.search(r'roomId\\":\\"(\d+)\\"', response.text)
            if match is None or len(match.groups()) < 1:
                print("【X】No match found for roomId")
            
            self.__room_id = match.group(1)
            
            return self.__room_id
    
    def get_ac_nonce(self):
        """
        获取 __ac_nonce
        """
        resp_cookies = self.session.get(self.host, headers=self.headers).cookies
        return resp_cookies.get("__ac_nonce")
    
    def get_ac_signature(self, __ac_nonce: str = None) -> str:
        """
        获取 __ac_signature
        """
        __ac_signature = get__ac_signature(self.host[8:], __ac_nonce, self.user_agent)
        self.session.cookies.set("__ac_signature", __ac_signature)
        return __ac_signature
    
    def get_a_bogus(self, url_params: dict):
        """
        获取 a_bogus
        """
        url = urllib.parse.urlencode(url_params)
        ctx = execute_js(self.abogus_file)
        _a_bogus = ctx.call("get_ab", url, self.user_agent)
        return _a_bogus
    
    def get_room_status(self):
        """
        获取直播间开播状态:
        room_status: 2 直播已结束
        room_status: 0 直播进行中
        """
        msToken = generateMsToken()
        nonce = self.get_ac_nonce()
        signature = self.get_ac_signature(nonce)
        url = ('https://live.douyin.com/webcast/room/web/enter/?aid=6383'
               '&app_name=douyin_web&live_id=1&device_platform=web&language=zh-CN&enter_from=page_refresh'
               '&cookie_enabled=true&screen_width=5120&screen_height=1440&browser_language=zh-CN&browser_platform=Win32'
               '&browser_name=Edge&browser_version=140.0.0.0'
               f'&web_rid={self.live_id}'
               f'&room_id_str={self.room_id}'
               '&enter_source=&is_need_double_stream=false&insert_task_id=&live_reason=&msToken=' + msToken)
        query = parse_url(url).query
        params = {i[0]: i[1] for i in [j.split('=') for j in query.split('&')]}
        a_bogus = self.get_a_bogus(params)  # 计算a_bogus,成功率不是100%，出现失败时重试即可
        url += f"&a_bogus={a_bogus}"
        headers = self.headers.copy()
        headers.update({
            'Referer': f'https://live.douyin.com/{self.live_id}',
            'Cookie': f'ttwid={self.ttwid};__ac_nonce={nonce}; __ac_signature={signature}',
        })
        resp = self.session.get(url, headers=headers)
        data = resp.json().get('data')
        if data:
            room_status = data.get('room_status')
            user = data.get('user')
            user_id = user.get('id_str')
            nickname = user.get('nickname')
            print(f"【{nickname}】[{user_id}]直播间：{['正在直播', '已结束'][bool(room_status)]}.")
    
    def _connectWebSocket(self):
        """
        连接抖音直播间websocket服务器，请求直播间数据
        """
        wss = ("wss://webcast100-ws-web-lq.douyin.com/webcast/im/push/v2/?app_name=douyin_web"
               "&version_code=180800&webcast_sdk_version=1.0.14-beta.0"
               "&update_version_code=1.0.14-beta.0&compress=gzip&device_platform=web&cookie_enabled=true"
               "&screen_width=1536&screen_height=864&browser_language=zh-CN&browser_platform=Win32"
               "&browser_name=Mozilla"
               "&browser_version=5.0%20(Windows%20NT%2010.0;%20Win64;%20x64)%20AppleWebKit/537.36%20(KHTML,"
               "%20like%20Gecko)%20Chrome/126.0.0.0%20Safari/537.36"
               "&browser_online=true&tz_name=Asia/Shanghai"
               "&cursor=d-1_u-1_fh-7392091211001140287_t-1721106114633_r-1"
               f"&internal_ext=internal_src:dim|wss_push_room_id:{self.room_id}|wss_push_did:7319483754668557238"
               f"|first_req_ms:1721106114541|fetch_time:1721106114633|seq:1|wss_info:0-1721106114633-0-0|"
               f"wrds_v:7392094459690748497"
               f"&host=https://live.douyin.com&aid=6383&live_id=1&did_rule=3&endpoint=live_pc&support_wrds=1"
               f"&user_unique_id=7319483754668557238&im_path=/webcast/im/fetch/&identity=audience"
               f"&need_persist_msg_count=15&insert_task_id=&live_reason=&room_id={self.room_id}&heartbeatDuration=0")
        
        signature = generateSignature(wss)
        wss += f"&signature={signature}"
        
        headers = {
            "cookie": f"ttwid={self.ttwid}",
            'user-agent': self.user_agent,
        }
        self.ws = websocket.WebSocketApp(wss,
                                         header=headers,
                                         on_open=self._wsOnOpen,
                                         on_message=self._wsOnMessage,
                                         on_error=self._wsOnError,
                                         on_close=self._wsOnClose)
        try:
            self.ws.run_forever()
        except Exception as e:
            # 抛给外层的 start()，由它决定是否重连
            print(f"【X】run_forever 异常: {e}")
            raise
    
    def _sendHeartbeat(self):
        """
        发送心跳包
        """
        # 确定日志文件路径：打包后用 exe 目录，开发时用当前文件目录
        if getattr(sys, 'frozen', False):
            base_dir = os.path.dirname(sys.executable)
        else:
            base_dir = os.path.dirname(__file__)

        heartbeat_log_path = os.path.join(base_dir, "heartbeat.log")

        while True:
            try:
                heartbeat = PushFrame(payload_type='hb').SerializeToString()
                self.ws.send(heartbeat, websocket.ABNF.OPCODE_PING)

                # 加时间戳的心跳日志
                now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                msg = f"[{now}] 【√】发送心跳包"

                # 控制台输出（可选，方便调试）
                print(msg)

                # 追加写入心跳日志文件
                with open(heartbeat_log_path, "a", encoding="utf-8") as f:
                    f.write(msg + "\n")

            except Exception as e:
                print("【X】心跳包检测错误: ", e)
                break
            else:
                time.sleep(5)
    
    def _wsOnOpen(self, ws):
        """
        连接建立成功
        """
        print("【√】WebSocket连接成功.")
        threading.Thread(target=self._sendHeartbeat).start()
    
    def _wsOnMessage(self, ws, message):
        """
        接收到数据
        :param ws: websocket实例
        :param message: 数据
        """
        
        # 根据proto结构体解析对象
        package = PushFrame().parse(message)
        response = Response().parse(gzip.decompress(package.payload))
        
        # 返回直播间服务器链接存活确认消息，便于持续获取数据
        if response.need_ack:
            ack = PushFrame(log_id=package.log_id,
                            payload_type='ack',
                            payload=response.internal_ext.encode('utf-8')
                            ).SerializeToString()
            ws.send(ack, websocket.ABNF.OPCODE_BINARY)
        
        # 根据消息类别解析消息体
        for msg in response.messages_list:
            method = msg.method
            try:
                {
                    'WebcastChatMessage': self._parseChatMsg,  # 聊天消息
                    'WebcastGiftMessage': self._parseGiftMsg,  # 礼物消息
                    'WebcastLikeMessage': self._parseLikeMsg,  # 点赞消息
                    'WebcastMemberMessage': self._parseMemberMsg,  # 进入直播间消息
                    'WebcastSocialMessage': self._parseSocialMsg,  # 关注消息
                    'WebcastRoomUserSeqMessage': self._parseRoomUserSeqMsg,  # 直播间统计
                    'WebcastFansclubMessage': self._parseFansclubMsg,  # 粉丝团消息
                    'WebcastControlMessage': self._parseControlMsg,  # 直播间状态消息
                    'WebcastEmojiChatMessage': self._parseEmojiChatMsg,  # 聊天表情包消息
                    'WebcastRoomStatsMessage': self._parseRoomStatsMsg,  # 直播间统计信息
                    'WebcastRoomMessage': self._parseRoomMsg,  # 直播间信息
                    'WebcastRoomRankMessage': self._parseRankMsg,  # 直播间排行榜信息
                    'WebcastRoomStreamAdaptationMessage': self._parseRoomStreamAdaptationMsg,  # 直播间流配置
                }.get(method)(msg.payload)
            except Exception:
                pass
    
    def _wsOnError(self, ws, error):
        print("WebSocket error: ", error)
    
    def _wsOnClose(self, ws, *args):
        self.get_room_status()
        print("WebSocket connection closed.")
    
    def _parseChatMsg(self, payload):
        """聊天消息"""
        message = ChatMessage().parse(payload)
        user_name = message.user.nick_name
        user_id = message.user.id
        content = message.content
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        line = f"【聊天msg】[{user_id}] {user_name}: {content} [{now}]"
        print(line)
        self._log(line, now)
    
    def _parseGiftMsg(self, payload):
        """礼物消息"""
        message = GiftMessage().parse(payload)
        user_name = message.user.nick_name
        gift_name = message.gift.name
        gift_cnt = message.combo_count
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        line = f"【礼物msg】{user_name} 送出了 {gift_name}x{gift_cnt} [{now}]"
        print(line)
        self._log(line, now)
    
    def _parseLikeMsg(self, payload):
        '''点赞消息'''
        message = LikeMessage().parse(payload)
        user_name = message.user.nick_name
        count = message.count
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        line = f"【点赞msg】{user_name} 点了{count}个赞 [{now}]"
        print(line)
        self._log(line, now)
    
    def _parseMemberMsg(self, payload):
        '''进入直播间消息'''
        message = MemberMessage().parse(payload)
        user_name = message.user.nick_name
        user_id = message.user.id
        gender = ["女", "男"][message.user.gender]
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"【进场msg】[{user_id}][{gender}] {user_name} 进入了直播间 [{now}]")
    
    def _parseSocialMsg(self, payload):
        '''关注消息'''
        message = SocialMessage().parse(payload)
        user_name = message.user.nick_name
        user_id = message.user.id
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"【关注msg】[{user_id}]{user_name} 关注了主播 [{now}]")
    
    def _parseRoomUserSeqMsg(self, payload):
        '''直播间统计'''
        message = RoomUserSeqMessage().parse(payload)
        current = message.total
        total = message.total_pv_for_anchor
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"【统计msg】当前观看人数: {current}, 累计观看人数: {total} [{now}]")
    
    def _parseFansclubMsg(self, payload):
        '''粉丝团消息'''
        message = FansclubMessage().parse(payload)
        content = message.content
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"【粉丝团msg】 {content} [{now}]")
    
    def _parseEmojiChatMsg(self, payload):
        '''聊天表情包消息'''
        message = EmojiChatMessage().parse(payload)
        
        emoji_id = message.emoji_id
        user_name = message.user.nick_name
        user_id = message.user.id
        default_content = message.default_content  # 通常是表情对应的文字，比如 "发送了表情" 之类
        
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # 默认文案可能为空，兜一层
        if not default_content:
            default_content = "发送了表情"
        
        # 最终输出格式：跟聊天消息保持类似风格
        line = f"【聊天表情包msg】[{user_id}] {user_name}: {default_content} (emoji_id={emoji_id}) [{now}]"
        print(line)
        self._log(line, now)
    
    def _parseRoomMsg(self, payload):
        message = RoomMessage().parse(payload)
        common = message.common
        room_id = common.room_id
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"【直播间msg】直播间id:{room_id} [{now}]")
    
    def _parseRoomStatsMsg(self, payload):
        message = RoomStatsMessage().parse(payload)
        display_long = message.display_long
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"【直播间统计msg】{display_long} [{now}]")
    
    def _parseRankMsg(self, payload):
        message = RoomRankMessage().parse(payload)
        ranks_list = message.ranks_list
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        simple = []
        for i, item in enumerate(ranks_list, start=1):
            nick = item.user.nick_name
            score = getattr(item, "score_str", "")  # 有些结构里有得分字符串
            simple.append(f"{i}. {nick} {score}".strip())

        print(f"【直播间排行榜msg】" + " | ".join(simple) + f" [{now}]")

    def _parseControlMsg(self, payload):
        '''直播间状态消息'''
        message = ControlMessage().parse(payload)
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        if message.status == 3:
            line = f"【控制msg】直播间已结束 [{now}]"
            print(line)
            # 结束时也记录一条到日志里
            self._log(line, now)
            # 关闭 websocket + 日志文件
            self.stop()
    
    def _parseRoomStreamAdaptationMsg(self, payload):
        message = RoomStreamAdaptationMessage().parse(payload)
        adaptationType = message.adaptation_type
        print(f'直播间adaptation: {adaptationType}')
