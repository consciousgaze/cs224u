from scipy.spatial import distance
import sklearn.metrics.pairwise
import inspect
import logging
import os.path
import sys
from math import isnan

sentenceEnds = ['...', '.', '.', '!', '?']

def sentenceSeg(doc):
    # new paragraph is meaningless here
    doc = doc.replace('\n', '').replace('\r', '')
    # split the doc with sentence ending marks
    initialRegions = [doc]
    for sentenceEnd in sentenceEnds:
        tmp = []
        for region in initialRegions:
            tmp += region.split(sentenceEnd)
        initialRegions = tmp
    return [x for x in initialRegions if x!='']

def cosine(x, y):
    rlt =  distance.cosine(x, y)
    if isnan(rlt):
        # TODO: what's the best
        return -2
    return rlt

def cosine_sparse(x, y):
  return sklearn.metrics.pairwise.cosine_similarity(x, y)

class PriorityQueue:
    def __init__(self):
        self._queue = []
        self._index = 0

    def push(self, item, priority):
        heapq.heappush(self._queue, (-priority, self._index, item))
        self._index += 1

    def pop(self):
        return heapq.heappop(self._queue)[-1]

    def isEmpty():
        return self._queue==[]
