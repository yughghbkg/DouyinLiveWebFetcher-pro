#!/usr/bin/python
# coding:utf-8
# python -m pip install -r requirements.txt


# @FileName:    main.py
# @Time:        2024/1/2 22:27
# @Author:      bubu
# @Project:     douyinLiveWebFetcher

from liveMan import DouyinLiveWebFetcher
import os  

if __name__ == '__main__':
    live_id = ''

    #log_dir = r".\formal_logs"
    base_dir = os.path.dirname(os.path.abspath(__file__))   # main.py 所在目录
    log_dir = os.path.join(base_dir, "formal_logs")         # 保证永远写到项目内部

    room = DouyinLiveWebFetcher(live_id, log_dir=log_dir)
    room.start()

