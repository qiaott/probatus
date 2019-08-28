import itertools
import warnings

import pandas as pd
from tqdm import tqdm

from pyrisk.binning import SimpleBucketer, AgglomerativeBucketer, QuantileBucketer
from pyrisk.stat_tests import es, ks, psi


class DistributionStatistics(object):
    """
    Wrapper that applies a statistical method and a binning strategy to data.

    Parameters
    ----------
    statistical_test: string
        Statistical method to apply, statistical methods implemented:
            'ES': Epps-Singleton
            'KS': Kolmogorov-Smirnov statistic
            'PSI': Population Stability Index

    binning_strategy: string or None
        Binning strategy to apply, binning strategies implemented:
            'SimpleBucketer': equally spaced bins
            'AgglomerativeBucketer': binning by applying the Scikit-learn implementation of Agglomerative Clustering
            'QuantileBucketer': bins with equal number of elements

    bin_count: integer or None
        In case binning_strategy is not None, specify the number of bins to be used by the binning strategy

    Example:
    d1 = np.histogram(np.random.normal(size=1000), 10)[0]
    d2 = np.histogram(np.random.normal(size=1000), 10)[0]

    myTest = DistributionStatistics('KS', 'SimpleBucketer', bin_count=10)
    myTest.fit(d1, d2, verbose=True)

    """
    statistical_test_list = ['ES', 'KS', 'PSI']
    binning_strategy_list = ['simplebucketer', 'agglomerativebucketer', 'quantilebucketer', None]

    def __init__(self, statistical_test, binning_strategy, bin_count=None):
        self.statistical_test = statistical_test.upper()
        self.binning_strategy = binning_strategy
        self.bin_count = bin_count
        self.fitted = False

        if self.statistical_test.upper() not in self.statistical_test_list:
            raise NotImplementedError(f"The statistical test should be one of {self.statistical_test_list}")
        elif self.statistical_test.upper() == 'ES':
            self._statistical_test_function = es
        elif self.statistical_test.upper() == 'KS':
            self._statistical_test_function = ks
        elif self.statistical_test.upper() == 'PSI':
            self._statistical_test_function = psi

        if self.binning_strategy:
            if self.binning_strategy.lower() not in self.binning_strategy_list:
                raise NotImplementedError(f"The binning strategy should be one of {self.binning_strategy_list}")
            if self.binning_strategy.lower() == 'simplebucketer':
                self.binner = SimpleBucketer(bin_count=self.bin_count)
            elif self.binning_strategy.lower() == 'agglomerativebucketer':
                self.binner = AgglomerativeBucketer(bin_count=self.bin_count)
            elif self.binning_strategy.lower() == 'quantilebucketer':
                self.binner = QuantileBucketer(bin_count=self.bin_count)

    def __repr__(self):
        repr_ = f"DistributionStatistics object\n\tstatistical_test: {self.statistical_test}"
        if self.binning_strategy:
            repr_ += f"\n\tbinning_strategy: {self.binning_strategy}\n\tbin_count: {self.bin_count}"
        else:
            repr_ += "\n\tNo binning applied"
        if self.fitted:
            repr_ += f"\nResults\n\tvalue {self.statistical_test}-statistic: {self.statistic}"
        if hasattr(self, 'p_value'):
            repr_ += f"\n\tp-value: {self.p_value}"
        return repr_

    def fit(self, d1, d2, verbose=False, **kwargs):
        """
        Fit the DistributionStatistics object to data; i.e. apply the statistical test

        Args:
            d1: distribution 1
            d2: distribution 2
            verbose:
            **kwargs:
                for PSI specific: set `n` and `m` as the size of the dataset *before* bucketing

        Returns: statistic value and p_value (if available, e.g. not for PSI)

        """
        if self.binning_strategy:
            self.binner.fit(d1)
            d1_preprocessed = self.binner.counts
            self.binner.fit(d2)
            d2_preprocessed = self.binner.counts
        else:
            d1_preprocessed, d2_preprocessed = d1, d2

        res = self._statistical_test_function(d1_preprocessed, d2_preprocessed, verbose=verbose, **kwargs)
        self.fitted = True
        if type(res) == tuple:
            self.statistic, self.p_value = res
            return self.statistic, self.p_value
        else:
            self.statistic = res
            return self.statistic


class AutoDist(object):
    def __init__(self, statistical_tests='all', binning_strategies='all'):
        self.fitted = False
        if statistical_tests == 'all':
            self.statistical_tests = DistributionStatistics.statistical_test_list
        elif isinstance(statistical_tests, str):
            self.statistical_tests = [statistical_tests]
        else:
            self.statistical_tests = statistical_tests
        if binning_strategies == 'all':
            self.binning_strategies = DistributionStatistics.binning_strategy_list
        elif isinstance(binning_strategies, str):
            self.binning_strategies = [binning_strategies]
        else:
            self.binning_strategies = binning_strategies

    def __repr__(self):
        repr_ = "AutoDist object"
        if not self.fitted:
            repr_ += f"\n\tAutoDist not fitted"
        if self.fitted:
            repr_ += f"\n\tAutoDist fitted"
        repr_ += f"\n\tstatistical_tests: {self.statistical_tests}"
        repr_ += f"\n\tbinning_strategies: {self.binning_strategies}"
        return repr_

    def fit(self, df1, df2, columns, return_failed_tests=True):
        warnings.filterwarnings("ignore", module=r'scipy*')  # to suppress the numerous warnings of scipy
        result_all = pd.DataFrame()
        for col, stat_test, bin_strat in tqdm(
                list(itertools.product(columns, self.statistical_tests, self.binning_strategies))):
            dist = DistributionStatistics(statistical_test=stat_test, binning_strategy=bin_strat, bin_count=10)
            try:
                _ = dist.fit(df1[col], df2[col])
                statistic = dist.statistic
                if hasattr(dist, 'p_value'):
                    p_value = dist.p_value
                else:
                    p_value = None
            except:
                statistic, p_value = 'an error occurred', None
                pass
            result_ = {'column': col, 'statistical_test': stat_test, 'binning_strategy': bin_strat,
                       'statistic': statistic, 'p_value': p_value}
            result_all = result_all.append(result_, ignore_index=True)
        warnings.filterwarnings('default')
        if not return_failed_tests:
            result_all = result_all[result_all['statistic'] != 'an error occurred']
        self.fitted = True
        self._result = result_all[['column', 'statistical_test', 'binning_strategy', 'statistic', 'p_value']]

        # create pivot table as final output
        self.result = pd.pivot_table(self._result, values=['statistic', 'p_value'], index='column',
                                     columns=['statistical_test', 'binning_strategy'], aggfunc='sum')
        self.result.columns = self.result.columns.to_series().str.join('_')
        self.result.reset_index(inplace=True)
        return self.result
