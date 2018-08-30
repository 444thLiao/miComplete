# Copyright (c) Eric Hugoson.
# See LICENSE for details.

"""
Module investigates the completeness of a given genome with respect to a given
set of HMM makers, in so far as it runs HMMer and parses the output.


"""

from __future__ import print_function, division
from collections import defaultdict
import sys
import math
import subprocess
import re
import os
import logging
from termcolor import cprint


class calcCompleteness():
    def __init__(self, fasta, base_name, hmms, evalue=1e-10, weights=None,
                 hlist=False, linkage=False, logger=None, lenient=False):
        self.base_name = base_name
        self.evalue = "-E %s" % (str(evalue))
        self.tblout = "%s.tblout" % (self.base_name)
        self.hmms = hmms
        self.fasta = fasta
        self.linkage = linkage
        self.weights = weights
        self.logger = logger
        logger.log(logging.WARNING, "test")
        self.lenient = lenient
        print("Starting completeness for " + fasta, file=sys.stderr)
        self.hmm_names = set({})
        with open(self.hmms) as hmmfile:
            for line in hmmfile:
                if re.search('^NAME', line):
                    name = line.split(' ')
                    self.hmm_names.add(name[2].strip())

    def hmm_search(self):
        """
        Runs hmmsearch using the supplied .hmm file, and specified evalue.
        Produces an output table from hmmsearch, function returns its name.
        """
        hmmsearch = ["hmmsearch", self.evalue, "--tblout", self.tblout,
                     self.hmms, self.fasta]
        if sys.version_info > (3, 4):
            comp_proc = subprocess.run(hmmsearch, stdout=subprocess.DEVNULL)
            errcode = comp_proc.returncode
        else:
            errcode = subprocess.call(hmmsearch, stdout=open(os.devnull, 'wb'),
                                      stderr=subprocess.STDOUT)
        if errcode > 0:
            cprint("Warning:", 'red', end=' ', file=sys.stderr)
            print("Error thrown by HMMER, is %s empty?" % self.fasta,
                  file=sys.stderr)
        return self.tblout, errcode

    def get_completeness(self, multi_hit=1/2, strict=False):
        """
        Reads the out table of hmmer to find which hmms are present, and
        which are duplicated. Duplicates are only considered duplicates if
        the evalue of the secondary hit is within the squareroot of the best
        hit.

        Returns: Dict of all hmms found with evalues for best and possible
        deulicates, list of hmms with duplicates, and names of all hmms
        which were searched for.
        """
        _, errcode = self.hmm_search()
        if errcode > 0:
            return 0, 0, 0
        self.hmm_matches = defaultdict(list)
        self.seen_hmms = set()
        # gather gene name and evalue in dict by key[hmm]
        for hmm in self.hmm_names:
            with open(self.tblout) as hmm_table:
                for found_hmm in hmm_table:
                    if re.match("#$", found_hmm):
                        break
                    if re.search("^" + hmm + "$", found_hmm.split()[2]):
                        found_hmm = found_hmm.split()
                        # gathers name, evalue, score, bias
                        self.hmm_matches[hmm].append([found_hmm[0], found_hmm[4],
                                                      found_hmm[5], found_hmm[6],
                                                      found_hmm[7]])
                        self.seen_hmms.add(hmm)
        self.filled_hmms = defaultdict(list)
        # section can be expanded to check for unique gene matches
        for hmm, gene_matches in self.hmm_matches.items():
            # sort by lowest eval to fill lowest first
            for gene in sorted(gene_matches, key=lambda ev: float(ev[1])):
                if not self.lenient:
                    # skip if sequence match found to be dubious
                    if suspiscion_check(gene):
                        continue
                if hmm not in self.filled_hmms:
                    self.filled_hmms[hmm].append(gene)
                elif float(gene[1]) < pow(float(self.filled_hmms[hmm][0][1]), 1/2):
                    self.filled_hmms[hmm].append(gene)
        self.dup_hmms = [hmm for hmm, genes in self.filled_hmms.items()
                         if len(genes) > 1]
        #if self.hlist and not self.linkage:
        #    self.print_hmm_lists()
        return self.filled_hmms, self.dup_hmms, self.hmm_names


    def quantify_completeness(self):
        """
        Function returns the number of found markers, duplicated markers, and
        total number of markers.
        """
        filled_hmms, _, hmm_names = self.get_completeness()
        try:
            num_foundhmms = len(filled_hmms)
            num_hmms = len(hmm_names)
        except TypeError:
            num_foundhmms = 0
            num_totalhmms = 0
            num_hmms = 0
            return num_foundhmms, num_totalhmms, num_hmms
        all_duphmms = [len(genes) for hmm, genes in self.filled_hmms.items()]
        num_totalhmms = sum(all_duphmms)
        return num_foundhmms, num_totalhmms, num_hmms

    def print_hmm_lists(self, directory='.'):
        """Prints the contents of found, duplicate and and not found markers"""
        if directory:
            try:
                os.mkdir(directory)
            except FileExistsError:
                pass
        hlist_name = directory + "/%s_hmms.list" % (self.base_name)
        with open(hlist_name, 'w+') as seen_list:
            for each_hmm in self.seen_hmms:
                seen_list.write("%s\n" % each_hmm)
        dup_list_name = directory + "/%s_hmms_duplicate.list" % (self.base_name)
        with open(dup_list_name, 'w+') as dup_list:
            for each_dup in self.dup_hmms:
                dup_list.write("%s\n" % each_dup)
        missing_list_name = directory + "/%s_hmms_missing.list" % (self.base_name)
        with open(missing_list_name, 'w+') as missing_list:
            for hmm in self.hmm_names:
                if hmm not in self.seen_hmms:
                    missing_list.write("%s\n" % hmm)
        return hlist_name

    def attribute_weights(self):
        """Using the markers found and duplicates from get_completeness(), and
        provided weights, adds up weight of present and duplicate markers"""
        weighted_complete = 0
        weighted_redun = 0
        for hmm in self.seen_hmms:
            with open(self.weights, 'r') as weights:
                for each_weight in weights:
                    if re.match(hmm + "\s", each_weight):
                        weighted_complete += float(each_weight.split()[1])
        for hmm in self.dup_hmms:
            with open(self.weights, 'r') as weights:
                for each_weight in weights:
                    if re.match(hmm + "\t", each_weight):
                        weighted_redun += float(each_weight.split()[1])
        weighted_redun = round(((weighted_redun + weighted_complete) /
                                weighted_complete), 3)
        weighted_complete = round(weighted_complete, 3)
        return weighted_complete, weighted_redun

def suspiscion_check(gene_match):
    """Check if bias is in the same order of magnitude as the match
    and if the evalue for the best domain is high. Both indicating
    a dubious result."""
    if len(str(gene_match[3])) >= len(str(gene_match[2])) or \
            float(gene_match[4]) > 0.01:
        cprint(gene_match, "magenta", file=sys.stderr)
        return True
    return False
