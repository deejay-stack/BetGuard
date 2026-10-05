import pandas as pd
from pathlib import Path


RAW_FILE = Path("data/raw/dataset_with_ssl_dns.csv")
OUTPUT_FILE = Path("data/processed/dataset_cleaned.csv")


df = pd.read_csv(RAW_FILE)


# ---------------------------------------------------------
# 1. Confirmed corrections
# ---------------------------------------------------------

confirmed_gambling = [
    "bet88.com",
    "casino.jackpocket.com",
    "slotmojo.com",
    "sailorbingo.com",
]


df.loc[
    df["domain"].str.lower().isin(confirmed_gambling),
    "label"
] = 1


# ---------------------------------------------------------
# 2. Basic cleaning
# ---------------------------------------------------------

df["domain"] = (
    df["domain"]
    .astype(str)
    .str.strip()
    .str.lower()
)


# ---------------------------------------------------------
# 3. Remove exact duplicate domains
# ---------------------------------------------------------

df = df.drop_duplicates(
    subset=["domain"],
    keep="first"
)


# ---------------------------------------------------------
# 4. Basic report
# ---------------------------------------------------------

print("\nDataset size:")
print(len(df))

print("\nLabel distribution:")
print(df["label"].value_counts())

print("\nMissing values:")
print(df.isnull().sum())

print("\nConfirmed corrected domains:")

print(
    df[
        df["domain"].isin(confirmed_gambling)
    ][["domain", "label"]]
)


# ---------------------------------------------------------
# 5. Save CLEAN COPY
# ---------------------------------------------------------

OUTPUT_FILE.parent.mkdir(
    parents=True,
    exist_ok=True
)

df.to_csv(
    OUTPUT_FILE,
    index=False
)

print(
    f"\nClean dataset saved to: {OUTPUT_FILE}"
)
suspicious = df[
    (df["has_gambling_keyword"] == 1)
    &
    (df["label"] == 0)
]

print("\nPossible mislabeled domains:")
print(
    suspicious[
        [
            "domain",
            "has_gambling_keyword",
            "label"
        ]
    ].to_string(index=False)
)