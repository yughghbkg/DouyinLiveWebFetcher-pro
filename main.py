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

    # 如果你想指定一个绝对路径，例如：
    # log_dir = r"D:\douyin_logs"
    # 否则就留空：log_dir = ""  写相对路径和其他任何字符是无效的
    log_dir = ""

    room = DouyinLiveWebFetcher(live_id, log_dir=log_dir)
    room.start()


