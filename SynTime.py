# import json                    # Json转换库
# import time
from datetime import datetime, timedelta  # , timezone
# import os

import requests  # 网络请求库


def get_time():
    """从网络获取时间戳."""
    url = 'https://a.jd.com//ajax/queryServerData.html'
    ret = requests.get(url)
    js = ret.json()['serverTime']
    # js = json.loads(ret)

    return float(js)/1000


def adj_cron(cron_tar, cron_src):
    """调整CRON.目前只支持具体时间点

    根据执行时间，将原始CRON调整为适配主机时间的CRON，以达到在原始CRON预计时间执行的目的.

    - param cron_tar: 目标源CRON.
    - param cron_src: syntime自身CRON.
    - return: 结果CRON.
    结论：
        github中主机时间与标准时间一致，但CRON调度时间有不规律延迟。
        通过程序修正CRON来达到在设定的准确时间点运行计划--作为前置任务提前1小时执行
    """
    cron_src_time = datetime(datetime.now().year, datetime.now().month, datetime.now().day,
                             int(cron_src.split(' ')[1]), int(cron_src.split(' ')[0]), 00)
    print('cron_src time is: ', cron_src_time)

    print('datetime now is: ', datetime.now())

    # 本任务的执行时间与计划时间差.实际滞后sec_dif
    sec_dif = (datetime.now()-cron_src_time).total_seconds()

    cron_tar_time = datetime(datetime.now().year, datetime.now().month, datetime.now().day,
                             int(cron_tar.split(' ')[1]), int(cron_tar.split(' ')[0]), 00)
    print('cron_tar time is: ', cron_tar_time)

    new_time = cron_tar_time-timedelta(seconds=sec_dif)  # 目标文件的计划将提前sec_dif
    print('cron_tar time will be: ', new_time)

    cron_rlt = f"""{new_time.minute} {new_time.hour} {cron_tar.split(' ')[2]} {cron_tar.split(' ')[3]} {cron_tar.split(' ')[4]}"""

    return cron_rlt


def read_cron(file, spe):
    """读取指定路径文件中的CRON文本. |符号后的内容为目标时点

    - param file -- 文件路径.
    - return -- CRON文本.
    """
    # with open(file, "r", encoding="utf-8") as f:
    #     for line in f:
    #         if 'cron' in line:
    #             cron = line.split("'")[1]
    #             # print(cron)
    #             break
    # return cron
    for line in open(file, 'r', encoding='UTF-8'):
        if 'cron' in line:
            cron = line.split(spe)[1]
            # print(cron)
            break
    return cron


def chg_file(file):
    """修改指定路径文件中的CRON文本.

    - param file -- 文件路径.
    - return none
    """
    file_data = ""
    new_cron = adj_cron(read_cron(file, "|"), read_cron(".github/workflows/syn_time.yml", "'"))
    with open(file, "r", encoding="utf-8") as f:
        for line in f:
            if 'cron:' in line:
                line = line.replace(line.split("'")[1], new_cron)
            file_data += line
    with open(file, "w", encoding="utf-8") as f:
        f.write(file_data)


if __name__ == '__main__':
    # print('new cron is: ', adj_cron(read_cron(".github/workflows/syn_time.yml")))
    # print(os.environ)
    # read_cron(".github/workflows/syn_time.yml")
    chg_file(".github/workflows/syn_time.yml")  # 应与read_cron的文件不同