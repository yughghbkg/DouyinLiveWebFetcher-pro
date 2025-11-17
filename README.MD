**正在适配  最新proto抖音弹幕解析方法  目前原始数据获取有误 大佬们有兴趣一起研究下**

万分感谢 @Remember-the-past 大佬帮忙适配 和提供的最新proto


**使用方法**

**安装 Python3.10      用vs code打开main.py      点击右上角的播放键运行程序      在下方控制栏里输入 python -m pip install -r requirements.txt   安装好，再点击右上角播放键运行程序，应该就能跑了   打包就按下面的来打包就行**

1.添加# python -m pip install -r requirements.txt 注释 方便首次运行 

2. 几乎所有消息添加时间搓 

3.排行榜和表情消息爆炸问题解决

4.更新重连机制

5.断联超过五次 邮件提醒 发送邮件的脚本我已经写好了，就是在./send_mail.py 我现在的状态是直接双击它就可以自动发送一封邮件，发送什么，你别管，反正就调用它就行

6.每次（从收到弹幕一直到直播状态变换为截止）输出到./formal_logs/日期.txt 并且可以控制哪些需要，哪些不需要写到正式日志(需要自己模仿着改一下代码) 支持相对目录和绝对目录(需要改一下注释)

7.增加心跳日志，即使后台运行，也能确保程序运行

8.为打包做适配，并且打包成 exe step2(需要手动操作) 按照打包教程 v2 完成前面的操作

特殊步骤： 找到你的 Python 环境里的 mini_racer.dll：where python（找到 Python 安装路径） 找到 C:\Users\user\AppData\Local\Programs\Python\Python310\Lib\site-packages\py_mini_racer\mini_racer.dll

在 auto-py-to-exe → Additional Files → Add Files 里加入： C:\Users\user\AppData\Local\Programs\Python\Python310\Lib\site-packages\py_mini_racer\icudtl.dat C:\Users\user\AppData\Local\Programs\Python\Python310\Lib\site-packages\py_mini_racer\snapshot_blob.bin

高级选项--add-binary C:\Users\user\AppData\Local\Programs\Python\Python310\Lib\site-packages\py_mini_racer\mini_racer.dll

最后的打包指令 pyinstaller --noconfirm --onedir --console --add-data "E:\DouyinLiveWebFetcher-1.8\a_bogus.js;." --add-data "E:\DouyinLiveWebFetcher-1.8\sign.js;." --add-data "E:\DouyinLiveWebFetcher-1.8\sign_v0.js;." --add-data "E:\DouyinLiveWebFetcher-1.8\webmssdk.js;." --add-data "E:\DouyinLiveWebFetcher-1.8\protobuf;protobuf/" --add-binary "C:\Users\user\AppData\Local\Programs\Python\Python310\Lib\site-packages\py_mini_racer\mini_racer.dll;." --add-data "C:\Users\user\AppData\Local\Programs\Python\Python310\Lib\site-packages\py_mini_racer\snapshot_blob.bin;." --add-data "C:\Users\user\AppData\Local\Programs\Python\Python310\Lib\site-packages\py_mini_racer\icudtl.dat;." "E:\DouyinLiveWebFetcher-1.8\main.py"

9.去掉隐私
10.填上实际的 准备部署
11.正式日志问题 把mini_racer需要的那4个文件添加进来

12.生成的弹幕文件可以在 vs code 里面及时刷新

13.完全分类 print 的消息分为直播的消息丢到正式日志，其他的东西丢到临时日志

14.修复日志混乱的 bug  心跳改为业务心跳

15.添加临时日志瘦身功能

16.【直播间排行榜msg】不触发开播，因为未直播的时候也会刷新






2.0  更新新的proto并适配 解决顽疾

【礼物msg】xxx 送出了 暮光星辰x1 [2025-11-16 22:10:27]  后面的礼物数量也不对     

然后就是直播结束的时候，会马上终结程序，不会再守护了  这个应该能自己解决

还有即使是提前打开直播的时候，他也不会接收弹幕消息。等于这个保和机制或者是抖音，根本就不存在这个机制必须完全的重连，而不是保活，是重连之后探测重连。有没有这个必须要参考其他项目怎么做的，一些录播项目，怎么做的

像这种连续的就不应该统计成连续的呀，连机的那应该统计他最后的  这个在礼物统计里面可以改





单独添加一个py脚本  专门统计每一场直播的数据 存储在一个新文档命名就是读取的那个文本的日期，再加上两个字总结就行
直播结束之后 

读取gift_clean.json 还有本场直播的正式日志 计算出本场直播获得的礼物的价值的钻石 每10分钟为平均列一行数据列出来 并且最后说明总礼物价值的钻石

读取正式日志中的【统计msg】当前观看人数: 6, 累计观看人数: 561 [2025-11-16 10:16:55] 每10分钟为平均列一行数据列出来 并且在最后说明观看总人数，这个应该在正式日志的最后有统计，你把它给直接抄上来就行

读取正式日志中的聊天 message 每10分钟为平均列一行数据列出来 并且在最后说明总的聊天 message 数量

在线时长超过10分钟的观众以礼物为第一排序 点赞数量为第二排序 聊天 message 以第三排序 在线时长为第四排序 并且列出表格，写在之后就行 用csv格式就是两个数据之间用tab空格

识别异常的数据就堆在这个新的文本文档的最后，比如说识别不到的礼物呀，还有所有异常的数据都放到最后就行



