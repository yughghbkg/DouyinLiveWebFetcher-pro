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
        base_path = sys._MEIPASS
    else:
        base_path = os.path.dirname(__file__)
    return os.path.join(base_path, relative_path)


def execute_js(js_file: str):
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


def generateMsToken(length=182):
    random_str = ''
    base_str = string.ascii_letters + string.digits + '-_'
    _len = len(base_str) - 1
    for _ in range(length):
        random_str += base_str[random.randint(0, _len)]
    return random_str


class DouyinLiveWebFetcher:

    def _trim_tmp_log(self, keep_lines=500):
        try:
            if not os.path.exists(self.tmp_log_path):
                return

            with open(self.tmp_log_path, "r", encoding="utf-8") as f:
                lines = f.readlines()

            if len(lines) > keep_lines:
                with open(self.tmp_log_path, "w", encoding="utf-8") as f:
                    f.writelines(lines[-keep_lines:])

                print(f"【√】tmp.log 已瘦身，只保留最后 {keep_lines} 行")
                self._tmp_log(f"【√】tmp.log 已瘦身，只保留最后 {keep_lines} 行")
        except Exception as e:
            print(f"【X】tmp.log 瘦身失败: {e}")
            self._tmp_log(f"【X】tmp.log 瘦身失败: {e}")

    def __init__(self, live_id, abogus_file='a_bogus.js', log_dir='logs'):

        self.heartbeat_interval = 10
        self.abogus_file = abogus_file
        self.__ttwid = None
        self.__room_id = None
        self.session = requests.Session()
        self.live_id = live_id
        self.host = "https://www.douyin.com/"
        self.live_url = "https://live.douyin.com/"
        self.user_agent = (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"
        )
        self.headers = {'User-Agent': self.user_agent}

        self._running = False
        self._disconnect_count = 0
        self._mail_sent = False

        if log_dir and os.path.isabs(log_dir):
            self.log_dir = log_dir
        else:
            if getattr(sys, 'frozen', False):
                base_dir = os.path.dirname(sys.executable)
            else:
                base_dir = os.path.dirname(__file__)

            self.log_dir = os.path.join(base_dir, "formal_logs")

        os.makedirs(self.log_dir, exist_ok=True)

        self._log_file = None
        self._log_session_start = None

        # 临时日志路径
        if getattr(sys, 'frozen', False):
            base_dir = os.path.dirname(sys.executable)
        else:
            base_dir = os.path.dirname(__file__)
        self.tmp_log_path = os.path.join(base_dir, "tmp.log")

    def _tmp_log(self, msg: str):
        """写入临时日志（非直播类消息）"""
        try:
            with open(self.tmp_log_path, "a", encoding="utf-8") as f:
                f.write(msg + "\n")
        except:
            pass

    def _ensure_log_file(self, now_str: str):
        if self._log_file is None:
            safe_name = now_str.replace(":", "-").replace(" ", "_")
            filename = f"{safe_name}.txt"
            full_path = os.path.join(self.log_dir, filename)

            self._log_file = open(full_path, "a", encoding="utf-8", buffering=1)
            self._log_session_start = now_str

            msg = f"【日志】本场直播日志文件: {full_path}"
            print(msg)
            self._tmp_log(msg)

            self._trim_tmp_log()

    def _log(self, line: str, now_str: str = None):
        try:
            if now_str is None:
                now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            self._ensure_log_file(now_str)

            if self._log_file:
                self._log_file.write(line + "\n")
                self._log_file.flush()
                os.fsync(self._log_file.fileno())

        except Exception as e:
            msg = f"【日志写入失败】{e}"
            print(msg)
            self._tmp_log(msg)
    def _close_log_file(self):
        if self._log_file:
            try:
                self._log_file.close()
            except:
                pass
        self._log_file = None
        self._log_session_start = None

    def start(self, retry_interval=5):
        self._running = True
        while self._running:
            try:
                self._connectWebSocket()
            except Exception as e:
                if not self._running:
                    break
                msg = f"【X】WebSocket异常: {e}"
                print(msg)
                self._tmp_log(msg)

            if self._running:
                self._disconnect_count += 1
                msg = f"【!】连接已断开，第 {self._disconnect_count} 次，{retry_interval} 秒后尝试重连..."
                print(msg)
                self._tmp_log(msg)

                if self._disconnect_count > 5 and not self._mail_sent:
                    self._notify_disconnect()

                time.sleep(retry_interval)

    def _notify_disconnect(self):
        self._mail_sent = True
        try:
            base_dir = os.path.dirname(os.path.abspath(__file__))
            script_path = os.path.join(base_dir, 'send_mail.py')

            subprocess.Popen(
                [sys.executable, script_path],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )

            msg = "【!】断联次数超过 5 次，已触发邮件通知脚本 send_mail.py"
            print(msg)
            self._tmp_log(msg)

        except Exception as e:
            msg = f"【X】触发邮件通知失败: {e}"
            print(msg)
            self._tmp_log(msg)

    def stop(self):
        self._running = False
        self._close_log_file()

        try:
            if hasattr(self, "ws") and self.ws:
                self.ws.close()
        except:
            pass

    @property
    def ttwid(self):
        if self.__ttwid:
            return self.__ttwid
        headers = {"User-Agent": self.user_agent}
        try:
            resp = self.session.get(self.live_url, headers=headers)
            resp.raise_for_status()
        except Exception as err:
            msg = f"【X】Request the live url error: {err}"
            print(msg)
            self._tmp_log(msg)
        else:
            self.__ttwid = resp.cookies.get('ttwid')
            return self.__ttwid

    @property
    def room_id(self):
        if self.__room_id:
            return self.__room_id

        url = self.live_url + self.live_id
        headers = {
            "User-Agent": self.user_agent,
            "cookie": f"ttwid={self.ttwid}&msToken={generateMsToken()}; __ac_nonce=0123407cc00a9e438deb4",
        }

        try:
            resp = self.session.get(url, headers=headers)
            resp.raise_for_status()
        except Exception as err:
            msg = f"【X】Request the live room url error: {err}"
            print(msg)
            self._tmp_log(msg)
        else:
            match = re.search(r'roomId\\":\\"(\d+)\\"', resp.text)
            if match is None or len(match.groups()) < 1:
                msg = "【X】No match found for roomId"
                print(msg)
                self._tmp_log(msg)

            self.__room_id = match.group(1)
            return self.__room_id

    def get_ac_nonce(self):
        return self.session.get(self.host, headers=self.headers).cookies.get("__ac_nonce")

    def get_ac_signature(self, __ac_nonce: str = None) -> str:
        sig = get__ac_signature(self.host[8:], __ac_nonce, self.user_agent)
        self.session.cookies.set("__ac_signature", sig)
        return sig

    def get_a_bogus(self, url_params: dict):
        url = urllib.parse.urlencode(url_params)
        ctx = execute_js(self.abogus_file)
        return ctx.call("get_ab", url, self.user_agent)

    def get_room_status(self):
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
        url += f"&a_bogus={self.get_a_bogus(params)}"

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
            msg = f"【{nickname}】[{user_id}]直播间：{['正在直播','已结束'][bool(room_status)]}."
            print(msg)
            self._tmp_log(msg)
    def _connectWebSocket(self):
        wss = (
            "wss://webcast100-ws-web-lq.douyin.com/webcast/im/push/v2/?app_name=douyin_web"
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
            f"&need_persist_msg_count=15&insert_task_id=&live_reason=&room_id={self.room_id}&heartbeatDuration=0"
        )

        signature = generateSignature(wss)
        wss += f"&signature={signature}"

        headers = {
            "cookie": f"ttwid={self.ttwid}",
            'user-agent': self.user_agent,
        }

        self.ws = websocket.WebSocketApp(
            wss,
            header=headers,
            on_open=self._wsOnOpen,
            on_message=self._wsOnMessage,
            on_error=self._wsOnError,
            on_close=self._wsOnClose
        )

        try:
            self.ws.run_forever()
        except Exception as e:
            msg = f"【X】run_forever 异常: {e}"
            print(msg)
            self._tmp_log(msg)
            raise

    def _sendHeartbeat(self):
        while self._running:
            try:
                heartbeat_frame = WebcastImPushFrame(
                    payload_type="hb"
                ).SerializeToString()

                self.ws.send(heartbeat_frame, websocket.ABNF.OPCODE_BINARY)

                now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                self._tmp_log(f"【心跳】发送业务心跳包 [{now}]")   

                print(f"【√】发送业务心跳包 [{now}]")

                time.sleep(self.heartbeat_interval)

            except Exception as e:
                print(f"【X】心跳发送失败: {e}")
                break

    def _wsOnOpen(self, ws):
        msg = "【√】WebSocket连接成功."
        print(msg)
        self._tmp_log(msg)
        threading.Thread(target=self._sendHeartbeat).start()

    def _wsOnMessage(self, ws, message):
        package = WebcastImPushFrame().parse(message)
        response = WebcastImResponse().parse(gzip.decompress(package.payload))

        # 如果服务器下发了新的心跳间隔，这里会自动同步
        # if hasattr(response, "heartbeat_duration") and response.heartbeat_duration > 0:
        #     self.heartbeat_interval = response.heartbeat_duration / 1000.0
        #     print(f"【√】服务器心跳间隔: {self.heartbeat_interval} 秒")

        if response.need_ack:
            ack = WebcastImPushFrame(
                log_id=package.log_id,
                payload_type='ack',
                payload=response.internal_ext.encode('utf-8')
            ).SerializeToString()
            ws.send(ack, websocket.ABNF.OPCODE_BINARY)

        # 新 protobuf 的消息字段名是 messages（不是 messages_list）
        for msg in response.messages:
            method = msg.method

            # 旧 method 名（兼容历史）
            # 新 method 名（WebcastImXXXXXMessage）
            handlers = {
                'WebcastImChatMessage': self._parseChatMsg,
                'WebcastImGiftMessage': self._parseGiftMsg,
                'WebcastImLikeMessage': self._parseLikeMsg,
                'WebcastImMemberMessage': self._parseMemberMsg,
                'WebcastImSocialMessage': self._parseSocialMsg,
                'WebcastImRoomUserSeqMessage': self._parseRoomUserSeqMsg,
                'WebcastImFansclubMessage': self._parseFansclubMsg,
                'WebcastImControlMessage': self._parseControlMsg,
                'WebcastImEmojiChatMessage': self._parseEmojiChatMsg,
                'WebcastImRoomStatsMessage': self._parseRoomStatsMsg,
                'WebcastImRoomMessage': self._parseRoomMsg,
                'WebcastImRoomRankMessage': self._parseRankMsg,
                'WebcastImRoomStreamAdaptationMessage': self._parseRoomStreamAdaptationMsg,

                # 兼容旧 method 字符串（抖音旧协议）
                'WebcastChatMessage': self._parseChatMsg,
                'WebcastGiftMessage': self._parseGiftMsg,
                'WebcastLikeMessage': self._parseLikeMsg,
                'WebcastMemberMessage': self._parseMemberMsg,
                'WebcastSocialMessage': self._parseSocialMsg,
                'WebcastRoomUserSeqMessage': self._parseRoomUserSeqMsg,
                'WebcastFansclubMessage': self._parseFansclubMsg,
                'WebcastControlMessage': self._parseControlMsg,
                'WebcastEmojiChatMessage': self._parseEmojiChatMsg,
                'WebcastRoomStatsMessage': self._parseRoomStatsMsg,
                'WebcastRoomMessage': self._parseRoomMsg,
                'WebcastRoomRankMessage': self._parseRankMsg,
                'WebcastRoomStreamAdaptationMessage': self._parseRoomStreamAdaptationMsg,
            }

            handler = handlers.get(method)
            if handler:
                try:
                    handler(msg.payload)
                except Exception as e:
                    print(f"【X】解析 {method} 失败: {e}")
            else:
                # Debug：如果遇到没处理的消息类型，可以看到具体名称
                print(f"【?】未处理的消息类型: {method}")
                pass

    def _wsOnError(self, ws, error):
        msg = f"WebSocket error: {error}"
        print(msg)
        self._tmp_log(msg)

    def _wsOnClose(self, ws, *args):
        self.get_room_status()
        msg = "WebSocket connection closed."
        print(msg)
        self._tmp_log(msg)

    def _parseChatMsg(self, payload):
        message = WebcastImChatMessage().parse(payload)
        user_name = message.user.nickname
        user_id = message.user.id
        content = message.content
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        line = f"【聊天msg】[{user_id}] {user_name}: {content} [{now}]"
        print(line)
        self._log(line, now)

    def _parseGiftMsg(self, payload):
        message = WebcastImGiftMessage().parse(payload)
        user_name = message.user.nickname
        gift_name = message.gift.name
        gift_cnt = message.combo_count
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        line = f"【礼物msg】{user_name} 送出了 {gift_name}x{gift_cnt} [{now}]"
        print(line)
        self._log(line, now)

    def _parseLikeMsg(self, payload):
        message = WebcastImLikeMessage().parse(payload)
        user_name = message.user.nickname
        count = message.count
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        line = f"【点赞msg】{user_name} 点了{count}个赞 [{now}]"
        print(line)
        self._log(line, now)
    def _parseMemberMsg(self, payload):
        message = WebcastImMemberMessage().parse(payload)
        user_name = message.user.nickname
        user_id = message.user.id
        gender = ["女", "男"][message.user.gender]
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        line = f"【进场msg】[{user_id}][{gender}] {user_name} 进入了直播间 [{now}]"
        print(line)
        self._log(line, now)

    def _parseSocialMsg(self, payload):
        message = WebcastImSocialMessage().parse(payload)
        user_name = message.user.nickname
        user_id = message.user.id
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        line = f"【关注msg】[{user_id}]{user_name} 关注了主播 [{now}]"
        print(line)
        self._log(line, now)

    def _parseRoomUserSeqMsg(self, payload):
        message = WebcastImRoomUserSeqMessage().parse(payload)
        current = message.total
        total = message.total_pv_for_anchor
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        line = f"【统计msg】当前观看人数: {current}, 累计观看人数: {total} [{now}]"
        print(line)
        self._log(line, now)

    def _parseFansclubMsg(self, payload):
        message = WebcastImFansclubMessage().parse(payload)
        content = message.content
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        line = f"【粉丝团msg】{content} [{now}]"
        print(line)
        self._log(line, now)

    def _parseEmojiChatMsg(self, payload):
        message = WebcastImEmojiChatMessage().parse(payload)
        emoji_id = message.emoji_id
        user_name = message.user.nickname
        user_id = message.user.id
        default_content = message.default_content or "发送了表情"

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        line = f"【聊天表情包msg】[{user_id}] {user_name}: {default_content} (emoji_id={emoji_id}) [{now}]"
        print(line)
        self._log(line, now)

    def _parseRoomMsg(self, payload):
        message = WebcastImRoomMessage().parse(payload)
        common = message.common
        room_id = common.room_id
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        line = f"【直播间msg】直播间id:{room_id} [{now}]"
        print(line)
        self._tmp_log(line)

    def _parseRoomStatsMsg(self, payload):
        message = WebcastImRoomStatsMessage().parse(payload)
        display_long = message.display_long
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        line = f"【直播间统计msg】{display_long} [{now}]"
        print(line)
        self._tmp_log(line)

    def _parseRankMsg(self, payload):
        message = WebcastImRoomRankMessage().parse(payload)
        ranks_list = message.ranks
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        simple = []
        for i, item in enumerate(ranks_list, start=1):
            nick = item.user.nickname
            score = getattr(item, "score_str", "")
            simple.append(f"{i}. {nick} {score}".strip())

        line = "【直播间排行榜msg】" + " | ".join(simple) + f" [{now}]"
        print(line)
        if self._log_file:
            self._log(line, now) #未直播的时候不触发开播
        else:
            self._tmp_log(line)


    def _parseControlMsg(self, payload):
        message = WebcastImControlMessage().parse(payload)
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        if message.status == 3:
            line = f"【控制msg】直播间已结束 [{now}]"
            print(line)
            self._log(line, now)
            self.stop()

    def _parseRoomStreamAdaptationMsg(self, payload):
        message = WebcastImRoomStreamAdaptationMessage().parse(payload)
        adaptationType = message.adaptation_type

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        line = f"【直播间流适配msg】adaptationType={adaptationType} [{now}]"
        print(line)
        self._tmp_log(line)
