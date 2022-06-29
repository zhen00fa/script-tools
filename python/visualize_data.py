#!/usr/bin/env python
import json
import matplotlib.pyplot as plt
from numpy import *

def printout(x, y, label):
    plt.plot(x, y, label=label)


def split(array):
    result = []
    for d in array:
        for i in range(len(d)):
            if len(result) < i + 1:
                result.append([])
            else:
                result[i].append(d[i])
    return result


with open('results', 'r') as f:
    results = json.loads(''.join(f.readlines()))


for s, data in results.items():
    # max_iter = max([i for i, _, _ in data])
    for i in data:
        avrg = mean([j[1] for j in data[i]])
        if avrg:
            printout(i, avrg, '%s-%s' % (s, i))
    # for i in range(1, max_iter + 1):
    #     ret = split([[ii, jj, kk] for ii, jj, kk in data if ii == i])
    #     if ret:
    #
    #         printout(ret[1], ret[2], '%s-%s' % (s, i))


plt.legend()
plt.xlabel('batch size')
plt.ylabel('elapsed time')
plt.title("test")
plt.show()



import json

if __name__ == '__main__':
        path = "/tmp/pyrasite-2038673-objects.json"
        ans = []
        with open(path, 'r') as f:
            for l in f:
                if l:
                    try:
                        i = json.loads(l)
                        # if i['type'] == 'dict':
                        ans.append(i)
                    except Exception as e:
                        print(i)

        ans = sorted(ans, key=lambda x: -x['size'])
        with open("ans.json", 'w') as f:
            for i in ans:
                f.write("%s \n" % (i))