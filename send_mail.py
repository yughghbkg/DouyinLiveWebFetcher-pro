import ssl
import smtplib
from email.mime.text import MIMEText
from email.utils import formatdate

# ========== 用户配置 ==========
SMTP_HOST = "smtp.qq.com"
SMTP_PORT = 465
SENDER     = ""
RECIPIENT  = ""
AUTH_CODE  = ""
SUBJECT    = "抖音弹幕下载挂了"
BODY       = "断连超过五次，请尝试手动重连"

# ========== 构造邮件 ==========
msg = MIMEText(BODY, "plain", "utf-8")
msg["Subject"] = SUBJECT
msg["From"]    = SENDER
msg["To"]      = RECIPIENT
msg["Date"]    = formatdate(localtime=True)

# ========== 发送邮件 ==========
context = ssl.create_default_context()

# 不使用 with，这样我们可以手动控制 quit/close 的异常处理
server = smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, context=context, timeout=30)
server.set_debuglevel(1)

try:
    server.login(SENDER, AUTH_CODE)
    server.sendmail(SENDER, [RECIPIENT], msg.as_string())
    print(">>> 邮件已经成功提交到服务器队列，请检查收件箱/垃圾箱。")
except Exception as e:
    print(">>> 发送邮件时出错：", e)

# 尝试优雅退出，如果报错则忽略
try:
    server.quit()
except Exception as e:
    print(">>> QUIT 阶段返回异常（可安全忽略）：", repr(e))
    try:
        server.close()
    except:
        pass
