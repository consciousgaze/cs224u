#!/usr/bin/env python
"""
Usage: %(program)s model_prefix data_dir

Run model.

model_prefix should be something like "wiki_en" corresponding to the
filename prefix of the ESA model files, which must be in the current directory.

data_dir should be the base folder for the newsgroups data.

Example:
    %(program)s --sample_size 20 --model GloveModel --depth 6 --decay 0.9 glove.6B.300d.txt 20news-18828/ testrecords.txt
"""

from glove import GloveModel
from esa import ESAModel, ClusteredESAModel
from models import LDAModel, LSAModel
from util import sentenceSeg, PriorityQueue, cosine, DataSet, function_name, \
                 MaxTopicFeatureExtractor, HierarchicalTopicFeatureExtractor, \
                 FlatFeatureExtractor, TopKLayerHierarchicalFeatureExtractor, \
                 topKHierarchicalSegments
#from distributedwordreps import ShallowNeuralNetwork
import argparse
import inspect
import json
import logging
import os.path
import sys
import time
import numpy as np
import scipy.sparse

from sklearn.naive_bayes import GaussianNB, MultinomialNB
from sklearn.linear_model import LogisticRegression
from sklearn.svm import SVC
from sklearn.metrics import classification_report, f1_score, precision_recall_fscore_support

try:
   import cPickle as pickle
except:
   import pickle

import gensim
from gensim.corpora import Dictionary
from gensim.models import TfidfModel
from gensim.similarities import Similarity
from nltk.tokenize import wordpunct_tokenize
from os import listdir

program = os.path.basename(sys.argv[0])
logger = logging.getLogger(program)

logging.basicConfig(format='%(asctime)s : %(levelname)s : %(message)s')
logging.root.setLevel(level=logging.INFO)

DEFAULT_MODEL = 'LDAModel' #'GloveModel'
DEFAULT_FEATURIZER = 'MaxTopicFeatureExtractor'
DEFAULT_NUM_REGIONS = 15
DEFAULT_SAMPLE_SIZE = 20

def evaluation(model = None,
               clf = GaussianNB,
               model_prefix = None,
               data_dir = '20news-18828',
               result_record = None,
               record_fname = None,
               sample_size = None,
               depth = 0,
               decay = 1.0,
               fullLayer = True):
    if result_record is None:
        raise Exception("Must pass result_record")
    if record_fname is None:
        raise Exception("Must pass record_fname")
    train = []
    trainY = []
    test = []
    testY = []

    # load data
    pickle_suffix = ".%s.segmented.pickle" % (model.__class__.__name__,)
    baseFolder = data_dir
    cats = sorted(listdir(baseFolder))
    for catIdx, cat in enumerate(cats):
        logger.info('Processing category %s (%d/%d)', cat, catIdx, len(cats))
        dirpath = os.path.join(baseFolder, cat)
        #print dirpath

        try:
            filtered_docs = []
            for d in listdir(dirpath):
                #print d
                if d.endswith(pickle_suffix):
                    filtered_docs.append(d)
            docs = sorted(filtered_docs, key = lambda n: int(n.split(".")[0]))
            if sample_size is not None and sample_size != 0:
                docs = docs[:sample_size]
        except:
            continue
        numDocs = len(docs)
        #logger.info("Docs: %s", docs)
        for docIdx, doc_filename in enumerate(docs):
            doc_filename = os.path.join(baseFolder, cat, doc_filename)
            logger.info('processing document %s (%d/%d)', doc_filename, docIdx, numDocs)
            doc = gensim.utils.unpickle(doc_filename)
            segments = doc[0]
            regions = doc[1]
            feature = topKHierarchicalSegments(segments,
                                               regions,
                                               feature_extractor = model,
                                               depth = depth,
                                               fullLayer = fullLayer,
                                               decay = decay)

            logger.debug('doc %d feature extracted', docIdx)
            if docIdx < numDocs*0.9:
                train.append(feature)
                trainY.append(catIdx)
            else:
                test.append(feature)
                testY.append(catIdx)
            logger.debug('-----')

    # Convert to sparse format for compact storage and minimal memory usage.
    train = np.vstack(train)
    trainY = np.hstack(trainY)
    test = np.vstack(test)
    testY = np.hstack(testY)

    logger.info("Shape of training set: %s", train.shape)
    logger.info("Shape of test set: %s", test.shape)

    num_labels = len(cats)
    logger.info("Number of labels: %d", num_labels)

    # Instantiate classifiers.
    classifiers = [
        LogisticRegression(),
        MultinomialNB()
        #,
        #ShallowNeuralNetwork(input_dim = feature_extractor.num_features(),
        #                     hidden_dim = 60,
        #                     output_dim = num_labels)
    ]

    for clf in classifiers:
        classifier_name = clf.__class__.__name__
        if classifier_name is None:
            raise Exception("Unable to get name of classifier class", clf_class)
        logger.info("Evaluating on classifier %s...", classifier_name)

        clf.fit(train, trainY)
        logger.info('training finished')

        # Record training error.
        trainPredY = clf.predict(train)
        print("Training error:")
        print(classification_report(trainY, trainPredY, target_names = cats, digits = 5))

        # Make prediction.
        testPredY = clf.predict(test)

        # Print detailed report.
        print("Test error:")
        print(classification_report(testY, testPredY, target_names = cats, digits = 5))

        # Save the important metrics.
        precision, recall, f1, support = \
            precision_recall_fscore_support(testY, testPredY, average='weighted')
        result_record[classifier_name + "_precision"] = precision
        result_record[classifier_name + "_recall"] = recall
        result_record[classifier_name + "_f1"] = f1
        #result_record[classifier_name + "_support"] = support

        precision, recall, f1, support = \
            precision_recall_fscore_support(trainY, trainPredY, average='weighted')
        result_record[classifier_name + "_f1_train"] = f1

    with open(record_fname, "a") as records_out:
        json.dump(result_record, records_out, sort_keys = True)
        records_out.write("\n")

if __name__ == "__main__":

    # Define command-line args.
    parser = argparse.ArgumentParser(description='Evaluate topic classification approaches.',
                                     epilog=str(__doc__ % {'program': program}))
    parser.add_argument('--model', help=('Base feature model. Default: ' + DEFAULT_MODEL))
    parser.set_defaults(model=DEFAULT_MODEL)
    parser.add_argument('--featurizer',
                        help=('Higher level featurizer. Default: ' + DEFAULT_FEATURIZER))
    parser.set_defaults(featurizer=DEFAULT_FEATURIZER)

    parser.add_argument('--max_regions', type=int,
                        help=('Maximum regions to use. Default: ' + str(DEFAULT_NUM_REGIONS)))
    parser.set_defaults(max_regions=DEFAULT_NUM_REGIONS)

    parser.add_argument('--sample_size', type=int,
                        help=('How much to sample the dataset. Set to 0 to disable sampling. Default: ' + str(DEFAULT_SAMPLE_SIZE)))
    parser.set_defaults(sample_size=DEFAULT_SAMPLE_SIZE)

    parser.add_argument('--depth', type=int,
                        help=('Depth of the TopK layer hierarchical feature extractor'))
    parser.add_argument('--decay', type=float,
                        help=('Decay of the TopK layer hierarchical feature extractor'))

    parser.add_argument('--reverse', dest='reverse', action='store_true', help='reverse region iter')
    parser.add_argument('--no-reverse', dest='reverse', action='store_false', help='reverse region iter')

    parser.add_argument('model_prefix', help='Model prefix of passed to the model constructor')
    parser.add_argument('data_dir', help='Directory in which to find the 20-newsgroups data.')
    parser.add_argument('record_fname', help='Filename to append result records.')
    args = parser.parse_args()

    # load base feature model
    model_clazz = globals()[args.model]
    model = model_clazz(args.model_prefix)
    #model = ESAModel(args.model_prefix) # ESA is not working very well.
    #model = GloveModel(args.model_prefix)

    """
    # load secondary feature extractor
    featurizer_clazz = globals()[args.featurizer]
    options = {'base_feature_extractor': model,
               'max_regions': args.max_regions,
               'reverse': args.reverse,
               'depth': args.depth,
               'decay': args.decay}
    featurizer = featurizer_clazz(options)
    #featurizer = MaxTopicFeatureExtractor(options)
    """

    result_record = {}
    result_record['timestamp'] = time.asctime()
    result_record['model_prefix'] = args.model_prefix
    result_record['model'] = args.model
    result_record['featurizer'] = "TopKLayerHierarchicalFeatureExtractor"
    result_record['max_regions'] = args.max_regions
    if args.depth is not None: result_record['depth'] = args.depth
    if args.decay is not None: result_record['decay'] = args.decay
    result_record['sample_size'] = args.sample_size

    evaluation(model = model,
               model_prefix = args.model_prefix,
               data_dir = args.data_dir,
               result_record = result_record,
               record_fname = args.record_fname,
               sample_size = args.sample_size,
               depth = args.depth,
               decay = args.decay)
