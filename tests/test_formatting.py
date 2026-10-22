import pandas as pd

from ui import formatting as f


def test_number_formats():
    assert f.num(75000) == "75\u202f000"
    assert f.num(1234567.5, 1) == "1\u202f234\u202f567,5"
    assert f.fcfa(75000) == "75\u202f000\u00a0FCFA"
    assert f.kg(212.4) == "212\u00a0FCFA/kg"


def test_percent_formats():
    assert f.pct(12.34) == "+12,3\u00a0%"
    assert f.pct(-3.2) == "−3,2\u00a0%"
    assert f.pct(5, signed=False) == "5,0\u00a0%"


def test_delta_uses_ascii_minus_so_streamlit_colours_it_correctly():
    assert f.pct_delta(-3.2).startswith("-") and f.pct_delta(3.2).startswith("+")


def test_month_labels():
    assert f.month_label(pd.Timestamp("2026-10-01")) == "oct. 26"
    assert f.month_label_long(pd.Timestamp("2027-01-01")) == "janv. 2027"
