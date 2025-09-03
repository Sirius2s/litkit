"""
基金筛选工具 (dumpcart.py)
=========================

功能:
- 筛选值得关注的基金
- 判断基金是否应该"下车"(卖出)
- 基于多种指标进行综合评估

筛选标准:
1. 基金类型: 仅考虑股票型和混合型基金
2. 成立时间: 至少成立一年以上
3. 基金规模: 不低于1亿元
4. 评级分数: 加权评级分数不低于2.5
5. 最大回撤: 不超过30%
6. 行业配置: 重仓行业不处于整体下跌趋势
7. 近期表现: 近3天平均跌幅超过2%，且RSI低于30
8. 估值情况: 当前估值为负增长

行业趋势判断:
- 使用行业指数近一周和近一月涨跌幅数据
- 近一周跌幅超过2%或近一月跌幅超过5%视为下跌趋势
- 超过一半重仓行业处于下跌趋势时，整体行业配置不佳

配置项:
- 所有筛选参数均可在CONFIG中调整

使用方法:
直接运行脚本:
    python dumpcart.py

注意事项:
- 需要网络连接以获取基金和指数数据
- 程序会自动缓存部分数据以提高性能
- 程序仅在交易日运行
"""

import requests
import json
import re
from chinese_calendar import is_workday
import datetime
import log
import notification

# 配置项
CONFIG = {
    # 近3天平均跌幅阈值，负数表示跌幅，建议范围: -3.0 到 -1.0
    # 值越小(如-3.0)筛选条件越严格，值越大(如-1.0)筛选条件越宽松: -2.0,
    'recent_fall_threshold': -2.0,
    
    # RSI阈值，用于判断是否超卖，建议范围: 20-40
    # 值越小(如20)表示更严格的超卖条件，值越大(如40)条件越宽松: 30,
    'rsi_threshold': 50,
    
    # 最小基金规模(亿元)，建议范围: 0.5-5.0
    # 过小规模基金可能存在清盘风险，过大可能缺乏灵活性: 1.0,
    'min_fund_scale': 1.0,
    
    # 最低评级分数，5分制，建议范围: 2.0-4.0
    # 值越高筛选条件越严格，只选择优质基金: 2.5,
    'min_rating_score': 2.5,
    
    # 最大回撤阈值(%)，负数表示回撤，建议范围: -20 到 -50
    # 值越小(如-20)筛选条件越严格，值越大(如-50)条件越宽松: -30,
    'max_drawdown_threshold': -30,
    
    # 行业近一周跌幅阈值(%)，建议范围: -1.0 到 -5.0
    # 用于判断行业短期趋势，值越小条件越严格: -2.0,
    'sector_decline_week_threshold': -2.0,
    
    # 行业近一月跌幅阈值(%)，建议范围: -3.0 到 -10.0
    # 用于判断行业中长期趋势，值越小条件越严格: -5.0,
    'sector_decline_month_threshold': -5.0,
    
    # 行业下跌比例阈值，建议范围: 0.3-0.8
    # 表示基金重仓行业中多少比例下跌时判定整体不佳，0.5表示一半: 0.5,
    'sector_decline_ratio_threshold': 0.5,
    
    # 缓存过期时间(秒)，建议范围: 180-600
    # 值越小数据越新鲜但请求越频繁，值越大性能越好但数据可能过期: 300,
    'cache_expire_seconds': 300,
}


header = {
    'Referer': 'http://fundf10.eastmoney.com/',
}
title = '发车'
content = ''

# 添加缓存字典
_cache = {}
_CACHE_EXPIRE_SECONDS = CONFIG['cache_expire_seconds']  # 5分钟缓存


def _get_cache(key):
    """获取缓存数据"""
    if key in _cache:
        data, timestamp = _cache[key]
        # 检查是否过期
        if (datetime.datetime.now() - timestamp).total_seconds() < _CACHE_EXPIRE_SECONDS:
            return data
        else:
            # 删除过期缓存
            del _cache[key]
    return None


def _set_cache(key, data):
    """设置缓存数据"""
    _cache[key] = (data, datetime.datetime.now())


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
            count = count + 1


def req(url, param, head, trans):
    """
    通用接口
    para: url,param,head,trans
    return: False/response
    """
    try:
        # 检查是否有缓存
        # 处理参数中的日期对象，使其可序列化
        param_str = ""
        if param:
            serializable_param = {}
            for k, v in param.items():
                if isinstance(v, (datetime.date, datetime.datetime)):
                    serializable_param[k] = v.isoformat()
                else:
                    serializable_param[k] = v
            param_str = json.dumps(serializable_param, sort_keys=True)
        
        cache_key = f"{url}_{param_str}_{trans}"
        cached_data = _get_cache(cache_key)
        if cached_data:
            log.logger.info(f"使用缓存数据: {trans}")
            return cached_data
        
        res = requests.get(url, params=param, headers=head)
        if res.status_code != 200:
            log.logger.error("获取失败:%s" % [trans, res.status_code])
            return False
        else:
            # 缓存成功的响应
            _set_cache(cache_key, res)
            return res
    except Exception as e:
        log.logger.error("获取失败:%s" % [trans, e])
        return False


def get_jz(fundCode, pageSize=15):
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
        'pageSize': str(pageSize),  # 动态设置天数
        'startDate': '',  # 开始日期
        'endDate': ''  # 结束日期
    }
    res_jz = req(url_jz, param_jz, header, 'jz')
    if res_jz == False:
        return res_jz
    else:
        return res_jz.json()['Data']['LSJZList']


def calculate_rsi(prices, period=14):
    """
    计算RSI指标
    """
    if len(prices) < period + 1:
        return None
    
    deltas = [float(prices[i]['DWJZ']) - float(prices[i+1]['DWJZ']) for i in range(len(prices)-1)]
    gains = [delta if delta > 0 else 0 for delta in deltas]
    losses = [-delta if delta < 0 else 0 for delta in deltas]
    
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    
    if avg_loss == 0:
        rs = 100
    else:
        rs = avg_gain / avg_loss
        
    rsi = 100 - (100 / (1 + rs))
    return round(rsi, 2)


def get_weighted_rating(fundCode):
    """
    获取加权评级分数
    """
    ratings = get_pj(fundCode)
    if ratings == 'x':
        # 对于无评级基金，根据基金基本信息进行评估
        return 0-evaluate_fund_without_rating(fundCode)
    
    # 定义各评级机构的权重
    weights = {
        'HTPJ': 0.25,  # 海通评级
        'JAPJ': 0.30,  # 济安金信评级
        'ZSPJ': 0.20,  # 招商评级
        'SZPJ3': 0.15, # 上海证券评级三年期
        'ZSPJ5': 0.10  # 招商证券评级五年期
    }
    
    weight_score = 0
    total_weight = 0
    
    # 根据评级机构权威性设置权重，并计算加权分数
    for rating_type, weight in weights.items():
        if ratings.get(rating_type) not in ['', '0', None]:
            weight_score += int(ratings[rating_type]) * weight
            total_weight += weight
    
    # 如果没有任何评级数据，返回0
    if total_weight == 0:
        return 0
    
    # 按实际权重占比计算最终得分
    return round(weight_score / total_weight, 2)


def evaluate_fund_without_rating(fundCode):
    """
    对无评级基金进行评估
    
    对于新基金或无评级基金，我们可以通过以下方式进行评估：
    1. 基金类型（股票型、混合型等）
    2. 基金规模
    3. 基金成立时间
    4. 基金经理经验等
    
    返回值：
    - 0: 不推荐（如成立时间过短、规模过小等）
    - 1-5: 根据基金基本信息给出的评分
    """
    # 获取基金基本信息
    fund_info = get_fund_info_from_jbgk(fundCode)
    fund_type = fund_info.get('type', '未知类型')
    establish_date = fund_info.get('establish_date')
    
    # 获取基金规模
    fund_scale = get_gm(fundCode)
    
    # 基础评分
    base_score = 2.5  # 默认评分
    
    # 根据基金类型调整评分（使用前3个字符进行匹配）
    fund_type_prefix = fund_type[:3] if len(fund_type) >= 3 else fund_type
    if fund_type_prefix in ['股票型', '混合型']:
        base_score += 0.5  # 股票型和混合型基金通常风险较高但收益也较高
    elif fund_type_prefix == '债券型':
        base_score -= 0.5  # 债券型基金风险较低
    
    # 根据基金规模调整评分
    if fund_scale != 'x' and fund_scale is not None:
        try:
            scale = float(fund_scale)
            if scale < 1:  # 规模小于1亿
                base_score -= 0.5  # 规模较小风险较高
            elif scale > 50:  # 规模大于50亿
                base_score += 0.5  # 规模较大相对稳定
        except ValueError:
            pass  # 无法解析规模数据
    
    # 根据成立时间调整评分
    if establish_date:
        days_since_establish = (datetime.date.today() - establish_date).days
        if days_since_establish < 30:  # 成立不足1个月
            base_score -= 1.0  # 新基金不确定性高
        elif days_since_establish < 90:  # 成立不足3个月
            base_score -= 0.5  # 较新基金
        elif days_since_establish > 365:  # 成立超过1年
            base_score += 0.5  # 成立时间较长，有一定历史数据
    
    # 确保评分在合理范围内
    base_score = max(1.0, min(5.0, base_score))
    
    return round(base_score, 2)


def get_fund_info_from_jbgk(fundCode):
    """
    从基金档案页面获取基金信息（类型、成立日期等）
    
    输入参数:
        fundCode (str): 基金代码，例如 '002601'
    
    返回值:
        dict: 包含基金信息的字典
    """
    import re
    from datetime import datetime, timedelta
    
    # 天天基金网基金档案页面接口
    url = f"https://fundf10.eastmoney.com/jbgk_{fundCode}.html"
    
    fund_info = {
        'type': '未知类型',
        'establish_date': datetime.today().date() - timedelta(days=700),
        'name': f'基金{fundCode}'
    }
    
    try:
        # 使用req函数发送请求获取基金档案数据
        response = req(url, None, {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Referer': 'http://fund.eastmoney.com/'
        }, 'fund_detail')
        
        if response == False:
            return fund_info
        
        # 解析返回的HTML数据，查找基金名称
        fund_name_match = re.search(r'<title>([^<>\(]+)\(', response.text)
        if fund_name_match:
            fund_info['name'] = fund_name_match.group(1).strip()
        
        # 解析返回的HTML数据，查找基金类型
        fund_type_match = re.search(r'基金类型.*?>([^<]+)</td>', response.text)
        if fund_type_match:
            fund_info['type'] = fund_type_match.group(1).strip()
        
        # 解析返回的HTML数据，查找基金成立日期
        fund_establish_date_match = re.search(r'成立日期.*?(\d{4}-\d{2}-\d{2})', response.text)
        if fund_establish_date_match:
            establish_date_str = fund_establish_date_match.group(1)
            fund_info['establish_date'] = datetime.strptime(establish_date_str, "%Y-%m-%d").date()
        
        return fund_info
        
    except Exception as e:
        print(f"获取基金信息时出错: {e}")
        return fund_info


def get_fund_name(fundCode):
    """
    获取基金名称
    
    输入参数:
        fundCode (str): 基金代码，例如 '002601'
    
    返回值:
        str: 基金名称，例如 '某某科技创新混合'
    """
    fund_info = get_fund_info_from_jbgk(fundCode)
    return fund_info['name']


def get_fund_type(fundCode):
    """
    获取基金类型
    
    输入参数:
        fundCode (str): 基金代码，例如 '002601'
    
    返回值:
        str: 基金类型，例如 '股票型', '混合型', '债券型', '指数型' 等
    """
    fund_info = get_fund_info_from_jbgk(fundCode)
    return fund_info['type']


def get_fund_establish_date(fundCode):
    """
    获取基金成立日期
    
    输入参数:
        fundCode (str): 基金代码，例如 '002601'
    
    返回值:
        datetime.date: 基金成立日期对象
    """
    fund_info = get_fund_info_from_jbgk(fundCode)
    return fund_info['establish_date']


def get_max_drawdown(fundCode):
    """
    获取基金最大回撤
    
    输入参数:
        fundCode (str): 基金代码，例如 '002601'
    
    返回值:
        float: 最大回撤百分比，例如 -25.8 表示最大回撤25.8%
    """
    from datetime import datetime
    
    try:
        # 使用项目中已有的get_jz函数获取基金历史净值数据，使用更大的天数(100天)来计算最大回撤
        jz_data = get_jz(fundCode, pageSize=100)
        if not jz_data:
            return -10.0  # 默认值
        
        # 过滤掉没有净值数据的记录
        valid_data = [item for item in jz_data if item.get('DWJZ') and item['DWJZ'] != '']
        
        if len(valid_data) < 2:
            return -10.0  # 默认值
        
        # 提取单位净值
        prices = [float(item['DWJZ']) for item in valid_data]
        
        # 计算最大回撤
        peak = prices[0]
        max_drawdown = 0
        
        for price in prices:
            if price > peak:
                peak = price
            drawdown = (peak - price) / peak
            if drawdown > max_drawdown:
                max_drawdown = drawdown
        
        return -max_drawdown * 100  # 转换为百分比并返回负值
        
    except Exception as e:
        print(f"计算基金最大回撤时出错: {e}")
        return -10.0  # 默认值


def is_sector_declining(sectors):
    """
    判断基金重仓行业是否处于下跌趋势
    
    输入参数:
        sectors (list): 基金重仓行业列表，例如 ['科技', '医疗', '消费']
    
    返回值:
        bool: True表示有行业处于下跌趋势，False表示没有
    
    行业趋势判断策略：
    1. 获取各行业的近期涨跌幅数据（使用近一周和近一月数据）
    2. 如果行业指数近期表现疲软（如近一周跌幅超过2%或近一月跌幅超过5%），则认为该行业处于下跌趋势
    3. 如果多个重仓行业都处于下跌趋势，则认为基金整体行业配置不佳
    """
    # 行业关键词到行业指数代码的映射
    # 这些映射基于天天基金网行业分类与指数代码的对应关系
    industry_index_map = {
        # 制造业相关
        '制造业': '000001',      # 上证指数
        '机械': '000001',        # 上证指数包含机械板块
        '设备': '000001',        # 上证指数包含设备制造板块
        '汽车': '000001',        # 上证指数包含汽车行业
        '化工': '000001',        # 上证指数包含化工行业
        '钢铁': '000001',        # 上证指数包含钢铁行业
        '有色金属': '000001',    # 上证指数包含有色金属
        
        # 科技相关
        '科技': '000300',        # 沪深300指数
        '信息技术': '000300',    # 沪深300包含信息技术
        '电子': '000300',        # 沪深300包含电子行业
        '计算机': '000300',      # 沪深300包含计算机行业
        '通信': '000300',        # 沪深300包含通信行业
        '软件': '000300',        # 沪深300包含软件行业
        '互联网': '000300',      # 沪深300包含互联网行业
        '半导体': '000300',      # 沪深300包含半导体行业
        
        # 医疗健康相关
        '医疗': '399380',        # 国证医药卫生行业指数
        '医药': '399380',        # 国证医药卫生行业指数
        '生物': '399380',        # 国证医药卫生行业指数
        '生物科技': '399380',    # 国证医药卫生行业指数
        '健康': '399380',        # 国证医药卫生行业指数
        '医疗服务': '399380',    # 国证医药卫生行业指数
        '卫生': '399380',        # 国证医药卫生行业指数
        '社会工作': '399380',    # 国证医药卫生行业指数（社会工作与医疗健康相关）
        '卫生和社会工作': '399380',        # 国证医药卫生行业指数
        
        # 消费相关
        '消费': '000932',        # 中证消费指数
        '食品': '000932',        # 中证消费指数包含食品饮料
        '饮料': '000932',        # 中证消费指数包含饮料制造
        '白酒': '000932',        # 中证消费指数包含白酒行业
        '家电': '000932',        # 中证消费指数包含家用电器
        '纺织': '000932',        # 中证消费指数包含纺织服装
        '服装': '000932',        # 中证消费指数包含服装行业
        
        # 金融相关
        '金融': '000016',        # 上证50指数（金融占比较高）
        '银行': '000016',        # 上证50包含大型银行
        '保险': '000016',        # 上证50包含保险企业
        '证券': '000016',        # 上证50包含证券公司
        
        # 能源相关
        '能源': '000928',        # 中证能源指数
        '煤炭': '000928',        # 中证能源指数包含煤炭行业
        '石油': '000928',        # 中证能源指数包含石油行业
        '天然气': '000928',      # 中证能源指数包含天然气行业
        
        # 房地产相关
        '房地产': '000933',      # 中证房地产指数
        
        # 交通运输相关
        '交通运输': '000929',    # 中证交通运输指数
        '物流': '000929',        # 中证交通运输指数包含物流行业
        '航空': '000929',        # 中证交通运输指数包含航空运输
        
        # 基建相关
        '建筑': '000001',        # 上证指数包含建筑行业
        '建材': '000001',        # 上证指数包含建筑材料
        
        # 公用事业相关
        '电力': '399980',        # 中证电力指数
        '公用': '399980',        # 中证电力指数包含公用事业
        
        # 其他服务行业
        '租赁': '000300',        # 沪深300包含租赁服务
        '商务服务': '000300',    # 沪深300包含商务服务
        '教育': '399987',        # 中证教育指数
        '传媒': '000300',        # 沪深300包含传媒行业
        '娱乐': '000300',        # 沪深300包含娱乐行业
    }
    
    # 下跌行业计数
    declining_count = 0
    
    # 确定实际需要请求的行业
    matched_industries = set()  # 存储实际匹配到的行业关键词
    
    # 先找出基金行业中能够匹配到的行业关键词
    for sector in sectors:
        for industry in industry_index_map.keys():
            # 使用模糊匹配，只要行业关键词在基金行业名称中出现即可
            if industry in sector or sector in industry:
                matched_industries.add(industry)
    
    # 如果没有匹配到任何行业关键词，直接返回False
    if not matched_industries:
        log.logger.warning(f"未找到任何匹配的行业关键词，基金行业: {', '.join(sectors)}")
        return False
    
    # 收集需要请求的唯一指数代码
    unique_index_codes = set()
    index_to_industries = {}  # 记录每个指数代码对应哪些行业
    
    for industry in matched_industries:
        index_code = industry_index_map[industry]
        unique_index_codes.add(index_code)
        if index_code not in index_to_industries:
            index_to_industries[index_code] = []
        index_to_industries[index_code].append(industry)
    
    # 获取行业指数近期表现数据
    industry_performance = {}
    index_performance_cache = {}  # 缓存指数表现数据
    
    # 只获取实际需要的唯一指数代码数据
    for index_code in unique_index_codes:
        # 检查缓存
        cached_performance = _get_cache(f"index_performance_{index_code}")
        if cached_performance:
            index_performance_cache[index_code] = cached_performance
            log.logger.info(f"使用缓存的指数数据: {index_code}")
            continue
            
        try:
            # 获取指数近期数据
            index_data = get_index_performance(index_code)
            if index_data:
                index_performance_cache[index_code] = index_data
                # 缓存数据
                _set_cache(f"index_performance_{index_code}", index_data)
            else:
                log.logger.warning(f"未能获取到指数 {index_code} 的数据")
        except Exception as e:
            log.logger.warning(f"获取指数{index_code}数据时出错: {e}")
            continue
    
    # 将指数数据映射回各行业
    for index_code, industries in index_to_industries.items():
        if index_code in index_performance_cache:
            performance = index_performance_cache[index_code]
            for industry in industries:
                industry_performance[industry] = performance
    
    # 遍历基金重仓行业
    for sector in sectors:
        # 查找对应的行业指数
        index_performance = None
        matched_industry = None
        for industry, performance in industry_performance.items():
            # 使用模糊匹配，只要行业关键词在基金行业名称中出现即可
            if industry in sector or sector in industry:
                index_performance = performance
                matched_industry = industry
                break
        
        # 如果找到了对应的行业指数数据
        if index_performance:
            week_change, month_change = index_performance
            
            # 判断行业是否处于下跌趋势
            # 判断标准：近一周跌幅超过配置阈值 或 近一月跌幅超过配置阈值
            if week_change < CONFIG['sector_decline_week_threshold'] or month_change < CONFIG['sector_decline_month_threshold']:
                declining_count += 1
                log.logger.info(f"行业 {sector} (匹配到 {matched_industry}) 处于下跌趋势: 近一周 {week_change:.2f}%，近一月 {month_change:.2f}%")
        else:
            log.logger.warning(f"未找到行业 {sector} 对应的指数数据")
    
    # 如果超过配置比例的重仓行业处于下跌趋势，则认为整体行业配置不佳
    if len(sectors) > 0 and declining_count / len(sectors) > CONFIG['sector_decline_ratio_threshold']:
        log.logger.info(f"基金行业配置不佳: {declining_count}/{len(sectors)} 个行业处于下跌趋势")
        return True
    
    return False


def get_index_performance(index_code):
    """
    获取指数的近期表现数据
    
    输入参数:
        index_code (str): 指数代码，例如 '000001'
    
    返回值:
        tuple: (近一周涨跌幅, 近一月涨跌幅) 或 None（获取失败时）
    """
    try:
        # 使用东方财富接口获取指数历史数据
        import time
        import random
        
        url = "https://push2his.eastmoney.com/api/qt/stock/kline/get"
        # 确保指数代码格式正确
        secid = f"1.{index_code}" if index_code.startswith(('0', '3')) else f"0.{index_code}"
        
        # 添加时间戳和随机数作为参数，避免缓存
        timestamp = int(time.time() * 1000)
        random_cb = f"jQuery{random.randint(1000000000000000, 9999999999999999)}_{timestamp}"
        
        params = {
            'cb': random_cb,
            'secid': secid,
            'ut': 'fa5fd1943c7b386f172d6893dbfba10b',
            'fields1': 'f1,f2,f3,f4,f5,f6',
            'fields2': 'f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61',
            'klt': '101',  # 日线
            'fqt': '1',    # 前复权
            'lmt': '120',  # 获取最近120天数据
            'end': '20500101',
            '_': timestamp
        }
        
        response = requests.get(url, params=params, headers=header)
        log.logger.info(f"获取指数数据 {index_code}: {response.status_code}")
        if response.status_code != 200:
            log.logger.error(f"获取指数数据失败 {index_code}: HTTP {response.status_code}")
            return None
            
        # 处理JSONP响应，提取JSON部分
        import re
        jsonp_data = response.text
        json_match = re.search(r'\((.*)\)', jsonp_data)
        if not json_match:
            log.logger.error(f"无法解析JSONP响应 {index_code}")
            return None
            
        import json
        data = json.loads(json_match.group(1))
        
        # 检查返回数据是否有效
        if not data.get('data') or not data['data'].get('klines'):
            log.logger.warning(f"指数数据为空 {index_code}")
            return None
            
        klines = data['data']['klines']
        if len(klines) < 5:
            log.logger.warning(f"指数数据不足 {index_code}")
            return None
            
        # 解析K线数据
        prices = []
        for kline in klines:
            parts = kline.split(',')
            if len(parts) >= 3:  # 确保有足够的数据字段
                # 日期, 开盘价, 收盘价, 最高价, 最低价, 成交量, 成交额
                try:
                    close_price = float(parts[2])
                    prices.append(close_price)
                except (ValueError, IndexError):
                    continue  # 跳过无法解析的数据点
        
        if len(prices) < 5:
            log.logger.warning(f"指数价格数据不足 {index_code}")
            return None
            
        # 计算近一周涨跌幅（5个交易日）
        if len(prices) >= 5:
            week_end_price = prices[-1]
            week_start_price = prices[-5]
            week_change = (week_end_price - week_start_price) / week_start_price * 100
        else:
            week_change = 0.0
        
        # 计算近一月涨跌幅（20个交易日）
        if len(prices) >= 20:
            month_end_price = prices[-1]
            month_start_price = prices[-20]
            month_change = (month_end_price - month_start_price) / month_start_price * 100
        else:
            # 如果不足20个交易日，使用全部数据计算
            month_end_price = prices[-1]
            month_start_price = prices[0]
            month_change = (month_end_price - month_start_price) / month_start_price * 100
        
        log.logger.info(f"指数 {index_code} 近一周涨跌幅: {week_change:.2f}%，近一月涨跌幅: {month_change:.2f}%")
        return (week_change, month_change)
        
    except Exception as e:
        log.logger.error(f"获取指数{index_code}近期表现数据时出错: {e}")
        return None


def get_fund_sectors(fundCode):
    """
    获取基金重仓行业
    
    输入参数:
        fundCode (str): 基金代码，例如 '002601'
    
    返回值:
        list: 基金重仓行业列表，例如 ['科技', '医疗', '消费']
    """
    import re
    try:
        # 使用新的API接口获取行业配置数据
        url = f"https://api.fund.eastmoney.com/f10/HYPZ/"
        param = {
            'fundCode': fundCode,
            'year': '',  # 空字符串表示获取最新年份数据
            'callback': f'jQuery{int(datetime.datetime.now().timestamp() * 1000)}',
            '_': int(datetime.datetime.now().timestamp() * 1000)  # 时间戳防止缓存
        }
        
        # 使用req函数发送请求获取行业配置数据
        response = req(url, param, header, 'fund_sectors')
        
        if response == False:
            return []
        
        # 解析JSONP响应数据
        # JSONP格式为: callbackName({data})
        # 需要提取括号内的JSON数据
        jsonp_response = response.text
        # 使用正则表达式提取JSON数据
        json_data_match = re.search(r'\((.*?)\)', jsonp_response, re.DOTALL)
        if not json_data_match:
            return []
            
        # 将JSON字符串转换为字典
        data = json.loads(json_data_match.group(1))
        
        # 检查返回数据是否有效
        if 'Data' not in data or 'QuarterInfos' not in data['Data'] or data['ErrCode'] != 0:
            return []
        
        # 获取最新的季度行业配置信息
        quarter_infos = data['Data']['QuarterInfos']
        if not quarter_infos:
            return []
        
        # 获取最新的季度信息（通常第一个是最新季度）
        latest_quarter = quarter_infos[0]
        if 'HYPZInfo' not in latest_quarter:
            return []
        
        # 提取行业名称
        sectors = []
        for industry_info in latest_quarter['HYPZInfo']:
            # 获取行业名称
            industry_name = industry_info.get('HYMC', '')
            # 获取行业占比
            zjzbl = industry_info.get('ZJZBL', '0')
            # 只获取占比较高的行业（大于2%）
            if industry_name and zjzbl and zjzbl != '---' and zjzbl != '':
                try:
                    if float(zjzbl) > 2.0:
                        # 清理行业名称
                        industry_name = re.sub(r'\s+', '', industry_name)
                        if industry_name not in sectors:
                            sectors.append(industry_name)
                except ValueError:
                    # 如果转换为浮点数失败，跳过该行业
                    pass
        
        return sectors
        
    except Exception as e:
        print(f"获取基金重仓行业时出错: {e}")
        return []


def jlj():
    """
    pickup
    para: -
    return: -/content
    """
    global content

    # 设置筛选参数
    recent_fall_threshold = CONFIG['recent_fall_threshold']  # 近3天平均跌幅阈值
    rsi_threshold = CONFIG['rsi_threshold']  # RSI阈值
    
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
        log.logger.error("获取导购数据失败")
        return
    try:
        rankData = res.text
        rankData_l = re.findall(r":\[(.*?)\],", rankData)  # 导购->list
        if not rankData_l:
            log.logger.error("未能解析导购数据")
            return
        lj_list = eval(rankData_l[0])
    except Exception as e:
        log.logger.error(f"解析导购数据时出错: {e}")
        return

    selected_funds_count = 0
    processed_funds_count = 0
    
    for item in lj_list:
        try:
            lj_id = item.split(",")[0]  # fund id
            processed_funds_count += 1
        except Exception as e:
            log.logger.warning(f"解析基金ID时出错: {e}")
            continue

        jz = get_jz(lj_id)
        if jz == False:
            continue
        
        # 检查最近3天的净值增长率
        valid_jz = []
        for i in range(3):
            if i >= len(jz) or jz[i]['JZZZL'] == "":
                valid_jz.append(0.0)
            else:
                try:
                    valid_jz.append(float(jz[i]['JZZZL']))
                except ValueError:
                    valid_jz.append(0.0)
        
        # 检查平均跌幅
        avg_fall = sum(valid_jz) / 3 if valid_jz else 0
        if avg_fall > recent_fall_threshold:
            log.logger.debug(f"基金{lj_id}平均跌幅未达标: {avg_fall}")
            continue

        # 获取RSI指标 越小越好
        rsi = calculate_rsi(jz)
        if rsi is not None and rsi > rsi_threshold:
            continue

        # 获取估值数据
        # gz = get_gz_xc(lj_id)
        # if gz != False:
        #     # 检查估值时间是否为当天
        #     try:
        #         gz_time = datetime.datetime.strptime(gz['gztime'], '%Y-%m-%d %H:%M')
        #         if gz_time.date() != datetime.date.today():
        #             gz = False
        #         # 检查异常波动
        #         if abs(float(gz['gszzl'])) > 10:
        #             gz = False
        #     except Exception as e:
        #         log.logger.warning(f"解析估值时间数据时出错 {lj_id}: {e}")
        #         gz = False

        # if gz == False:
        gz = get_gz(lj_id)
        if gz == False:
            continue
        try:
            if float(gz['gszzl']) > 0:
                log.logger.debug(f"基金{lj_id}估值增长为正: {gz['gszzl']}")
                continue
            gz_gsz = gz['gsz']
            gz_gszzl = gz['gszzl']
        except Exception as e:
            log.logger.warning(f"解析估值数据时出错 {lj_id}: {e}")
            continue
        # else:
        #     try:
        #         gz_dtl = list(map(float, gz['detail'].split(",")[1::2]))
        #         gz_gsz = round(sum(gz_dtl)/len(gz_dtl),4) if gz_dtl else 0
        #         gz_gszzl = round((gz_gsz-float(gz['yes']))/float(gz['yes']),4) if float(gz['yes']) != 0 else 0
        #         if gz_gszzl > 0:
        #             gz = False
        #             continue
        #     except Exception as e:
        #         log.logger.warning(f"计算估值数据时出错 {lj_id}: {e}")
        #         continue

        # 获取基金规模
        fund_scale = get_gm(lj_id)
        if fund_scale != 'x' and fund_scale is not None:
            try:
                if float(fund_scale) < CONFIG['min_fund_scale']:
                    log.logger.debug(f"基金{lj_id}规模不足: {fund_scale}")
                    continue
            except ValueError:
                continue  # 如果无法转换为float，跳过该基金

        # 获取加权评级
        rating_score = get_weighted_rating(lj_id)
        if abs(rating_score) < CONFIG['min_rating_score']:  # 评级分数过低的基金排除
            log.logger.debug(f"基金{lj_id}评级分数不足: {rating_score}")
            continue

        # 获取基金类型并过滤
        fund_type = get_fund_type(lj_id)
        # 取基金类型的前3个字符进行匹配
        fund_type_prefix = fund_type[:3] if len(fund_type) >= 3 else fund_type
        if fund_type_prefix not in ['股票型', '混合型']:
            log.logger.debug(f"基金{lj_id}类型不符合要求: {fund_type}")
            continue

        # 检查基金成立时间
        establish_date = get_fund_establish_date(lj_id)
        if (datetime.date.today() - establish_date).days < 365:  # 成立不足一年的基金
            log.logger.debug(f"基金{lj_id}成立时间不足一年")
            continue

        # 检查最大回撤
        max_drawdown = get_max_drawdown(lj_id)
        if max_drawdown < CONFIG['max_drawdown_threshold']:  # 最大回撤超过阈值风险较高
            log.logger.debug(f"基金{lj_id}最大回撤超过阈值: {max_drawdown}")
            continue

        # 检查基金重仓行业
        sectors = get_fund_sectors(lj_id)
        if is_sector_declining(sectors):  # 行业处于下跌趋势
            log.logger.debug(f"基金{lj_id}重仓行业处于下跌趋势")
            continue

        # 获取基金名称
        fund_name = get_fund_name(lj_id)

        # 组装基金信息
        try:
            item = {
                'id🎫': lj_id,
                'name': fund_name,
                'type': fund_type,
                'gz': gz_gsz,
                'zzl': gz_gszzl,
                'gm': fund_scale,
                'pj': rating_score,
                'rsi': rsi if rsi is not None else 'N/A',
                'fall📉': round(avg_fall, 2),
                'score🚦': round((avg_fall * -1 + 5) * 0.4 + (rating_score / 5 * 3) * 0.6, 2),  # 综合推荐分数
                'clrq': establish_date.strftime('%Y-%m-%d'),
                'zdhc': f'{round(max_drawdown, 2)}%',
                'hy': ','.join(sectors) if sectors else 'N/A'
            }
            content = content + str(item) + '\n'
            content = content.replace('{', '').replace('}', '').replace("'", '')
            selected_funds_count += 1
        except Exception as e:
            log.logger.warning(f"组装基金信息时出错 {lj_id}: {e}")
            continue

    log.logger.info(f"处理了{processed_funds_count}个基金，选中{selected_funds_count}个基金")
    
    if len(content) > 0:
        content = f'今日关注：\n{content}\n'
        log.logger.info(content)
    else:
        log.logger.info('无车')


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
    # url_rt = 'https://buy.vmall.com/getSkuRushbuyInfo.json'
    # res_rt = requests.get(url_rt)
    # rt = res_rt.json()['currentTime']
    url_gz = f'http://fundgz.1234567.com.cn/js/{fundCode}.js'
    param_gz = {}
    res_gz = req(url_gz, param_gz, header, 'gz')
    if res_gz == False:
        return res_gz
    else:
        res_gz_text = res_gz.text
        res_gz_text = res_gz_text[res_gz_text.find(
            '(')+1: res_gz_text.rfind(')')]
        if len(res_gz_text) > 0 and res_gz_text != 'null':
            return json.loads(res_gz_text)
        else:
            return False


def get_gz_xc(fundCode):
    """
    根据代码获取当前所有估值XinCai
    para: fundCode
    return: False/Data
        yes: 昨日净值
        detail: time,gz *N
    """
    # url_gz_xc = f'https://app.xincai.com/fund/api/jsonp.json/var%20t1fu_{fundCode}=/XinCaiFundService.getFundYuCeNav'
    # param_gz_xc = {
    #     'symbol': fundCode,
    #     '___qn': 3
    # }
    url_gz_xc = f'https://hq.sinajs.cn/list=fu_{fundCode}'
    param_gz_xc = {
        # 'symbol': fundCode,
        # '___qn': 3
    }
    res_gz_xc = req(url_gz_xc, param_gz_xc, header, 'gz_xc')
    if res_gz_xc == False:
        return res_gz_xc
    else:
        res_gz_xc_text = res_gz_xc.text
        res_gz_xc_text = res_gz_xc_text[res_gz_xc_text.find(
            '(')+1: res_gz_xc_text.rfind(')')]
        if len(res_gz_xc_text) > 0 and res_gz_xc_text != 'null':
            return json.loads(res_gz_xc_text)
        else:
            return False


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
        if list_pj == []:
            return 'x'
        else:
            return list_pj[0]
        # for item_pj in list_pj:
        #     if item_pj['HTPJ'] != '':
        #         return item_pj['HTPJ']
        #     if item_pj['JAPJ'] != '':
        #         return item_pj['JAPJ']
        #     if item_pj['SZPJ3'] != '':
        #         return item_pj['SZPJ3']
        #     if item_pj['ZSPJ5'] != '':
        #         return item_pj['ZSPJ5']
        #     if item_pj['ZSPJ'] != '':
        #         return item_pj['ZSPJ']
        # return 'x'
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
            return list_gm[len(list_gm)-1][1]
        else:
            return 'x'


def watcher():
    """
    追踪
    para: -
    return: -/content
    """
    global content
    content_x = ''
    json_fs = None
    
    # 尝试从本地文件读取关注列表
    try:
        with open('focus.json', 'r', encoding='utf8') as focus:
            json_fs = json.load(focus)
            log.logger.info("成功从本地文件加载关注列表")
    except FileNotFoundError:
        log.logger.warning("本地focus.json文件不存在，尝试从远程获取")
    except json.JSONDecodeError as e:
        log.logger.error(f"本地focus.json文件格式错误: {e}")
    except Exception as e:
        log.logger.error(f"读取本地focus.json文件时发生异常: {e}")

    # 如果本地读取失败，尝试从远程获取
    if json_fs is None:
        log.logger.info("尝试从远程获取关注列表")
        url_fs1 = 'https://cdn.jsdelivr.net/gh/sirius2s/litkit@main/dumpcart/focus.json'
        url_fs2 = 'https://gh-proxy.com/https://raw.githubusercontent.com/Sirius2s/litkit/main/dumpcart/focus.json'

        try:
            res = req(url_fs2, None, None, 'focus')
            if res == False:
                raise Exception("通过url_fs2获取失败")
            json_fs = res.json()
            log.logger.info("成功从url_fs2获取关注列表")
        except Exception as e:
            log.logger.warning(f"通过url_fs2获取关注列表失败: {e}")
            try:
                res = req(url_fs1, None, None, 'focus')
                if res == False:
                    raise Exception("通过url_fs1获取失败")
                json_fs = res.json()
                log.logger.info("成功从url_fs1获取关注列表")
            except Exception as e:
                log.logger.error(f"通过url_fs1获取关注列表失败: {e}")
                return

    if json_fs is None:
        log.logger.info('关注列表为空，不进行追踪')
        return

    # 处理关注列表中的每个基金
    processed_count = 0
    alert_count = 0
    
    for item_fs in json_fs:
        processed_count += 1
        try:
            # 检查必需字段
            if 'fundcode' not in item_fs or 'buyin' not in item_fs or 'wpoint' not in item_fs:
                log.logger.warning(f"关注列表项缺少必要字段: {item_fs}")
                continue
                
            gz = get_gz(item_fs['fundcode'])
            if gz == False:
                log.logger.warning(f"获取基金{item_fs['fundcode']}估值失败")
                continue
                
            # 检查字段是否存在
            if 'gsz' not in gz:
                log.logger.warning(f"基金{item_fs['fundcode']}估值数据缺少gsz字段")
                continue
                
            # 检查是否达到预警点位
            try:
                current_price = float(gz['gsz'])
                buyin_price = float(item_fs['buyin'])
                warning_point = float(item_fs['wpoint'])
                threshold_price = buyin_price * warning_point
                
                # 当当前价格大于阈值价格时触发
                if current_price > threshold_price:
                    # 计算获利比例
                    profit_ratio = (current_price - buyin_price) / buyin_price * 100
                    content_x += f"{item_fs['fundcode']}: {gz['gsz']} (获利 {profit_ratio:.2f}%)\n"
                    alert_count += 1
                    log.logger.info(f"基金{item_fs['fundcode']}触发下车预警: 当前价{gz['gsz']} > 阈值{threshold_price:.4f} (获利 {profit_ratio:.2f}%)")
            except ValueError as e:
                log.logger.error(f"数值转换错误，基金{item_fs['fundcode']}: {e}")
                continue
            except ZeroDivisionError as e:
                log.logger.error(f"计算获利比例时发生除零错误，基金{item_fs['fundcode']}: {e}")
                continue
        except Exception as e:
            log.logger.error(f"处理基金{item_fs.get('fundcode', 'unknown')}时发生异常: {e}")
            continue

    log.logger.info(f"完成关注列表处理，总计{processed_count}个基金，{alert_count}个触发预警")

    if len(content_x) > 0:
        content_x = f'下车：\n{content_x}\n'
        log.logger.info(content_x)
        content = content + content_x
    else:
        log.logger.info('无下车信号')


def dumpcart():
    log.logger.info("开始执行基金筛选程序")
    start_time = datetime.datetime.now()
    
    if is_trade_day(datetime.datetime.now().date()):
        log.logger.info('今天是交易日，开始筛选基金')
    else:
        log.logger.info('今天不是交易日，程序退出')
        return

    jlj()
    watcher()

    if len(content) > 0:
        notification.notify_QW_AM(title, content)
        notification.notify_QMSG(title, content)
        log.logger.info("已发送通知")
    else:
        log.logger.info('无符合条件的基金，不发送通知')
        notification.notify_QW_AM(title, '无车&不下')
    
    end_time = datetime.datetime.now()
    duration = (end_time - start_time).total_seconds()
    log.logger.info(f"程序执行完成，耗时: {duration:.2f}秒")


if __name__ == '__main__':
    # get_trade_day(5)
    # get_trade_day(0)
    # print(get_gm('002601'))
    dumpcart()
    # print(get_gz_xc('002601'))
