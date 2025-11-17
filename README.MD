**正在适配  最新proto抖音弹幕解析方法  目前原始数据获取有误 大佬们有兴趣一起研究下**


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

