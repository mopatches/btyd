# -*- coding: utf-8 -*-
from __future__ import print_function

import numpy as np
import pandas as pd
import numpy.testing as npt
import pytest
import os
from collections import OrderedDict

import btyd as lt
import btyd.utils as utils
from btyd.datasets import (
    load_cdnow_summary,
    load_cdnow_summary_data_with_monetary_value,
    load_donations,
    load_transaction_data,
)

PATH_SAVE_MODEL = "./base_fitter.pkl"
PATH_SAVE_BGNBD_MODEL = "./betageo_fitter.pkl"


class TestBaseFitter:
    def test_repr(self):
        base_fitter = lt.BaseFitter()
        assert repr(base_fitter) == "<btyd.BaseFitter>"
        base_fitter.params_ = pd.Series(dict(x=12.3, y=42))
        base_fitter.data = np.array([1, 2, 3])
        assert (
            repr(base_fitter)
            == "<btyd.BaseFitter: fitted with 3 subjects, x: 12.3, y: 42.0>"
        )
        base_fitter.data = None
        assert repr(base_fitter) == "<btyd.BaseFitter: x: 12.3, y: 42.0>"

    def test_unload_params(self):
        base_fitter = lt.BaseFitter()
        with pytest.raises(ValueError):
            base_fitter._unload_params()
        base_fitter.params_ = pd.Series(dict(x=12.3, y=42))
        npt.assert_array_almost_equal([12.3, 42], base_fitter._unload_params("x", "y"))

    def test_save_load_model(self):
        base_fitter = lt.BaseFitter()
        base_fitter.save_model(PATH_SAVE_MODEL)
        assert os.path.exists(PATH_SAVE_MODEL) == True

        base_fitter_saved = lt.BaseFitter()
        base_fitter_saved.load_model(PATH_SAVE_MODEL)

        assert repr(base_fitter) == repr(base_fitter_saved)
        os.remove(PATH_SAVE_MODEL)


class TestBetaGeoBetaBinomFitter:
    @pytest.fixture()
    def donations(self):
        return load_donations()

    def test_model_has_standard_error_variance_matrix_and_confidence_intervals_(
        self, donations
    ):
        donations = donations
        bbtf = lt.BetaGeoBetaBinomFitter()
        bbtf.fit(
            donations["frequency"],
            donations["recency"],
            donations["periods"],
            donations["weights"],
        )
        assert hasattr(bbtf, "standard_errors_")
        assert hasattr(bbtf, "variance_matrix_")
        assert hasattr(bbtf, "confidence_intervals_")

    def test_params_out_is_close_to_Hardie_paper(self, donations):
        donations = donations
        bbtf = lt.BetaGeoBetaBinomFitter()
        bbtf.fit(
            donations["frequency"],
            donations["recency"],
            donations["periods"],
            donations["weights"],
        )
        expected = np.array([1.204, 0.750, 0.657, 2.783])
        npt.assert_array_almost_equal(
            expected,
            np.array(bbtf._unload_params("alpha", "beta", "gamma", "delta")),
            decimal=2,
        )

    def test_prob_alive_is_close_to_Hardie_paper_table_6(self, donations):
        """Table 6: P(Alive in 2002) as a Function of Recency and Frequency"""

        bbtf = lt.BetaGeoBetaBinomFitter()
        bbtf.fit(
            donations["frequency"],
            donations["recency"],
            donations["periods"],
            donations["weights"],
        )

        bbtf.data["prob_alive"] = bbtf.conditional_probability_alive(
            1, donations["frequency"], donations["recency"], donations["periods"]
        )

        # Expected probabilities for last year 1995-0 repeat, 1999-2 repeat, 2001-6 repeat
        expected = np.array([0.11, 0.59, 0.93])
        prob_list = np.zeros(3)
        prob_list[0] = bbtf.data[
            (bbtf.data["frequency"] == 0) & (bbtf.data["recency"] == 0)
        ]["prob_alive"]
        prob_list[1] = bbtf.data[
            (bbtf.data["frequency"] == 2) & (bbtf.data["recency"] == 4)
        ]["prob_alive"]
        prob_list[2] = bbtf.data[
            (bbtf.data["frequency"] == 6) & (bbtf.data["recency"] == 6)
        ]["prob_alive"]
        npt.assert_array_almost_equal(expected, prob_list, decimal=2)

    def test_conditional_expectation_returns_same_value_as_Hardie_excel_sheet(
        self, donations
    ):
        """
        Total from Hardie's Conditional Expectations (II) sheet.
        http://brucehardie.com/notes/010/BGBB_2011-01-20_XLSX.zip
        """

        bbtf = lt.BetaGeoBetaBinomFitter()
        bbtf.fit(
            donations["frequency"],
            donations["recency"],
            donations["periods"],
            donations["weights"],
        )
        pred_purchases = (
            bbtf.conditional_expected_number_of_purchases_up_to_time(
                5, donations["frequency"], donations["recency"], donations["periods"]
            )
            * donations["weights"]
        )
        expected = 12884.2  # Sum of column F Exp Tot
        npt.assert_almost_equal(expected, pred_purchases.sum(), decimal=0)

    def test_expected_purchases_in_n_periods_returns_same_value_as_Hardie_excel_sheet(
        self, donations
    ):
        """Total expected from Hardie's In-Sample Fit sheet."""

        bbtf = lt.BetaGeoBetaBinomFitter()
        bbtf.fit(
            donations["frequency"],
            donations["recency"],
            donations["periods"],
            donations["weights"],
        )
        expected = np.array([3454.9, 1253.1])  # Cells C18 and C24
        estimated = (
            bbtf.expected_number_of_transactions_in_first_n_periods(6)
            .loc[[0, 6]]
            .values.flatten()
        )
        npt.assert_almost_equal(expected, estimated, decimal=0)

    def test_fit_with_index(self, donations):

        bbtf = lt.BetaGeoBetaBinomFitter()
        index = range(len(donations), 0, -1)
        bbtf.fit(
            donations["frequency"],
            donations["recency"],
            donations["periods"],
            donations["weights"],
            index=index,
        )
        assert (bbtf.data.index == index).all() == True

        bbtf = lt.BetaGeoBetaBinomFitter()
        bbtf.fit(
            donations["frequency"],
            donations["recency"],
            donations["periods"],
            donations["weights"],
            index=None,
        )
        assert (bbtf.data.index == index).all() == False

    def test_fit_with_and_without_weights(self, donations):

        exploded_dataset = pd.DataFrame(columns=["frequency", "recency", "periods"])

        for _, row in donations.iterrows():
            exploded_dataset = exploded_dataset.append(
                pd.DataFrame(
                    [[row["frequency"], row["recency"], row["periods"]]]
                    * row["weights"],
                    columns=["frequency", "recency", "periods"],
                )
            )

        exploded_dataset = exploded_dataset.astype(np.int64)
        exploded_dataset.to_csv("exploded.csv")
        assert exploded_dataset.shape[0] == donations["weights"].sum()

        bbtf_noweights = lt.BetaGeoBetaBinomFitter()
        bbtf_noweights.fit(
            exploded_dataset["frequency"],
            exploded_dataset["recency"],
            exploded_dataset["periods"],
        )

        bbtf = lt.BetaGeoBetaBinomFitter()
        bbtf.fit(
            donations["frequency"],
            donations["recency"],
            donations["periods"],
            donations["weights"],
        )

        npt.assert_array_almost_equal(
            np.array(bbtf_noweights._unload_params("alpha", "beta", "gamma", "delta")),
            np.array(bbtf._unload_params("alpha", "beta", "gamma", "delta")),
            decimal=4,
        )


class TestGammaGammaFitter:
    @pytest.fixture()
    def cdnow_with_monetary_value(self):
        return load_cdnow_summary_data_with_monetary_value()

    def test_params_out_is_close_to_Hardie_paper(self, cdnow_with_monetary_value):
        returning_cdnow_with_monetary_value = cdnow_with_monetary_value[
            cdnow_with_monetary_value["frequency"] > 0
        ]
        ggf = lt.GammaGammaFitter()
        ggf.fit(
            returning_cdnow_with_monetary_value["frequency"],
            returning_cdnow_with_monetary_value["monetary_value"],
        )
        expected = np.array([6.25, 3.74, 15.44])
        npt.assert_array_almost_equal(
            expected, np.array(ggf._unload_params("p", "q", "v")), decimal=2
        )

    def test_conditional_expected_average_profit(self, cdnow_with_monetary_value):

        ggf = lt.GammaGammaFitter()
        ggf.params_ = pd.Series({"p": 6.25, "q": 3.74, "v": 15.44})

        summary = cdnow_with_monetary_value.head(10)
        estimates = ggf.conditional_expected_average_profit(
            summary["frequency"], summary["monetary_value"]
        )
        expected = np.array(
            [24.65, 18.91, 35.17, 35.17, 35.17, 71.46, 18.91, 35.17, 27.28, 35.17]
        )  # from Hardie spreadsheet http://brucehardie.com/notes/025/

        npt.assert_allclose(estimates.values, expected, atol=0.1)

    def test_customer_lifetime_value_with_bgf(self, cdnow_with_monetary_value):

        ggf = lt.GammaGammaFitter()
        ggf.params_ = pd.Series({"p": 6.25, "q": 3.74, "v": 15.44})

        bgf = lt.BetaGeoFitter()
        bgf.fit(
            cdnow_with_monetary_value["frequency"],
            cdnow_with_monetary_value["recency"],
            cdnow_with_monetary_value["T"],
        )

        ggf_clv = ggf.customer_lifetime_value(
            bgf,
            cdnow_with_monetary_value["frequency"],
            cdnow_with_monetary_value["recency"],
            cdnow_with_monetary_value["T"],
            cdnow_with_monetary_value["monetary_value"],
        )

        utils_clv = utils._customer_lifetime_value(
            bgf,
            cdnow_with_monetary_value["frequency"],
            cdnow_with_monetary_value["recency"],
            cdnow_with_monetary_value["T"],
            ggf.conditional_expected_average_profit(
                cdnow_with_monetary_value["frequency"],
                cdnow_with_monetary_value["monetary_value"],
            ),
        )
        npt.assert_equal(ggf_clv.values, utils_clv.values)

        ggf_clv = ggf.customer_lifetime_value(
            bgf,
            cdnow_with_monetary_value["frequency"],
            cdnow_with_monetary_value["recency"],
            cdnow_with_monetary_value["T"],
            cdnow_with_monetary_value["monetary_value"],
            freq="H",
        )

        utils_clv = utils._customer_lifetime_value(
            bgf,
            cdnow_with_monetary_value["frequency"],
            cdnow_with_monetary_value["recency"],
            cdnow_with_monetary_value["T"],
            ggf.conditional_expected_average_profit(
                cdnow_with_monetary_value["frequency"],
                cdnow_with_monetary_value["monetary_value"],
            ),
            freq="H",
        )
        npt.assert_equal(ggf_clv.values, utils_clv.values)

    def test_fit_with_index(self, cdnow_with_monetary_value):
        returning_cdnow_with_monetary_value = cdnow_with_monetary_value[
            cdnow_with_monetary_value["frequency"] > 0
        ]

        ggf = lt.GammaGammaFitter()
        index = range(len(returning_cdnow_with_monetary_value), 0, -1)
        ggf.fit(
            returning_cdnow_with_monetary_value["frequency"],
            returning_cdnow_with_monetary_value["monetary_value"],
            index=index,
        )
        assert (ggf.data.index == index).all()

        ggf = lt.GammaGammaFitter()
        ggf.fit(
            returning_cdnow_with_monetary_value["frequency"],
            returning_cdnow_with_monetary_value["monetary_value"],
            index=None,
        )
        assert not (ggf.data.index == index).all()

    def test_params_out_is_close_to_Hardie_paper_with_q_constraint(
        self, cdnow_with_monetary_value
    ):

        returning_cdnow_with_monetary_value = cdnow_with_monetary_value[
            cdnow_with_monetary_value["frequency"] > 0
        ]
        ggf = lt.GammaGammaFitter(penalizer_coef=0.0)
        ggf.fit(
            returning_cdnow_with_monetary_value["frequency"],
            returning_cdnow_with_monetary_value["monetary_value"],
            q_constraint=True,
        )
        expected = np.array([6.25, 3.74, 15.44])
        npt.assert_array_almost_equal(
            expected, np.array(ggf._unload_params("p", "q", "v")), decimal=2
        )

    def test_using_weights_col_gives_correct_results(self, cdnow_with_monetary_value):
        cdnow_with_monetary_value = cdnow_with_monetary_value[
            cdnow_with_monetary_value["frequency"] > 0
        ]
        cdnow_weights = cdnow_with_monetary_value.copy()
        cdnow_weights["weights"] = 1.0
        cdnow_weights = cdnow_weights.groupby(["frequency", "monetary_value"])[
            "weights"
        ].sum()
        cdnow_weights = cdnow_weights.reset_index()
        assert (cdnow_weights["weights"] > 1).any()

        gg_weights = lt.GammaGammaFitter(penalizer_coef=0.0)
        gg_weights.fit(
            cdnow_weights["frequency"],
            cdnow_weights["monetary_value"],
            weights=cdnow_weights["weights"],
        )

        gg_no_weights = lt.GammaGammaFitter(penalizer_coef=0.0)
        gg_no_weights.fit(
            cdnow_with_monetary_value["frequency"],
            cdnow_with_monetary_value["monetary_value"],
        )

        npt.assert_almost_equal(
            np.array(gg_no_weights._unload_params("p", "q", "v")),
            np.array(gg_weights._unload_params("p", "q", "v")),
            decimal=3,
        )


class TestParetoNBDFitter:
    def test_overflow_error(self):

        ptf = lt.ParetoNBDFitter()
        params = np.array([10.465, 7.98565181e-03, 3.0516, 2.820])
        freq = np.array([400.0, 500.0, 500.0])
        rec = np.array([5.0, 1.0, 4.0])
        age = np.array([6.0, 37.0, 37.0])
        assert all(
            [
                r < 0 and not np.isinf(r) and not pd.isnull(r)
                for r in ptf._log_A_0(params, freq, rec, age)
            ]
        )

    def test_sum_of_scalar_inputs_to_negative_log_likelihood_is_equal_to_array(self):
        ptf = lt.ParetoNBDFitter
        x = np.array([1, 3])
        t_x = np.array([2, 2])
        weights = np.array([1.0, 1.0])
        t = np.array([5, 6])
        params = [1, 1, 1, 1]
        assert ptf()._negative_log_likelihood(
            params,
            np.array([x[0]]),
            np.array([t_x[0]]),
            np.array([t[0]]),
            weights[0],
            0,
        ) + ptf()._negative_log_likelihood(
            params,
            np.array([x[1]]),
            np.array([t_x[1]]),
            np.array([t[1]]),
            weights[1],
            0,
        ) == ptf()._negative_log_likelihood(
            params, x, t_x, t, weights, 0
        )

    def test_params_out_is_close_to_Hardie_paper(self, cdnow):
        ptf = lt.ParetoNBDFitter()
        ptf.fit(cdnow["frequency"], cdnow["recency"], cdnow["T"], iterative_fitting=3)
        expected = np.array([0.553, 10.578, 0.606, 11.669])
        npt.assert_array_almost_equal(
            expected, np.array(ptf._unload_params("r", "alpha", "s", "beta")), decimal=2
        )

    def test_expectation_returns_same_value_as_R_BTYD(self, cdnow):
        """From https://cran.r-project.org/web/packages/BTYD/BTYD.pdf"""
        ptf = lt.ParetoNBDFitter()
        ptf.fit(cdnow["frequency"], cdnow["recency"], cdnow["T"], tol=1e-6)

        expected = np.array(
            [
                0.00000000,
                0.05077821,
                0.09916088,
                0.14542507,
                0.18979930,
                0.23247466,
                0.27361274,
                0.31335159,
                0.35181024,
                0.38909211,
            ]
        )
        actual = ptf.expected_number_of_purchases_up_to_time(range(10))
        npt.assert_allclose(expected, actual, atol=0.01)

    def test_conditional_expectation_returns_same_value_as_R_BTYD(self, cdnow):
        """From https://cran.r-project.org/web/packages/BTYD/vignettes/BTYD-walkthrough.pdf"""
        ptf = lt.ParetoNBDFitter()
        ptf.fit(cdnow["frequency"], cdnow["recency"], cdnow["T"])
        x = 26.00
        t_x = 30.86
        T = 31
        t = 52
        expected = 25.46
        actual = ptf.conditional_expected_number_of_purchases_up_to_time(t, x, t_x, T)
        assert abs(expected - actual) < 0.01

    def test_conditional_expectation_underflow(self):
        """Test a pair of inputs for the ParetoNBD ptf.conditional_expected_number_of_purchases_up_to_time().
        For a small change in the input, the result shouldn't change dramatically -- however, if the
        function doesn't guard against numeric underflow, this change in input will result in an
        underflow error.
        """
        ptf = lt.ParetoNBDFitter()
        alpha = 10.58
        beta = 11.67
        r = 0.55
        s = 0.61
        ptf.params_ = pd.Series({"alpha": alpha, "beta": beta, "r": r, "s": s})

        # small change in inputs
        left = ptf.conditional_expected_number_of_purchases_up_to_time(
            10, 132, 200, 200
        )  # 6.2060517889632418
        right = ptf.conditional_expected_number_of_purchases_up_to_time(
            10, 133, 200, 200
        )  # 6.2528722475748113
        assert abs(left - right) < 0.05

    def test_conditional_probability_alive_is_between_0_and_1(self, cdnow):
        ptf = lt.ParetoNBDFitter()
        ptf.fit(cdnow["frequency"], cdnow["recency"], cdnow["T"])

        for freq in np.arange(0, 100, 10.0):
            for recency in np.arange(0, 100, 10.0):
                for t in np.arange(recency, 100, 10.0):
                    assert (
                        0.0
                        <= ptf.conditional_probability_alive(freq, recency, t)
                        <= 1.0
                    )

    def test_conditional_probability_alive(self, cdnow):
        """
        Target taken from page 8,
        https://cran.r-project.org/web/packages/BTYD/vignettes/BTYD-walkthrough.pdf
        """
        ptf = lt.ParetoNBDFitter()
        ptf.params_ = pd.Series(
            *([0.5534, 10.5802, 0.6061, 11.6562], ["r", "alpha", "s", "beta"])
        )
        p_alive = ptf.conditional_probability_alive(26.00, 30.86, 31.00)
        assert abs(p_alive - 0.9979) < 0.001

    def test_conditional_probability_alive_overflow_error(self):
        ptf = lt.ParetoNBDFitter()
        ptf.params_ = pd.Series(
            *([10.465, 7.98565181e-03, 3.0516, 2.820], ["r", "alpha", "s", "beta"])
        )
        freq = np.array([40.0, 50.0, 50.0])
        rec = np.array([5.0, 1.0, 4.0])
        age = np.array([6.0, 37.0, 37.0])
        assert all(
            [
                r <= 1 and r >= 0 and not np.isinf(r) and not pd.isnull(r)
                for r in ptf.conditional_probability_alive(freq, rec, age)
            ]
        )

    def test_conditional_probability_alive_matrix(self, cdnow):
        ptf = lt.ParetoNBDFitter()
        ptf.fit(cdnow["frequency"], cdnow["recency"], cdnow["T"])
        Z = ptf.conditional_probability_alive_matrix()
        max_t = int(ptf.data["T"].max())

        for t_x in range(Z.shape[0]):
            for x in range(Z.shape[1]):
                assert Z[t_x][x] == ptf.conditional_probability_alive(x, t_x, max_t)

    def test_fit_with_index(self, cdnow):
        ptf = lt.ParetoNBDFitter()
        index = range(len(cdnow), 0, -1)
        ptf.fit(cdnow["frequency"], cdnow["recency"], cdnow["T"], index=index)
        assert (ptf.data.index == index).all() == True

        ptf = lt.ParetoNBDFitter()
        ptf.fit(cdnow["frequency"], cdnow["recency"], cdnow["T"], index=None)
        assert (ptf.data.index == index).all() == False

    def test_conditional_probability_of_n_purchases_up_to_time_is_between_0_and_1(
        self, cdnow
    ):
        """
        Due to the large parameter space we take a random subset.
        """
        ptf = lt.ParetoNBDFitter()
        ptf.fit(cdnow["frequency"], cdnow["recency"], cdnow["T"])

        for freq in np.random.choice(100, 5):
            for recency in np.random.choice(100, 5):
                for age in recency + np.random.choice(100, 5):
                    for t in np.random.choice(100, 5):
                        for n in np.random.choice(10, 5):
                            assert (
                                0.0
                                <= ptf.conditional_probability_of_n_purchases_up_to_time(
                                    n, t, freq, recency, age
                                )
                                <= 1.0
                            )

    def test_conditional_probability_of_n_purchases_up_to_time_adds_up_to_1(
        self, cdnow
    ):
        """
        Due to the large parameter space we take a random subset. We also restrict our limits to keep the number of
        values of n for which the probability needs to be calculated to a sane level.
        """
        ptf = lt.ParetoNBDFitter()
        ptf.fit(cdnow["frequency"], cdnow["recency"], cdnow["T"])

        for freq in np.random.choice(10, 5):
            for recency in np.random.choice(9, 5):
                for age in np.random.choice(np.arange(recency, 10, 1), 5):
                    for t in 1 + np.random.choice(9, 5):
                        npt.assert_almost_equal(
                            np.sum(
                                [
                                    ptf.conditional_probability_of_n_purchases_up_to_time(
                                        n, t, freq, recency, age
                                    )
                                    for n in np.arange(0, 20, 1)
                                ]
                            ),
                            1.0,
                            decimal=2,
                        )

    def test_fit_with_and_without_weights(self, cdnow):
        original_dataset_with_weights = cdnow.copy()
        original_dataset_with_weights = original_dataset_with_weights.groupby(
            ["frequency", "recency", "T"]
        ).size()
        original_dataset_with_weights = original_dataset_with_weights.reset_index()
        original_dataset_with_weights = original_dataset_with_weights.rename(
            columns={0: "weights"}
        )

        pnbd_noweights = lt.ParetoNBDFitter()
        pnbd_noweights.fit(cdnow["frequency"], cdnow["recency"], cdnow["T"])

        pnbd = lt.ParetoNBDFitter()
        pnbd.fit(
            original_dataset_with_weights["frequency"],
            original_dataset_with_weights["recency"],
            original_dataset_with_weights["T"],
            original_dataset_with_weights["weights"],
        )

        npt.assert_array_almost_equal(
            np.array(pnbd_noweights._unload_params("r", "alpha", "s", "beta")),
            np.array(pnbd._unload_params("r", "alpha", "s", "beta")),
            decimal=2,
        )


class TestBetaGeoFitter:
    def test_sum_of_scalar_inputs_to_negative_log_likelihood_is_equal_to_array(self):
        bgf = lt.BetaGeoFitter
        x = np.array([1, 3])
        t_x = np.array([2, 2])
        t = np.array([5, 6])
        weights = np.array([1, 1])
        params = np.array([1, 1, 1, 1])
        assert (
            bgf._negative_log_likelihood(
                params, x[0], np.array([t_x[0]]), np.array([t[0]]), weights[0], 0
            )
            + bgf._negative_log_likelihood(
                params, x[1], np.array([t_x[1]]), np.array([t[1]]), weights[1], 0
            )
        ) / 2 == bgf._negative_log_likelihood(params, x, t_x, t, weights, 0)

    def test_params_out_is_close_to_Hardie_paper(self, cdnow):
        bfg = lt.BetaGeoFitter()
        bfg.fit(cdnow["frequency"], cdnow["recency"], cdnow["T"])
        expected = np.array([0.243, 4.414, 0.793, 2.426])
        npt.assert_array_almost_equal(
            expected, np.array(bfg._unload_params("r", "alpha", "a", "b")), decimal=2
        )

    def test_conditional_expectation_returns_same_value_as_Hardie_excel_sheet(
        self, cdnow
    ):
        bfg = lt.BetaGeoFitter()
        bfg.fit(cdnow["frequency"], cdnow["recency"], cdnow["T"])
        x = 2
        t_x = 30.43
        T = 38.86
        t = 39
        expected = 1.226
        actual = bfg.conditional_expected_number_of_purchases_up_to_time(t, x, t_x, T)
        assert abs(expected - actual) < 0.001

    def test_expectation_returns_same_value_Hardie_excel_sheet(self, cdnow):
        bfg = lt.BetaGeoFitter()
        bfg.fit(cdnow["frequency"], cdnow["recency"], cdnow["T"], tol=1e-6)

        times = np.array([0.1429, 1.0, 3.00, 31.8571, 32.00, 78.00])
        expected = np.array([0.0078, 0.0532, 0.1506, 1.0405, 1.0437, 1.8576])
        actual = bfg.expected_number_of_purchases_up_to_time(times)
        npt.assert_array_almost_equal(actual, expected, decimal=3)

    def test_conditional_probability_alive_returns_1_if_no_repeat_purchases(
        self, cdnow
    ):
        bfg = lt.BetaGeoFitter()
        bfg.fit(cdnow["frequency"], cdnow["recency"], cdnow["T"])

        assert bfg.conditional_probability_alive(0, 1, 1) == 1.0

    def test_conditional_probability_alive_is_between_0_and_1(self, cdnow):
        bfg = lt.BetaGeoFitter()
        bfg.fit(cdnow["frequency"], cdnow["recency"], cdnow["T"])

        for i in range(0, 100, 10):
            for j in range(0, 100, 10):
                for k in range(j, 100, 10):
                    assert 0 <= bfg.conditional_probability_alive(i, j, k) <= 1.0

    def test_penalizer_term_will_shrink_coefs_to_0(self, cdnow):
        bfg_no_penalizer = lt.BetaGeoFitter()
        bfg_no_penalizer.fit(cdnow["frequency"], cdnow["recency"], cdnow["T"])
        params_1 = bfg_no_penalizer.params_

        bfg_with_penalizer = lt.BetaGeoFitter(penalizer_coef=0.1)
        bfg_with_penalizer.fit(cdnow["frequency"], cdnow["recency"], cdnow["T"])
        params_2 = bfg_with_penalizer.params_
        assert np.all(params_2 < params_1)

        bfg_with_more_penalizer = lt.BetaGeoFitter(penalizer_coef=10)
        bfg_with_more_penalizer.fit(cdnow["frequency"], cdnow["recency"], cdnow["T"])
        params_3 = bfg_with_more_penalizer.params_
        assert np.all(params_3 < params_2)

    def test_conditional_probability_alive_matrix(self, cdnow):
        bfg = lt.BetaGeoFitter()
        bfg.fit(cdnow["frequency"], cdnow["recency"], cdnow["T"])
        Z = bfg.conditional_probability_alive_matrix()
        max_t = int(bfg.data["T"].max())
        assert Z[0][0] == 1

        for t_x in range(Z.shape[0]):
            for x in range(Z.shape[1]):
                assert Z[t_x][x] == bfg.conditional_probability_alive(x, t_x, max_t)

    def test_probability_of_n_purchases_up_to_time_same_as_R_BTYD(self):
        """See https://cran.r-project.org/web/packages/BTYD/BTYD.pdf"""
        bgf = lt.BetaGeoFitter()
        bgf.params_ = pd.Series({"r": 0.243, "alpha": 4.414, "a": 0.793, "b": 2.426})
        # probability that a customer will make 10 repeat transactions in the
        # time interval (0,2]
        expected = 1.07869e-07
        actual = bgf.probability_of_n_purchases_up_to_time(2, 10)
        assert abs(expected - actual) < 10e-5
        # probability that a customer will make no repeat transactions in the
        # time interval (0,39]
        expected = 0.5737864
        actual = bgf.probability_of_n_purchases_up_to_time(39, 0)
        assert abs(expected - actual) < 10e-5
        # PMF
        expected = np.array(
            [
                0.0019995214,
                0.0015170236,
                0.0011633150,
                0.0009003148,
                0.0007023638,
                0.0005517902,
                0.0004361913,
                0.0003467171,
                0.0002769613,
                0.0002222260,
            ]
        )
        actual = np.array(
            [bgf.probability_of_n_purchases_up_to_time(30, n) for n in range(11, 21)]
        )
        npt.assert_array_almost_equal(expected, actual, decimal=5)

    def test_scaling_inputs_gives_same_or_similar_results(self, cdnow):
        bgf = lt.BetaGeoFitter()
        bgf.fit(cdnow["frequency"], cdnow["recency"], cdnow["T"])
        scale = 10
        bgf_with_large_inputs = lt.BetaGeoFitter()
        bgf_with_large_inputs.fit(
            cdnow["frequency"], scale * cdnow["recency"], scale * cdnow["T"]
        )
        assert bgf_with_large_inputs._scale < 1.0

        assert (
            abs(
                bgf_with_large_inputs.conditional_probability_alive(
                    1, scale * 1, scale * 2
                )
                - bgf.conditional_probability_alive(1, 1, 2)
            )
            < 10e-5
        )
        assert (
            abs(
                bgf_with_large_inputs.conditional_probability_alive(
                    1, scale * 2, scale * 10
                )
                - bgf.conditional_probability_alive(1, 2, 10)
            )
            < 10e-5
        )

    def test_save_load(self, cdnow):
        """Test saving and loading model for BG/NBD."""
        bgf = lt.BetaGeoFitter(penalizer_coef=0.0)
        bgf.fit(cdnow["frequency"], cdnow["recency"], cdnow["T"])
        bgf.save_model(PATH_SAVE_BGNBD_MODEL)

        bgf_new = lt.BetaGeoFitter()
        bgf_new.load_model(PATH_SAVE_BGNBD_MODEL)
        assert bgf_new.__dict__["penalizer_coef"] == bgf.__dict__["penalizer_coef"]
        assert bgf_new.__dict__["_scale"] == bgf.__dict__["_scale"]
        assert bgf_new.__dict__["params_"].equals(bgf.__dict__["params_"])
        assert (
            bgf_new.__dict__["_negative_log_likelihood_"]
            == bgf.__dict__["_negative_log_likelihood_"]
        )
        assert (bgf_new.__dict__["data"] == bgf.__dict__["data"]).all().all()
        assert bgf_new.__dict__["predict"](1, 1, 2, 5) == bgf.__dict__["predict"](
            1, 1, 2, 5
        )
        assert bgf_new.expected_number_of_purchases_up_to_time(
            1
        ) == bgf.expected_number_of_purchases_up_to_time(1)
        # remove saved model
        os.remove(PATH_SAVE_BGNBD_MODEL)

    def test_save_load_no_data(self, cdnow):
        """Test saving and loading model for BG/NBD without data."""
        bgf = lt.BetaGeoFitter(penalizer_coef=0.0)
        bgf.fit(cdnow["frequency"], cdnow["recency"], cdnow["T"])
        bgf.save_model(PATH_SAVE_BGNBD_MODEL, save_data=False)

        bgf_new = lt.BetaGeoFitter()
        bgf_new.load_model(PATH_SAVE_BGNBD_MODEL)
        assert bgf_new.__dict__["penalizer_coef"] == bgf.__dict__["penalizer_coef"]
        assert bgf_new.__dict__["_scale"] == bgf.__dict__["_scale"]
        assert bgf_new.__dict__["params_"].equals(bgf.__dict__["params_"])
        assert (
            bgf_new.__dict__["_negative_log_likelihood_"]
            == bgf.__dict__["_negative_log_likelihood_"]
        )
        assert bgf_new.__dict__["predict"](1, 1, 2, 5) == bgf.__dict__["predict"](
            1, 1, 2, 5
        )
        assert bgf_new.expected_number_of_purchases_up_to_time(
            1
        ) == bgf.expected_number_of_purchases_up_to_time(1)

        assert bgf_new.__dict__["data"] is None
        # remove saved model
        os.remove(PATH_SAVE_BGNBD_MODEL)

    def test_save_load_no_data_replace_with_empty_str(self, cdnow):
        """Test saving and loading model for BG/NBD without data with replaced value empty str."""
        bgf = lt.BetaGeoFitter(penalizer_coef=0.0)
        bgf.fit(cdnow["frequency"], cdnow["recency"], cdnow["T"])
        bgf.save_model(PATH_SAVE_BGNBD_MODEL, save_data=False, values_to_save=[""])

        bgf_new = lt.BetaGeoFitter()
        bgf_new.load_model(PATH_SAVE_BGNBD_MODEL)
        assert bgf_new.__dict__["penalizer_coef"] == bgf.__dict__["penalizer_coef"]
        assert bgf_new.__dict__["_scale"] == bgf.__dict__["_scale"]
        assert bgf_new.__dict__["params_"].equals(bgf.__dict__["params_"])
        assert (
            bgf_new.__dict__["_negative_log_likelihood_"]
            == bgf.__dict__["_negative_log_likelihood_"]
        )
        assert bgf_new.__dict__["predict"](1, 1, 2, 5) == bgf.__dict__["predict"](
            1, 1, 2, 5
        )
        assert bgf_new.expected_number_of_purchases_up_to_time(
            1
        ) == bgf.expected_number_of_purchases_up_to_time(1)

        assert bgf_new.__dict__["data"] is ""
        # remove saved model
        os.remove(PATH_SAVE_BGNBD_MODEL)

    def test_fit_with_index(self, cdnow):
        bgf = lt.BetaGeoFitter(penalizer_coef=0.0)
        index = range(len(cdnow), 0, -1)
        bgf.fit(cdnow["frequency"], cdnow["recency"], cdnow["T"], index=index)
        assert (bgf.data.index == index).all() == True

        bgf = lt.BetaGeoFitter(penalizer_coef=0.0)
        bgf.fit(cdnow["frequency"], cdnow["recency"], cdnow["T"], index=None)
        assert (bgf.data.index == index).all() == False

    def test_no_runtime_warnings_high_frequency(self, cdnow):
        old_settings = np.seterr(all="raise")
        bgf = lt.BetaGeoFitter(penalizer_coef=0.0)
        bgf.fit(cdnow["frequency"], cdnow["recency"], cdnow["T"], index=None)

        p_alive = bgf.conditional_probability_alive(frequency=1000, recency=10, T=100)
        np.seterr(**old_settings)
        assert p_alive == 0.0

    def test_using_weights_col_gives_correct_results(self, cdnow):
        cdnow_weights = cdnow.copy()
        cdnow_weights["weights"] = 1.0
        cdnow_weights = cdnow_weights.groupby(["frequency", "recency", "T"])[
            "weights"
        ].sum()
        cdnow_weights = cdnow_weights.reset_index()
        assert (cdnow_weights["weights"] > 1).any()

        bgf_weights = lt.BetaGeoFitter(penalizer_coef=0.0)
        bgf_weights.fit(
            cdnow_weights["frequency"],
            cdnow_weights["recency"],
            cdnow_weights["T"],
            weights=cdnow_weights["weights"],
        )

        bgf_no_weights = lt.BetaGeoFitter(penalizer_coef=0.0)
        bgf_no_weights.fit(cdnow["frequency"], cdnow["recency"], cdnow["T"])

        npt.assert_almost_equal(
            np.array(bgf_no_weights._unload_params("r", "alpha", "a", "b")),
            np.array(bgf_weights._unload_params("r", "alpha", "a", "b")),
            decimal=3,
        )


class TestModifiedBetaGammaFitter:
    def test_sum_of_scalar_inputs_to_negative_log_likelihood_is_equal_to_array(self):
        mbgf = lt.ModifiedBetaGeoFitter
        x = np.array([1, 3])
        t_x = np.array([2, 2])
        t = np.array([5, 6])
        weights = np.array([1, 1])
        params = [1, 1, 1, 1]
        assert (
            mbgf._negative_log_likelihood(
                params,
                np.array([x[0]]),
                np.array([t_x[0]]),
                np.array([t[0]]),
                weights[0],
                0,
            )
            + mbgf._negative_log_likelihood(
                params,
                np.array([x[1]]),
                np.array([t_x[1]]),
                np.array([t[1]]),
                weights[1],
                0,
            )
        ) / 2 == mbgf._negative_log_likelihood(params, x, t_x, t, weights, 0)

    def test_params_out_is_close_to_BTYDplus(self, cdnow):
        """See https://github.com/mplatzer/BTYDplus"""
        mbfg = lt.ModifiedBetaGeoFitter()
        mbfg.fit(cdnow["frequency"], cdnow["recency"], cdnow["T"])
        expected = np.array([0.525, 6.183, 0.891, 1.614])
        npt.assert_array_almost_equal(
            expected, np.array(mbfg._unload_params("r", "alpha", "a", "b")), decimal=3
        )

    def test_conditional_expectation_returns_same_value_as_Hardie_excel_sheet(
        self, cdnow
    ):
        mbfg = lt.ModifiedBetaGeoFitter()
        mbfg.fit(cdnow["frequency"], cdnow["recency"], cdnow["T"])
        x = 2
        t_x = 30.43
        T = 38.86
        t = 39
        expected = 1.226
        actual = mbfg.conditional_expected_number_of_purchases_up_to_time(t, x, t_x, T)
        assert abs(expected - actual) < 0.05

    def test_expectation_returns_same_value_Hardie_excel_sheet(self, cdnow):
        mbfg = lt.ModifiedBetaGeoFitter()
        mbfg.fit(cdnow["frequency"], cdnow["recency"], cdnow["T"], tol=1e-6)

        times = np.array([0.1429, 1.0, 3.00, 31.8571, 32.00, 78.00])
        expected = np.array([0.0078, 0.0532, 0.1506, 1.0405, 1.0437, 1.8576])
        actual = mbfg.expected_number_of_purchases_up_to_time(times)
        npt.assert_allclose(actual, expected, rtol=0.05)

    def test_conditional_probability_alive_returns_lessthan_1_if_no_repeat_purchases(
        self, cdnow
    ):
        mbfg = lt.ModifiedBetaGeoFitter()
        mbfg.fit(cdnow["frequency"], cdnow["recency"], cdnow["T"])

        assert mbfg.conditional_probability_alive(0, 1, 1) < 1.0

    def test_conditional_probability_alive_is_between_0_and_1(self, cdnow):
        mbfg = lt.ModifiedBetaGeoFitter()
        mbfg.fit(cdnow["frequency"], cdnow["recency"], cdnow["T"])

        for i in range(0, 100, 10):
            for j in range(0, 100, 10):
                for k in range(j, 100, 10):
                    assert 0 <= mbfg.conditional_probability_alive(i, j, k) <= 1.0

    def test_penalizer_term_will_shrink_coefs_to_0(self, cdnow):
        mbfg_no_penalizer = lt.ModifiedBetaGeoFitter()
        mbfg_no_penalizer.fit(cdnow["frequency"], cdnow["recency"], cdnow["T"])
        params_1 = mbfg_no_penalizer.params_

        mbfg_with_penalizer = lt.ModifiedBetaGeoFitter(penalizer_coef=0.1)
        mbfg_with_penalizer.fit(cdnow["frequency"], cdnow["recency"], cdnow["T"])
        params_2 = mbfg_with_penalizer.params_
        assert params_2.sum() < params_1.sum()

        mbfg_with_more_penalizer = lt.ModifiedBetaGeoFitter(penalizer_coef=1.0)
        mbfg_with_more_penalizer.fit(cdnow["frequency"], cdnow["recency"], cdnow["T"])
        params_3 = mbfg_with_more_penalizer.params_
        assert params_3.sum() < params_2.sum()

    def test_conditional_probability_alive_matrix(self, cdnow):
        mbfg = lt.ModifiedBetaGeoFitter()
        mbfg.fit(cdnow["frequency"], cdnow["recency"], cdnow["T"])
        Z = mbfg.conditional_probability_alive_matrix()
        max_t = int(mbfg.data["T"].max())

        for t_x in range(Z.shape[0]):
            for x in range(Z.shape[1]):
                assert Z[t_x][x] == mbfg.conditional_probability_alive(x, t_x, max_t)

    def test_probability_of_n_purchases_up_to_time_same_as_R_BTYD(self):
        """See https://cran.r-project.org/web/packages/BTYD/BTYD.pdf"""
        mbgf = lt.ModifiedBetaGeoFitter()
        mbgf.params_ = pd.Series({"r": 0.243, "alpha": 4.414, "a": 0.793, "b": 2.426})
        # probability that a customer will make 10 repeat transactions in the
        # time interval (0,2]
        expected = 1.07869e-07
        actual = mbgf.probability_of_n_purchases_up_to_time(2, 10)
        assert abs(expected - actual) < 10e-5
        # PMF
        expected = np.array(
            [
                0.0019995214,
                0.0015170236,
                0.0011633150,
                0.0009003148,
                0.0007023638,
                0.0005517902,
                0.0004361913,
                0.0003467171,
                0.0002769613,
                0.0002222260,
            ]
        )
        actual = np.array(
            [mbgf.probability_of_n_purchases_up_to_time(30, n) for n in range(11, 21)]
        )
        npt.assert_allclose(expected, actual, rtol=0.5)

    def test_scaling_inputs_gives_same_or_similar_results(self, cdnow):
        mbgf = lt.ModifiedBetaGeoFitter()
        mbgf.fit(cdnow["frequency"], cdnow["recency"], cdnow["T"])
        scale = 10.0
        mbgf_with_large_inputs = lt.ModifiedBetaGeoFitter()
        mbgf_with_large_inputs.fit(
            cdnow["frequency"], scale * cdnow["recency"], scale * cdnow["T"]
        )
        assert mbgf_with_large_inputs._scale < 1.0

        assert (
            abs(
                mbgf_with_large_inputs.conditional_probability_alive(
                    1, scale * 1, scale * 2
                )
                - mbgf.conditional_probability_alive(1, 1, 2)
            )
            < 10e-2
        )
        assert (
            abs(
                mbgf_with_large_inputs.conditional_probability_alive(
                    1, scale * 2, scale * 10
                )
                - mbgf.conditional_probability_alive(1, 2, 10)
            )
            < 10e-2
        )

    def test_purchase_predictions_do_not_differ_much_if_looking_at_hourly_or_daily_frequencies(
        self,
    ):
        transaction_data = load_transaction_data(parse_dates=["date"])
        daily_summary = utils.summary_data_from_transaction_data(
            transaction_data,
            "id",
            "date",
            observation_period_end=max(transaction_data.date),
            freq="D",
        )
        hourly_summary = utils.summary_data_from_transaction_data(
            transaction_data,
            "id",
            "date",
            observation_period_end=max(transaction_data.date),
            freq="h",
        )
        thirty_days = 30
        hours_in_day = 24
        mbfg = lt.ModifiedBetaGeoFitter()

        np.random.seed(0)
        mbfg.fit(
            daily_summary["frequency"], daily_summary["recency"], daily_summary["T"]
        )
        thirty_day_prediction_from_daily_data = (
            mbfg.expected_number_of_purchases_up_to_time(thirty_days)
        )

        np.random.seed(0)
        mbfg.fit(
            hourly_summary["frequency"], hourly_summary["recency"], hourly_summary["T"]
        )
        thirty_day_prediction_from_hourly_data = (
            mbfg.expected_number_of_purchases_up_to_time(thirty_days * hours_in_day)
        )

        npt.assert_almost_equal(
            thirty_day_prediction_from_daily_data,
            thirty_day_prediction_from_hourly_data,
        )

    def test_fit_with_index(self, cdnow):
        mbgf = lt.ModifiedBetaGeoFitter()
        index = range(len(cdnow), 0, -1)
        mbgf.fit(cdnow["frequency"], cdnow["recency"], cdnow["T"], index=index)
        assert (mbgf.data.index == index).all() == True

        mbgf = lt.ModifiedBetaGeoFitter()
        mbgf.fit(cdnow["frequency"], cdnow["recency"], cdnow["T"], index=None)
        assert (mbgf.data.index == index).all() == False


class TestBetaGeoCovarsFitter:
    def test_sum_of_scalar_inputs_to_negative_log_likelihood_is_equal_to_array(self):
        bgcf = lt.BetaGeoCovarsFitter()
        x = np.array([1, 3])
        t_x = np.array([2, 2])
        t = np.array([5, 6])
        tr = np.array([[2, 2]])
        do = np.array([[2, 2]])
        weights = np.array([1, 1])
        params = np.array([1, 1, 1, 1, 1, 1, 1, 1, 1, 1])
        sc1 = bgcf._negative_log_likelihood(
            params,
            x[0],
            np.array([t_x[0]]),
            np.array([t[0]]),
            np.array([tr[0]]),
            np.array([do[0]]),
            weights[0],
            0,
        )
        sc2 = bgcf._negative_log_likelihood(
            params,
            x[1],
            np.array([t_x[1]]),
            np.array([t[1]]),
            np.array([tr[0]]),
            np.array([do[0]]),
            weights[1],
            0,
        )
        ar = bgcf._negative_log_likelihood(params, x, t_x, t, tr, do, weights, 0)
        assert (sc1 + sc2) / 2 == ar

    def test_conditional_expectation_returns_same_value_as_Hardie_excel_sheet(
        self, cdnow
    ):
        bgcf = lt.BetaGeoCovarsFitter()
        X_tr = np.ones((cdnow.shape[0], 5))
        X_do = np.ones((cdnow.shape[0], 5))
        bgcf.fit(cdnow["frequency"], cdnow["recency"], cdnow["T"], X_tr, X_do)
        x = 2
        t_x = 30.43
        T = 38.86
        t = 39
        expected = 1.226
        actual = bgcf.conditional_expected_number_of_purchases_up_to_time(
            t, x, t_x, T, X_tr[0], X_do[0]
        )
        assert abs(expected - actual) < 0.001

    def test_expectation_returns_same_value_Hardie_excel_sheet(self, cdnow):
        bgcf = lt.BetaGeoCovarsFitter()
        X_tr = np.ones((cdnow.shape[0], 2))
        X_do = np.ones((cdnow.shape[0], 1))
        bgcf.fit(cdnow["frequency"], cdnow["recency"], cdnow["T"], X_tr, X_do, tol=1e-6)

        times = np.array([0.1429, 1.0, 3.00, 31.8571, 32.00, 78.00])
        expected = np.array([0.0078, 0.0532, 0.1506, 1.0405, 1.0437, 1.8576])
        actual = bgcf.expected_number_of_purchases_up_to_time(
            times, np.ones((1, 2)), np.ones((1, 1))
        )
        npt.assert_array_almost_equal(actual, expected, decimal=3)

    def test_conditional_probability_alive_returns_1_if_no_repeat_purchases(
        self, cdnow
    ):
        bgcf = lt.BetaGeoCovarsFitter()
        X_tr = np.ones((cdnow.shape[0], 2))
        X_do = np.ones((cdnow.shape[0], 2))
        bgcf.fit(cdnow["frequency"], cdnow["recency"], cdnow["T"], X_tr, X_do)

        assert bgcf.conditional_probability_alive(0, 1, 1, [1, 1], [1, 1]) == 1.0

    def test_conditional_probability_alive_is_between_0_and_1(self, cdnow):
        bgcf = lt.BetaGeoCovarsFitter()
        X_tr = np.ones((cdnow.shape[0], 1))
        X_do = np.ones((cdnow.shape[0], 1))
        bgcf.fit(cdnow["frequency"], cdnow["recency"], cdnow["T"], X_tr, X_do)

        for i in range(0, 100, 10):
            for j in range(0, 100, 10):
                for k in range(j, 100, 10):
                    assert (
                        0
                        <= bgcf.conditional_probability_alive(i, j, k, X_tr[0], X_do[0])
                        <= 1.0
                    )

    def test_penalizer_term_will_shrink_coefs_to_0(self, cdnow):
        frequency = cdnow["frequency"]
        recency = cdnow["recency"]
        T = cdnow["T"]
        X_tr = np.ones((cdnow.shape[0], 2))
        X_do = np.ones((cdnow.shape[0], 3))
        bfcg_no_penalizer = lt.BetaGeoCovarsFitter()
        bfcg_no_penalizer.fit(frequency, recency, T, X_tr, X_do)
        params_1 = bfcg_no_penalizer.params_

        bfcg_with_penalizer = lt.BetaGeoCovarsFitter(penalizer_coef=0.1)
        bfcg_with_penalizer.fit(frequency, recency, T, X_tr, X_do)
        params_2 = bfcg_with_penalizer.params_
        assert np.all(params_2 < params_1)

        bfcg_with_more_penalizer = lt.BetaGeoCovarsFitter(penalizer_coef=10)
        bfcg_with_more_penalizer.fit(frequency, recency, T, X_tr, X_do)
        params_3 = bfcg_with_more_penalizer.params_
        assert np.all(params_3 < params_2)

    def test_conditional_probability_alive_matrix(self, cdnow):
        bfcg = lt.BetaGeoCovarsFitter()
        X_tr = np.ones((cdnow.shape[0], 1))
        X_do = np.ones((cdnow.shape[0], 1))
        bfcg.fit(cdnow["frequency"], cdnow["recency"], cdnow["T"], X_tr, X_do)
        Z = bfcg.conditional_probability_alive_matrix(X_tr, X_do)
        max_t = int(bfcg.data["T"].max())
        assert Z[0][0] == 1

        for t_x in range(Z.shape[0]):
            for x in range(Z.shape[1]):
                assert Z[t_x][x] == bfcg.conditional_probability_alive(
                    x, t_x, max_t, 1, 1
                )

    def test_scaling_inputs_gives_same_or_similar_results(self, cdnow):
        bgcf = lt.BetaGeoCovarsFitter()
        X_tr = np.ones((cdnow.shape[0], 2))
        X_do = np.ones((cdnow.shape[0], 2))
        bgcf.fit(cdnow["frequency"], cdnow["recency"], cdnow["T"], X_tr, X_do)
        scale = 10
        bgcf_with_large_inputs = lt.BetaGeoCovarsFitter()
        bgcf_with_large_inputs.fit(
            cdnow["frequency"], scale * cdnow["recency"], scale * cdnow["T"], X_tr, X_do
        )
        assert bgcf_with_large_inputs._scale < 1.0

        assert (
            abs(
                bgcf_with_large_inputs.conditional_probability_alive(
                    1, scale * 1, scale * 2, X_tr[0], X_do[0]
                )
                - bgcf.conditional_probability_alive(1, 1, 2, X_tr[0], X_do[0])
            )
            < 10e-5
        )
        assert (
            abs(
                bgcf_with_large_inputs.conditional_probability_alive(
                    1, scale * 2, scale * 10, X_tr[0], X_do[0]
                )
                - bgcf.conditional_probability_alive(1, 2, 10, X_tr[0], X_do[0])
            )
            < 10e-5
        )

    def test_save_load(self, cdnow):
        """Test saving and loading model for BG/NBD."""
        bgcf = lt.BetaGeoCovarsFitter(penalizer_coef=0.0)
        X_tr = np.ones((cdnow.shape[0], 1))
        X_do = np.ones((cdnow.shape[0], 1))
        bgcf.fit(cdnow["frequency"], cdnow["recency"], cdnow["T"], X_tr, X_do)
        bgcf.save_model(PATH_SAVE_BGNBD_MODEL)

        bgcf_new = lt.BetaGeoCovarsFitter()
        bgcf_new.load_model(PATH_SAVE_BGNBD_MODEL)
        assert bgcf_new.__dict__["penalizer_coef"] == bgcf.__dict__["penalizer_coef"]
        assert bgcf_new.__dict__["_scale"] == bgcf.__dict__["_scale"]
        assert bgcf_new.__dict__["params_"].equals(bgcf.__dict__["params_"])
        assert (
            bgcf_new.__dict__["_negative_log_likelihood_"]
            == bgcf.__dict__["_negative_log_likelihood_"]
        )
        assert (bgcf_new.__dict__["data"] == bgcf.__dict__["data"]).all().all()
        assert bgcf_new.__dict__["predict"](1, 1, 2, 5, 1, 1) == bgcf.__dict__[
            "predict"
        ](1, 1, 2, 5, 1, 1)
        assert bgcf_new.expected_number_of_purchases_up_to_time(
            1, 1, 1
        ) == bgcf.expected_number_of_purchases_up_to_time(1, 1, 1)
        # remove saved model
        os.remove(PATH_SAVE_BGNBD_MODEL)

    def test_save_load_no_data(self, cdnow):
        """Test saving and loading model for BG/NBD without data."""
        bgcf = lt.BetaGeoCovarsFitter(penalizer_coef=0.0)
        X_tr = np.ones((cdnow.shape[0], 1))
        X_do = np.ones((cdnow.shape[0], 1))
        bgcf.fit(cdnow["frequency"], cdnow["recency"], cdnow["T"], X_tr, X_do)
        bgcf.save_model(PATH_SAVE_BGNBD_MODEL, save_data=False)

        bgcf_new = lt.BetaGeoCovarsFitter()
        bgcf_new.load_model(PATH_SAVE_BGNBD_MODEL)
        assert bgcf_new.__dict__["penalizer_coef"] == bgcf.__dict__["penalizer_coef"]
        assert bgcf_new.__dict__["_scale"] == bgcf.__dict__["_scale"]
        assert bgcf_new.__dict__["params_"].equals(bgcf.__dict__["params_"])
        assert (
            bgcf_new.__dict__["_negative_log_likelihood_"]
            == bgcf.__dict__["_negative_log_likelihood_"]
        )
        assert bgcf_new.__dict__["predict"](1, 1, 2, 5, 1, 1) == bgcf.__dict__[
            "predict"
        ](1, 1, 2, 5, 1, 1)
        assert bgcf_new.expected_number_of_purchases_up_to_time(
            1, 1, 1
        ) == bgcf.expected_number_of_purchases_up_to_time(1, 1, 1)
        assert bgcf_new.__dict__["data"] is None
        # remove saved model
        os.remove(PATH_SAVE_BGNBD_MODEL)

    def test_save_load_no_data_replace_with_empty_str(self, cdnow):
        """Test saving and loading model for BG/NBD without data with replaced value empty str."""
        bgcf = lt.BetaGeoCovarsFitter(penalizer_coef=0.0)
        X_tr = np.ones((cdnow.shape[0], 1))
        X_do = np.ones((cdnow.shape[0], 1))
        bgcf.fit(cdnow["frequency"], cdnow["recency"], cdnow["T"], X_tr, X_do)
        bgcf.save_model(PATH_SAVE_BGNBD_MODEL, save_data=False, values_to_save=[""])

        bgcf_new = lt.BetaGeoCovarsFitter()
        bgcf_new.load_model(PATH_SAVE_BGNBD_MODEL)
        assert bgcf_new.__dict__["penalizer_coef"] == bgcf.__dict__["penalizer_coef"]
        assert bgcf_new.__dict__["_scale"] == bgcf.__dict__["_scale"]
        assert bgcf_new.__dict__["params_"].equals(bgcf.__dict__["params_"])
        assert (
            bgcf_new.__dict__["_negative_log_likelihood_"]
            == bgcf.__dict__["_negative_log_likelihood_"]
        )
        assert bgcf_new.__dict__["predict"](1, 1, 2, 5, 1, 1) == bgcf.__dict__[
            "predict"
        ](1, 1, 2, 5, 1, 1)
        assert bgcf_new.expected_number_of_purchases_up_to_time(
            1, 1, 1
        ) == bgcf.expected_number_of_purchases_up_to_time(1, 1, 1)
        assert bgcf_new.__dict__["data"] is ""
        # remove saved model
        os.remove(PATH_SAVE_BGNBD_MODEL)

    def test_fit_with_index(self, cdnow):
        X_tr = np.ones((cdnow.shape[0], 1))
        X_do = np.ones((cdnow.shape[0], 1))
        bgcf = lt.BetaGeoCovarsFitter(penalizer_coef=0.0)
        index = range(len(cdnow), 0, -1)
        bgcf.fit(
            cdnow["frequency"], cdnow["recency"], cdnow["T"], X_tr, X_do, index=index
        )
        assert (bgcf.data.index == index).all() == True

        bgcf = lt.BetaGeoCovarsFitter(penalizer_coef=0.0)
        bgcf.fit(
            cdnow["frequency"], cdnow["recency"], cdnow["T"], X_tr, X_do, index=None
        )
        assert (bgcf.data.index == index).all() == False

    def test_no_runtime_warnings_high_frequency(self, cdnow):
        X_tr = np.ones((cdnow.shape[0], 1))
        X_do = np.ones((cdnow.shape[0], 1))
        old_settings = np.seterr(all="raise")
        bgcf = lt.BetaGeoCovarsFitter(penalizer_coef=0.0)
        bgcf.fit(cdnow["frequency"], cdnow["recency"], cdnow["T"], X_tr, X_do)

        p_alive = bgcf.conditional_probability_alive(
            frequency=1000, recency=10, T=100, X_tr=1, X_do=1
        )
        np.seterr(**old_settings)
        assert p_alive == 0.0

    def test_using_weights_col_gives_correct_results(self, cdnow):
        cdnow_weights = cdnow.copy()
        cdnow_weights["weights"] = 1.0
        cdnow_weights["X_tr"] = 1.0
        cdnow_weights["X_do"] = 2.0
        cdnow_weights = cdnow_weights.groupby(
            ["frequency", "recency", "T", "X_tr", "X_do"]
        ).sum()
        cdnow_weights = cdnow_weights.reset_index()
        assert (cdnow_weights["weights"] > 1).any()

        bgcf_weights = lt.BetaGeoCovarsFitter(penalizer_coef=0.0)
        bgcf_weights.fit(
            cdnow_weights["frequency"],
            cdnow_weights["recency"],
            cdnow_weights["T"],
            np.array(cdnow_weights["X_tr"]).reshape((-1, 1)),
            np.array(cdnow_weights["X_do"]).reshape((-1, 1)),
            cdnow_weights["weights"],
        )

        bgcf_no_weights = lt.BetaGeoCovarsFitter(penalizer_coef=0.0)
        bgcf_no_weights.fit(
            cdnow["frequency"],
            cdnow["recency"],
            cdnow["T"],
            np.ones((cdnow.shape[0], 1)),
            np.ones((cdnow.shape[0], 1)) * 2.0,
        )

        npt.assert_almost_equal(
            np.array(bgcf_no_weights._unload_params("r", "alpha0", "a0", "b0")),
            np.array(bgcf_weights._unload_params("r", "alpha0", "a0", "b0")),
            decimal=3,
        )
