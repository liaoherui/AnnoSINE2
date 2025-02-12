import pandas as pd
import subprocess
import os.path
import shlex
import sys
import math
import re

nonmatch_pattern = re.compile(r"NM:i:(\d+);")
cigar_pattern = re.compile(r"cg:Z:([A-Za-z0-9]+)")


class QualityCalculations:
    def __init__(self, genome_size=832400799511):
        self._k = 0.1
        self._lambda = 1.58
        self.genome_size = genome_size

    def calc_bitscore(self, alen, nonmatch):
        score = alen - 2 * nonmatch
        return (score * self._lambda - math.log(self._k)) / math.log(2.0)

    def calc_evalue(self, alen, nonmatch):
        # we want to keep -self._lambda * score negative otherwise we could start
        #   getting overflow errors. So we don't let score go below 0.
        score = max(0, alen - 2 * nonmatch)
        return self._k * alen * self.genome_size * math.exp(-self._lambda * score)

    def calc_gap_openings(self, cigar):
        go = 0
        for char in cigar:
            if char == "I" or char == "D":
                go += 1
        return go


def standardize_paf(paf_file):
    """paf files can have variable number of optional key-value pairs"""
    out = subprocess.run(shlex.split("sed 's/\t/;/13g' -i {}".format(paf_file)))

    assert out.returncode == 0


def main(paf_file,odir):
    name = os.path.basename(paf_file.replace(".paf", ""))
    standardize_paf(paf_file)
    df = pd.read_csv(
        paf_file,
        delimiter="\t",
        header=None,
        names=[
            "qname",
            "qlen",
            "qstart",
            "qend",
            "strand",
            "tname",
            "tlen",
            "tstart",
            "tend",
            "nmatch",
            "alen",
            "mapq",
            "other",
        ],
    )
    try:
        df["nonmatch"] = df.other.map(
            lambda x: int(re.search(nonmatch_pattern, x).group(1))
        )
    except:
        df["nonmatch"]=0
    qc = QualityCalculations()
    try:
        df["gap_openings"] = df.other.map(
            lambda x: qc.calc_gap_openings(re.search(cigar_pattern, x).group(1))
        )
    except:
        df["gap_openings"] =0
    df["bitscore"] = [
        qc.calc_bitscore(a, n) for a, n in zip(df["alen"], df["nonmatch"])
    ]
    df["evalue"] = [qc.calc_evalue(a, n) for a, n in zip(df["alen"], df["nonmatch"])]
    df["percent_ident"] = [
        (nmatch / a) * 100 for a, nmatch in zip(df["alen"], df["nmatch"])
    ]
    df = df.round({"bitscore": 3, "percent_ident": 3})
    m = df["strand"] == "-"
    df.loc[m, ["tstart", "tend"]] = (df.loc[m, ["tend", "tstart"]].values)

    blast = df.loc[
        :,
        [
            "qname",
            "tname",
            "percent_ident",
            "alen",
            "nonmatch",
            "gap_openings",
            "qstart",
            "qend",
            "tstart",
            "tend",
            "evalue",
            "bitscore",
        ],
    ]
    blast["qstart"] = blast["qstart"] + 1
    blast.loc[~m, "tstart"] = blast.loc[~m, "tstart"] + 1
    blast.loc[m, "tend"] = blast.loc[m, "tend"] + 1
    blast.loc[:, "tstart"] = blast.loc[:, "tstart"].astype(int)
    blast.loc[:, "tend"] = blast.loc[:, "tend"].astype(int)

    blast.to_csv(f"{odir}/{name}.out", sep="\t", index=None, header=False)


if __name__ == "__main__":
    paf_file = sys.argv[1]
    odir=sys.argv[2]
    main(paf_file,odir)
