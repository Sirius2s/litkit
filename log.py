import logging
import logging.handlers
from datetime import datetime, timedelta, timezone

bj_time = datetime.utcnow().replace(tzinfo=timezone.utc)
bj_time = bj_time.astimezone(timezone(timedelta(hours=8)))
lf_name = bj_time.strftime("%Y%m%d")

logger = logging.getLogger("logger")

handler1 = logging.StreamHandler()
handler2 = logging.FileHandler(filename=f"""/tmp/{lf_name}.log""", encoding="utf-8")

logger.setLevel(logging.DEBUG)
# handler1.setLevel(logging.WARNING)
handler1.setLevel(logging.DEBUG)
handler2.setLevel(logging.DEBUG)

# formatter = logging.Formatter("%(asctime)s %(name)s %(levelname)s %(message)s")
formatter = logging.Formatter("%(message)s")
handler1.setFormatter(formatter)
handler2.setFormatter(formatter)

logger.addHandler(handler1)
logger.addHandler(handler2)

# 分别为 10、30、30
# print(handler1.level)
# print(handler2.level)
# print(logger.level)

if __name__ == '__main__':
    logger.debug('This is a customer debug message')
    logger.info('This is a customer info message')
    logger.warning('This is a customer warning message')
    logger.error('This is a customer error message')
    logger.critical('This is a customer critical message')