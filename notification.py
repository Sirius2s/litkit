import requests
import os
# import smtplib
# from email.mime.text import MIMEText
import time
import json


#######################
# 通知服务
#######################

needYou2Know = 1   # [0,1,2]  0:不通知     1:server酱      2:SMTP邮件服务

SCKEY = ''        # Server酱的SCKEY
QQ_SKEY = ''    # CoolPush的KEY
QYWX_AM = ''    # 企业微信应用的KEY
QMSG_KEY = ''  # QMSG的KEY

# email_dict = {
#     "sender": '',                 # ① sender是邮件发送人邮箱
#     "passWord": '',               # ② passWord是服务器授权码
#     "mail_host": 'smtp.qq.com',   # ③ mail_host是服务器地址（这里是QQsmtp服务器）
#     "port": 465,                  # ④ QQsmtp服务器的端口号为465或587
#     "receiver": ''                # ⑤ receiver是邮件接收人
# }
##################################################################

def n0(a, b):
    """空函数,即不使用通知服务"""
    print(">>>>未开启通知服务")
    return

# def send_email(subject, msg_content):
#     """SMTP邮件服务,暂不支持读取Secrets"""
#     if not email_dict["sender"]:
#         print("SMTP服务的未设置!!\n取消推送")
#         return
#     print("SMTP服务启动")
#     mail_host = email_dict["mail_host"]
#     mail_user = email_dict["sender"]
#     mail_pass = email_dict["passWord"]
#     sender = mail_user
#     receiver = email_dict["receiver"]
#     message = MIMEText(msg_content, 'plain', 'utf-8')
#     message['From'] = sender
#     message['To'] = receiver
#     message['Subject'] = subject
#     try:
#         smtpObj = smtplib.SMTP_SSL(mail_host, email_dict["port"])  # ssl加密
#         # smtpObj = smtplib.SMTP(mail_host, 25)                    # 明文发送
#         smtpObj.login(mail_user, mail_pass)
#         print("邮件登录成功")
#         smtpObj.sendmail(sender, receiver, message.as_string())
#         smtpObj.quit()
#         print("邮件发送成功")
#     except smtplib.SMTPException as e:
#         print("Error: 无法发送邮件", e)


def serverJ(title, content):
    """server酱服务"""
    sckey = SCKEY
    if "PUSH_KEY" in os.environ:
        """
        判断是否运行自GitHub action,"PUSH_KEY" 该参数与 repo里的Secrets的名称保持一致
        """
        sckey = os.environ["PUSH_KEY"]

    if not sckey:
        print("server酱服务的PUSH_KEY未设置!!\n取消推送")
        return
    print("serverJ服务启动")
    data = {
        "text": title,
        "desp": content
    }
    response = requests.post(f"https://sc.ftqq.com/{sckey}.send", data=data)
    print(response.text)

def CoolPush(title, content):
    """CoolPush服务"""
    qqskey = QQ_SKEY
    if "QQ_SKEY" in os.environ:
        """
        判断是否运行自GitHub action,"QQ_SKEY" 该参数与 repo里的Secrets的名称保持一致
        """
        qqskey = os.environ["QQ_SKEY"]

    if not qqskey:
        print("CoolPush服务的QQ_SKEY未设置!!\n取消推送")
        return
    print("CoolPush服务启动")
    # data = f"{title}\n\n{content}"
    response = requests.post(f"https://push.xuthus.cc/send/{qqskey}?c={title}\n\n{content}")#, data=data)
    print(response.text)
    # print(os.environ.values)

def qywxamNotify(title, content):
    """企业微信应用消息服务"""
    qywxam = QYWX_AM
    if "QYWX_AM" in os.environ:
        """
        判断是否运行自GitHub action,"QYWX_AM" 该参数与 repo里的Secrets的名称保持一致
        """
        qywxam = os.environ["QYWX_AM"]

    if not qywxam:
        print("企业微信应用服务的KEY未设置!!\n取消推送")
        return
    print("企业微信应用服务启动")

    QYWX_AM_AY = qywxam.split(',')
    # 获取token开始
    options_accesstoken = {
        'url': 'https://qyapi.weixin.qq.com/cgi-bin/gettoken',
        'json': {
            'corpid': QYWX_AM_AY[0],
            'corpsecret': QYWX_AM_AY[1],
        },
        'headers': {
            'Content-Type': 'application/json',
        },
    }
    # req = requests.post(url, params=options_accesstoken)
    req = requests.post(options_accesstoken['url'], params=options_accesstoken['json'])
    data = json.loads(req.text)
    accesstoken = data["access_token"]
    # 获取token结束

    # 准备数据开始
    html = content.replace('\n', "<br/>")
    options_textcard = {
        'url': f'https://qyapi.weixin.qq.com/cgi-bin/message/send?access_token={accesstoken}',
        'json': {
            'touser': QYWX_AM_AY[2],
            'agentid': QYWX_AM_AY[3],
            'msgtype': 'textcard',
            'textcard': {
                'title': title,
                'description': content,
                'url': '127.0.0.1',
                'btntxt': '更多'
            },
            'safe':'0',
        },
        'headers': {
            'Content-Type': 'application/json',
        },
    }
    options_mpnews = {
        'url': f'https://qyapi.weixin.qq.com/cgi-bin/message/send?access_token={accesstoken}',
        'json': {
            'touser': QYWX_AM_AY[2],
            'agentid': QYWX_AM_AY[3],
            'msgtype': 'mpnews',
            'mpnews': {
                'articles': [
                    {
                        'title': title,
                        'thumb_media_id': QYWX_AM_AY[4],
                        'author' : '智能助手',
                        'content_source_url': '',
                        'content' : html,
                        'digest': content
                    }
                ]
            },
            'safe':'0',
        },
        'headers': {
            'Content-Type': 'application/json',
        },
    }
    # 准备数据结束

    if QYWX_AM_AY[4] == 0:
        response = requests.post(options_textcard['url'], json.dumps(options_textcard['json']))
    else:
        response = requests.post(options_mpnews['url'], json.dumps(options_mpnews['json']))

    print(response.text)

def QMSG(title, content):
    """QMSG服务"""
    qmsgkey = QMSG_KEY
    if "QMSG_KEY" in os.environ:
        """
        判断是否运行自GitHub action,"QMSG_KEY" 该参数与 repo里的Secrets的名称保持一致
        """
        qmsgkey = os.environ["QMSG_KEY"]

    if not qmsgkey:
        print("QMSG服务的QMSG_KEY未设置!!\n取消推送")
        return
    print("QMSG服务启动")
    # data = f"{title}\n\n{content}"
    data = {
    #     'msg': '标题:{}\n内容:{}'.format(title, content)
        'msg': f"{title}\n\n{content}"
    }
    response = requests.post(f"https://qmsg.zendee.cn/send/{qmsgkey}", data=data) #data=data.encode("utf-8"))
    print(response.text)
    # print(os.environ.values)

notify = [n0, serverJ][needYou2Know]
notify_CoolPush = [n0, CoolPush][needYou2Know]
notify_QW_AM = [n0, qywxamNotify][needYou2Know]
notify_QMSG = [n0, QMSG][needYou2Know]

if __name__ == "__main__":
    print("通知服务测试")
    start = time.time()
    # notify("脚本通知服务", "needYou2Know\n\n通知服务测试")
    # notify_CoolPush("脚本通知服务", "needYou2Know\n\n通知服务测试")
    # url = f"{os.environ['GITHUB_SERVER_URL']}/{os.environ['GITHUB_REPOSITORY']}/actions/runs/{os.environ['GITHUB_RUN_ID']}?check_suite_focus=true"
    # notify_QW_AM("脚本通知服务", url)
    notify_QMSG("脚本通知服务", "needYou2Know\n\n通知服务测试")
    # notify_QW_AM("脚本通知服务", "needYou2Know\n\n通知服务测试")
    print("耗时: ", time.time()-start, "s")