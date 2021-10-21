import requests
import json
import re
from chinese_calendar import is_workday
import datetime
import log
import notification

header = {
    # 'accept': '*/*',
    # 'accept-encoding': 'gzip, deflate, br',
    # 'accept-language': 'zh-CN,zh;q=0.9',
    # 'Host': 'api.fund.eastmoney.com',
    'Referer': 'http://fundf10.eastmoney.com/',
    # 'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:56.0) Gecko/20100101 Firefox/56.0',
    # 'X-Requested-With': 'XMLHttpRequest'
}
title = '发车'
content = ''


def is_trade_day(date):
    """
    判断是否交易日
    para: date
    return: True/False
    """
    if is_workday(date):
        if date.isoweekday() < 6:
            return True
    return False


def get_trade_day(n):
    """
    获取30个自然日内，过去第n个交易日
    para: n
    return: date
    """
    count = 0
    for i in range(0, 30):  # 30个自然日内
        trade_day = datetime.datetime.now() - datetime.timedelta(days=i)
        if (is_trade_day(trade_day)):
            # print(trade_day))
            if (count == n):  # 过去第n个交易日
                # print(trade_day.date())
                return trade_day.date()
                break
            count = count + 1


def req(url, param, head, trans):
    """
    通用接口
    para: url,param,head,trans
    return: False/response
    """
    try:
        res = requests.get(url, params=param, headers=head)
        if res.status_code != 200:
            log.logger.error("获取失败:%s" % [trans, res.status_code])
            return False
        else:
            return res
    except Exception as e:
        log.logger.error("获取失败:%s" % [trans, e])
        return False


def get_jz(fundCode):
    """
    根据代码获取历史净值
    para: fundCode
    return: False/LSJZList
        ACTUALSYI: ""
        DTYPE: null
        DWJZ: 单位净值
        FHFCBZ: ""
        FHFCZ: ""
        FHSP: ""
        FSRQ: FS日期date
        JZZZL: 净值增长率
        LJJZ: 累计净值
        NAVTYPE: "1"
        SDATE: null
        SGZT: 申购状态
        SHZT: 赎回状态    
    """
    url_jz = 'http://api.fund.eastmoney.com/f10/lsjz'
    param_jz = {
        'fundCode': fundCode,
        'pageIndex': '1',
        'pageSize': '10',  # 获取数量
        'startDate': '',  # 开始日期
        'endDate': ''  # 结束日期
    }
    res_jz = req(url_jz, param_jz, header, 'jz')
    if res_jz == False:
        return res_jz
    else:
        return res_jz.json()['Data']['LSJZList']


def get_gz(fundCode):
    """
    根据代码获取当前估值
    para: fundCode
    return: False/Data
        dwjz: 单位净值
        fundcode: 
        gsz: 估算值
        gszzl: 估算增长率
        gztime: 估算时间datetime
        jzrq: 净值日期date
        name: 
    """
    url_gz = 'http://api.fund.eastmoney.com/fund/fundgz'
    param_gz = {
        'fundCode': fundCode
    }
    res_gz = req(url_gz, param_gz, header, 'gz')
    if res_gz == False:
        return res_gz
    else:
        return res_gz.json()['Data'][0]


def get_pj(fundCode):
    """
    根据代码获取最新一次评级
    para: fundCode
    return: Data/x
        FCODE: fundCode
        HTPJ: ""
        JAPJ: 济安金信评级
        RDATE: 报告日期date
        SZPJ3: 上海证券评级三年期
        ZSPJ: 招商评级
        ZSPJ5: 上海证券评级五年期
    """
    url_pj = 'http://api.fund.eastmoney.com/F10/JJPJ'
    param_pj = {
        'fundCode': fundCode,
        'pageIndex': '1',
        'pageSize': '50'
    }
    res_pj = req(url_pj, param_pj, header, 'pj')
    if res_pj == False:
        return 'x'
    else:
        list_pj = res_pj.json()['Data']
        for item_pj in list_pj:
            if item_pj['HTPJ'] != '':
                return item_pj['HTPJ']
            if item_pj['JAPJ'] != '':
                return item_pj['JAPJ']
            if item_pj['SZPJ3'] != '':
                return item_pj['SZPJ3']
            if item_pj['ZSPJ5'] != '':
                return item_pj['ZSPJ5']
            if item_pj['ZSPJ'] != '':
                return item_pj['ZSPJ']
        return 'x'
        # return res_pj.json()['Data']


def get_gm(fundCode):
    """
    根据代码获取当前规模
    para: fundCode
    return: x/Data
        0: 时间戳
        1: 净资产规模值（亿元）
    """
    url_gm = f'http://fundf10.eastmoney.com/FundArchivesDatas.aspx'
    param_gm = {
        'type': 'jzcgm',
        'code': fundCode
    }
    res_gm = req(url_gm, param_gm, None, 'gm')
    if res_gm == False:
        return 'x'
    else:
        text_gm = res_gm.text
        temp_gm = re.findall(r"\=(.*?)$", text_gm)
        list_gm = eval(temp_gm[0])
        if len(list_gm) > 0:
            return list_gm[4][1]
        else:
            return 'x'


def jlj():
    """
    pickup
    para: -
    return: -/content
    """
    global content

    url_dg = "http://fund.eastmoney.com/data/FundGuideapi.aspx"  # 导购
    param5d = {
        'dt': '4',
        'sd': get_trade_day(5),  # 开始日期
        'ed': get_trade_day(1),  # 结束日期
        'sc': 'diy',
        'st': 'asc',  # 升序
        'pi': '1',
        'pn': '20',  # 获取数量 20
        'zf': 'diy',
        'sh': 'list'
    }
    res = req(url_dg, param5d, None, 'dg')
    if res == False:
        return
    rankData = res.text
    rankData_l = re.findall(r":\[(.*?)\],", rankData)  # 导购->list
    lj_list = eval(rankData_l[0])

    for item in lj_list:
        lj_id = item.split(",")[0]  # fund id

        jz = get_jz(lj_id)
        if jz == False:
            continue
        if float(jz[0]['JZZZL']) > 0 or float(jz[1]['JZZZL']) > 0 or float(jz[2]['JZZZL']) > 0:  # 近3天为负则继续后续逻辑
            continue

        gz = get_gz(lj_id)
        if gz == False:
            continue
        if float(gz['gszzl']) > 0:
            continue

        item = {
            'id': lj_id,
            'gz': gz['gsz'],
            'gzzzl': gz['gszzl'],
            'gm': get_gm(lj_id),
            'pj': get_pj(lj_id)
        }
        content = content + str(item) + '\n'
        content = content.replace('{', '').replace('}', '').replace("'", '')

    if len(content) > 0:
        content = f'今日关注：\n{content}\n'
        log.logger.info(content)
    else:
        log.logger.info('无车')


def watcher():
    """
    追踪
    para: -
    return: -/content
    """
    global content
    content_x = ''
    try:
        with open('focus.json', 'r', encoding='utf8')as focus:
            json_fs = json.load(focus)
    except Exception as e:
        # print("本地读取异常:%s" % e)
        url_fs = "https://raw.githubusercontent.com/Sirius2s/litkit/main/dumpcart/focus.json"

        res = req(url_fs, None, None, 'focus')
        if res == False:
            # print("读取失败")
            return
        json_fs = res.json()

    if json_fs is None:
        log.logger.info('不追了')
        return

    for item_fs in json_fs:
        gz = get_gz(item_fs['fundcode'])
        if gz == False:
            continue
        if float(gz['gsz']) < float(item_fs['buyin']) * float(item_fs['wpoint']):
            continue

        content_x = content_x + item_fs['fundcode'] + ': ' + gz['gsz'] + '\n'

    if len(content_x) > 0:
        content_x = f'下车：\n{content_x}\n'
        log.logger.info(content_x)
        content = content + content_x
    else:
        log.logger.info('不下')


def dumpcart():
    if is_trade_day(datetime.datetime.now().date()):
        log.logger.info('发车')
    else:
        log.logger.info('休息')
        return

    jlj()
    watcher()

    if len(content) > 0:
        notification.notify_QW_AM(title, content)
        notification.notify_QMSG(title, content)
    else:
        log.logger.info('停车')

if __name__ == '__main__':
    # get_trade_day(5)
    # get_trade_day(0)
    # print(get_gm('002601'))
    dumpcart()
