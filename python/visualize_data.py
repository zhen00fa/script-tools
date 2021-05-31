#!/usr/bin/env python
import json
import matplotlib.pyplot as plt


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
    max_iter = max([i for i, _, _ in data])
    for i in range(1, max_iter + 1):
        ret = split([[ii, jj, kk] for ii, jj, kk in data if ii == i])
        if ret:

            printout(ret[1], ret[2], '%s-%s' % (s, i))


plt.legend()
plt.xlabel('batch size')
plt.ylabel('elapsed time')
plt.title("test")
plt.show()

