from collections import Counter

import numpy as np

from sklearn.base import (
    BaseEstimator,
    TransformerMixin,
)


# =========================================================
# BETGUARD
# DOMAIN LEXICAL FEATURE TRANSFORMER
# =========================================================
#
# These features are calculated ONLY from the domain
# string.
#
# No:
#
#   gambling keyword list
#   SSL
#   DNS
#   WHOIS
#   domain age
#
# This makes the features reproducible for every domain.
#
# =========================================================


FEATURE_NAMES = [
    "domain_length",
    "digit_count",
    "letter_count",
    "hyphen_count",
    "dot_count",
    "special_char_count",
    "label_count",
    "max_label_length",
    "tld_length",
    "digit_ratio",
    "hyphen_ratio",
    "unique_char_ratio",
    "entropy",
    "longest_digit_run",
]


# =========================================================
# NORMALIZE DOMAIN
# =========================================================

def normalize_domain(domain):

    if domain is None:
        return ""

    domain = str(
        domain
    ).strip().lower()

    if domain.startswith(
        "https://"
    ):

        domain = domain[
            len("https://"):
        ]

    elif domain.startswith(
        "http://"
    ):

        domain = domain[
            len("http://"):
        ]

    domain = domain.split(
        "/"
    )[0]

    domain = domain.split(
        "?"
    )[0]

    domain = domain.split(
        "#"
    )[0]

    if domain.startswith(
        "www."
    ):

        domain = domain[4:]

    domain = domain.rstrip(
        "."
    )

    if domain.count(":") == 1:

        hostname, possible_port = (
            domain.rsplit(
                ":",
                1
            )
        )

        if possible_port.isdigit():

            domain = hostname

    return domain


# =========================================================
# SHANNON ENTROPY
# =========================================================

def calculate_entropy(text):

    if not text:
        return 0.0

    counts = Counter(
        text
    )

    length = len(
        text
    )

    entropy = 0.0

    for count in counts.values():

        probability = (
            count
            /
            length
        )

        entropy -= (
            probability
            *
            np.log2(
                probability
            )
        )

    return float(
        entropy
    )


# =========================================================
# LONGEST DIGIT RUN
# =========================================================

def longest_digit_run(text):

    longest = 0
    current = 0

    for character in text:

        if character.isdigit():

            current += 1

            longest = max(
                longest,
                current
            )

        else:

            current = 0

    return longest


# =========================================================
# EXTRACT ONE DOMAIN
# =========================================================

def extract_domain_features(
    domain
):

    domain = normalize_domain(
        domain
    )

    domain_length = len(
        domain
    )

    if domain_length == 0:

        domain_length = 1

    digit_count = sum(

        character.isdigit()

        for character in domain
    )

    letter_count = sum(

        character.isalpha()

        for character in domain
    )

    hyphen_count = domain.count(
        "-"
    )

    dot_count = domain.count(
        "."
    )

    special_char_count = sum(

        not character.isalnum()

        for character in domain
    )

    labels = [

        label

        for label in domain.split(
            "."
        )

        if label
    ]

    label_count = len(
        labels
    )

    max_label_length = (

        max(
            len(label)
            for label in labels
        )

        if labels

        else 0
    )

    tld_length = (

        len(
            labels[-1]
        )

        if labels

        else 0
    )

    digit_ratio = (
        digit_count
        /
        domain_length
    )

    hyphen_ratio = (
        hyphen_count
        /
        domain_length
    )

    unique_char_ratio = (
        len(
            set(
                domain
            )
        )
        /
        domain_length
    )

    entropy = calculate_entropy(
        domain
    )

    longest_digits = longest_digit_run(
        domain
    )

    return [
        domain_length,
        digit_count,
        letter_count,
        hyphen_count,
        dot_count,
        special_char_count,
        label_count,
        max_label_length,
        tld_length,
        digit_ratio,
        hyphen_ratio,
        unique_char_ratio,
        entropy,
        longest_digits,
    ]


# =========================================================
# SKLEARN TRANSFORMER
# =========================================================

class DomainLexicalTransformer(
    BaseEstimator,
    TransformerMixin
):

    def fit(
        self,
        X,
        y=None
    ):

        return self


    def transform(
        self,
        X
    ):

        # -------------------------------------------------
        # ColumnTransformer may send:
        #
        # Series
        # list
        # numpy array
        #
        # Normalize all of them into a flat sequence.
        # -------------------------------------------------

        if hasattr(
            X,
            "to_numpy"
        ):

            values = (
                X.to_numpy()
            )

        else:

            values = np.asarray(
                X
            )

        values = values.reshape(
            -1
        )

        features = [

            extract_domain_features(
                domain
            )

            for domain in values
        ]

        return np.asarray(
            features,
            dtype=float
        )


    def get_feature_names_out(
        self,
        input_features=None
    ):

        return np.asarray(
            FEATURE_NAMES,
            dtype=object
        )