import json

from runtime_service import (
    BetGuardRuntime,
)


# =========================================================
# BETGUARD
# RUNTIME SERVICE TEST V2
# =========================================================
#
# Tests:
#
# 1. Runtime initialization
# 2. Normal domain evaluation
# 3. Cache hits
# 4. URL/domain normalization
#
# =========================================================


def display(
    title,
    value
):

    print(
        "\n===================================="
    )

    print(
        f" {title}"
    )

    print(
        "===================================="
    )

    print(
        json.dumps(
            value,
            indent=4
        )
    )


def main():

    # =====================================================
    # INITIALIZE
    # =====================================================

    service = BetGuardRuntime()


    display(
        "INITIAL STATUS",
        service.get_status()
    )


    # =====================================================
    # FIRST REQUEST
    # =====================================================

    domains = [
        "stake.com",
        "draftkings.com",
        "wikipedia.org",
        "microsoft.com",
        "reddit.com",
    ]


    first_results = (
        service.evaluate_many(
            domains
        )
    )


    display(
        "FIRST REQUEST",
        first_results
    )


    # =====================================================
    # SECOND REQUEST
    #
    # All should come from cache.
    # =====================================================

    second_results = (
        service.evaluate_many(
            domains
        )
    )


    display(
        "SECOND REQUEST - CACHE TEST",
        second_results
    )


    # =====================================================
    # NORMALIZATION TEST
    #
    # These should all resolve to:
    #
    #     stake.com
    #
    # and therefore share the existing cache entry.
    # =====================================================

    normalized_inputs = [
        "stake.com",
        "www.stake.com",
        "https://stake.com",
        "https://stake.com/",
        "https://www.stake.com/casino",
    ]


    normalization_results = (
        service.evaluate_many(
            normalized_inputs
        )
    )


    display(
        "NORMALIZATION CACHE TEST",
        normalization_results
    )


    # =====================================================
    # VERIFY NORMALIZED DOMAIN
    # =====================================================

    normalization_passed = all(

        result.get(
            "domain"
        )
        ==
        "stake.com"

        for result
        in normalization_results

        if "error" not in result
    )


    # =====================================================
    # VERIFY CACHE
    # =====================================================

    cache_passed = all(

        result.get(
            "cache_hit"
        )
        is True

        for result
        in normalization_results

        if "error" not in result
    )


    display(
        "NORMALIZATION RESULT",
        {
            "normalized_to_stake_com":
                normalization_passed,

            "all_cache_hits":
                cache_passed,

            "test_passed":
                (
                    normalization_passed
                    and
                    cache_passed
                ),
        }
    )


    # =====================================================
    # FINAL STATUS
    # =====================================================

    display(
        "FINAL STATUS",
        service.get_status()
    )


if __name__ == "__main__":

    main()