import tushare as ts
import logging
# ts.get_k_data(code='', start='2018-03-31', end='2021-03-31', )
from concurrent.futures import FIRST_COMPLETED, ALL_COMPLETED, FIRST_EXCEPTION
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import wait
import logging
from multiprocessing import Pool
import pdb
import time


logging.basicConfig(level=logging.INFO)
LOG = logging.getLogger(__name__)

# data = ts.get_hist_data('AAPL')
# data = ts.get_stock_basics()
# logging.basicConfig(level=logging.DEBUG)
#pro = ts.pro_api(token='8a33fddfd49bc0cbe53e5c7fbe66a201e71181db6ffe48503002dbca')


#df = pro.us_daily(ts_code='SHI', start_date='20180331', end_date='20210331')

# print(data)


# df.to_excel('C:/Users/laizhen/Desktop/照片/us_daily_SHI.xlsx')


class ThreadPoolExecutorWithLimit(ThreadPoolExecutor):
    def __init__(self, max_workers):
        self._task_futures = set()
        self._limit = max_workers
        LOG.debug("max_workers: %s", max_workers)
        super(ThreadPoolExecutorWithLimit, self).__init__(max_workers)

    def submit(self, fn, *args, **kwargs):
        if len(self._task_futures) >= self._limit:
            done, self._task_futures = wait(self._task_futures,
                                            return_when=FIRST_COMPLETED)
        future = super(ThreadPoolExecutorWithLimit, self).submit(fn, *args,
                                                                 **kwargs)
        self._task_futures.add(future)
        return future


def pp(al):
    for i in range(3):
        global a2
        a2 = al
        print(a2[i])
        al.pop(i)

    # if i % 2 == 0:
    #     time.sleep(2)
    #     return
    # else:
    #     time.sleep(4)
    #     raise Exception




def main():
    # pool, process_dict = Pool(5), dict()
    # for i in range(9):
    #     process = pool.apply_async(func=migrate, args=(_servers, source_host, host_map[source_host]))
    #     process_dict[source_host] = process
    # pool.close()
    # pool.join()

    executor = ThreadPoolExecutorWithLimit(max_workers=5)
    # executor = ThreadPoolExecutor(max_workers=5)
    al = range(9)
    for i in range(9):
        executor.submit(pp, al)


if __name__ == '__main__':
    main()