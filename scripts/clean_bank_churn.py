"""
clean_bank_churn.py
-------------------
Cleans the messy North Bank churn workbook (Bank_Churn_Messy.xlsx) and
produces an analysis-ready CSV for Looker Studio.

Usage:
    python scripts/clean_bank_churn.py
    python scripts/clean_bank_churn.py --input data/raw/Bank_Churn_Messy.xlsx \
                                       --output data/processed/Bank_Churn_Clean.csv
"""
import argparse
from pathlib import Path

import numpy as np
import pandas as pd

GEO_MAP = {  # every spelling found in the raw data -> canonical name
    "france": "France", "french": "France", "fra": "France",
    "germany": "Germany", "spain": "Spain",
}
SALARY_PLACEHOLDER = -999_999  # sentinel used for "unknown" salary
AGE_BINS = [17, 30, 40, 50, 60, np.inf]
AGE_LABELS = ["18-30", "31-40", "41-50", "51-60", "61+"]


def money_to_float(series: pd.Series) -> pd.Series:
    """'€101348.88' -> 101348.88  |  '-€999999' -> -999999.0"""
    return pd.to_numeric(
        series.astype(str).str.replace(r"[€$,\s]", "", regex=True), errors="coerce"
    )


def clean(input_path: Path) -> pd.DataFrame:
    customers = pd.read_excel(input_path, sheet_name="Customer_Info")
    accounts = pd.read_excel(input_path, sheet_name="Account_Info")

    # Drop empty trailing columns that Excel adds
    customers = customers.loc[:, ~customers.columns.astype(str).str.startswith("Unnamed")]
    accounts = accounts.loc[:, ~accounts.columns.astype(str).str.startswith("Unnamed")]
    print(f"[load]   Customer_Info {customers.shape} | Account_Info {accounts.shape}")

    # 1. Remove duplicates
    n_c, n_a = len(customers), len(accounts)
    customers = customers.drop_duplicates(subset="CustomerId", keep="first")
    accounts = accounts.drop_duplicates(subset="CustomerId", keep="first")
    print(f"[dedupe] removed {n_c - len(customers)} customer and {n_a - len(accounts)} account duplicates")

    # 2. Standardise text columns
    customers["Geography"] = (
        customers["Geography"].astype(str).str.strip().str.lower().map(GEO_MAP)
    )
    customers["Gender"] = customers["Gender"].astype(str).str.strip().str.title()
    customers["Surname"] = customers["Surname"].astype("string").str.strip()

    # 3. Money columns: strip currency symbol -> numeric
    customers["EstimatedSalary"] = money_to_float(customers["EstimatedSalary"])
    accounts["Balance"] = money_to_float(accounts["Balance"])

    # 4. Placeholders / missing values
    bad_salary = customers["EstimatedSalary"] == SALARY_PLACEHOLDER
    customers.loc[bad_salary, "EstimatedSalary"] = np.nan
    customers["HadMissingData"] = (
        bad_salary | customers["Age"].isna() | customers["Surname"].isna()
    )
    customers["Surname"] = customers["Surname"].fillna("Unknown")
    customers["Age"] = customers["Age"].fillna(customers["Age"].median())
    customers["EstimatedSalary"] = customers["EstimatedSalary"].fillna(
        customers["EstimatedSalary"].median()
    )
    print(f"[impute] repaired {int(customers['HadMissingData'].sum())} rows "
          "(Age/Salary -> median, Surname -> 'Unknown')")

    # 5. Yes/No -> 1/0
    yn = {"yes": 1, "no": 0, "y": 1, "n": 0, "1": 1, "0": 0}
    for col in ["HasCrCard", "IsActiveMember"]:
        accounts[col] = accounts[col].astype(str).str.strip().str.lower().map(yn)

    # 6. Merge the two sheets (Tenure exists in both -> keep one)
    df = customers.merge(
        accounts.drop(columns=["Tenure"]), on="CustomerId", how="inner", validate="1:1"
    )

    # 7. Types
    df["Age"] = df["Age"].round().astype(int)
    for col in ["CreditScore", "Tenure", "NumOfProducts", "HasCrCard",
                "IsActiveMember", "Exited"]:
        df[col] = df[col].astype(int)

    # 8. Feature engineering
    df["AgeGroup"] = pd.cut(df["Age"], bins=AGE_BINS, labels=AGE_LABELS).astype(str)

    # 9. Final column order
    cols = ["CustomerId", "Surname", "CreditScore", "Geography", "Gender", "Age",
            "AgeGroup", "Tenure", "Balance", "NumOfProducts", "HasCrCard",
            "IsActiveMember", "EstimatedSalary", "Exited", "HadMissingData"]
    df = df[cols].sort_values("CustomerId").reset_index(drop=True)

    # 10. Sanity checks
    assert df["CustomerId"].is_unique, "duplicate CustomerId after cleaning"
    assert df["Geography"].isin(["France", "Germany", "Spain"]).all(), "unmapped Geography"
    assert df.drop(columns=["HadMissingData"]).notna().all().all(), "nulls remain"
    print(f"[done]   {len(df):,} rows x {df.shape[1]} columns")
    return df


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input", default="data/raw/Bank_Churn_Messy.xlsx")
    p.add_argument("--output", default="data/processed/Bank_Churn_Clean.csv")
    args = p.parse_args()

    df = clean(Path(args.input))
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(args.output, index=False)
    print(f"[saved]  {args.output}")


if __name__ == "__main__":
    main()
