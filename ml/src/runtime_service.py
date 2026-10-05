from collections import OrderedDict
from threading import RLock

if __package__:
    from . import decision_engine
else:
    import decision_engine

USER_ALLOWLIST_FILE = decision_engine.USER_ALLOWLIST_FILE
USER_BLOCKLIST_FILE = decision_engine.USER_BLOCKLIST_FILE
decide_domain = decision_engine.decide_domain
load_gambling_blocklist = decision_engine.load_gambling_blocklist
load_model = decision_engine.load_model
load_text_list = decision_engine.load_text_list
normalize_domain = decision_engine.normalize_domain


# =========================================================
# BETGUARD
# RUNTIME DETECTION SERVICE V3
# =========================================================
#
# Loads expensive resources ONCE:
#
#     ML model
#     gambling blocklist
#     user allowlist
#     user blocklist
#
# Improvements:
#
#     - normalized cache keys
#     - thread-safe cache
#     - correct current input on cache hits
#
# =========================================================


class BetGuardRuntime:

    def __init__(
        self,
        cache_size=10000,
        verbose=True,
        use_user_lists=True
    ):

        self.verbose = verbose
        # Application rules live in Android Room, never in shared server text
        # lists. Standalone CLI users retain the original behavior by default.
        self.use_user_lists = use_user_lists

        if self.verbose:

            print(
                "\n===================================="
            )

            print(
                " BETGUARD RUNTIME INITIALIZATION"
            )

            print(
                "===================================="
            )


        # =================================================
        # MODEL
        # =================================================

        if self.verbose:

            print(
                "\nLoading ML model..."
            )


        (
            self.model,
            self.model_config,

        ) = load_model()


        if self.verbose:

            print(
                "Model loaded:"
            )

            print(
                self.model_config.get(
                    "display_name",
                    self.model_config.get(
                        "model_name",
                        "unknown"
                    )
                )
            )


        # =================================================
        # GAMBLING BLOCKLIST
        # =================================================

        if self.verbose:

            print(
                "\nLoading gambling blocklist..."
            )


        self.gambling_lookup = (
            load_gambling_blocklist()
        )


        if self.verbose:

            print(
                "Gambling domains loaded:"
            )

            print(
                f"{len(self.gambling_lookup):,}"
            )


        # =================================================
        # USER LISTS
        # =================================================

        self.allowlist = (
            load_text_list(
                USER_ALLOWLIST_FILE
            ) if self.use_user_lists else set()
        )


        self.user_blocklist = (
            load_text_list(
                USER_BLOCKLIST_FILE
            ) if self.use_user_lists else set()
        )


        if self.verbose:

            print(
                "\nUser allowlist entries:"
            )

            print(
                len(
                    self.allowlist
                )
            )

            print(
                "User blocklist entries:"
            )

            print(
                len(
                    self.user_blocklist
                )
            )


        # =================================================
        # CACHE
        # =================================================

        self.cache_size = max(
            0,
            int(
                cache_size
            )
        )


        self.cache = OrderedDict()


        # =================================================
        # THREAD LOCK
        # =================================================

        self.lock = RLock()


        # =================================================
        # STATISTICS
        # =================================================

        self.request_count = 0

        self.cache_hits = 0

        self.cache_misses = 0


        if self.verbose:

            print(
                "\nRuntime ready."
            )


    # =====================================================
    # CACHE KEY
    # =====================================================

    def _make_cache_key(
        self,
        value
    ):

        return normalize_domain(
            value
        )


    # =====================================================
    # CACHE LOOKUP
    # =====================================================

    def _get_cached(
        self,
        cache_key
    ):

        with self.lock:

            if cache_key not in self.cache:

                return None


            result = self.cache.pop(
                cache_key
            )


            self.cache[
                cache_key
            ] = result


            self.cache_hits += 1


            return dict(
                result
            )


    # =====================================================
    # CACHE SAVE
    # =====================================================

    def _cache_result(
        self,
        cache_key,
        result
    ):

        if self.cache_size <= 0:

            return


        with self.lock:

            if cache_key in self.cache:

                self.cache.pop(
                    cache_key
                )


            self.cache[
                cache_key
            ] = dict(
                result
            )


            while (
                len(
                    self.cache
                )
                >
                self.cache_size
            ):

                self.cache.popitem(
                    last=False
                )


    # =====================================================
    # EVALUATE ONE DOMAIN
    # =====================================================

    def evaluate(
        self,
        value
    ):
        # Reloads replace list snapshots and clear the cache under this lock.
        # Keep inference and cache insertion in the same transaction so an
        # in-flight result cannot repopulate a cache after a list reload.
        with self.lock:
            return self._evaluate(value)


    def _evaluate(self, value):

        with self.lock:

            self.request_count += 1


        cache_key = (
            self._make_cache_key(
                value
            )
        )


        if not cache_key:

            return {
                "input":
                    value,

                "error":
                    "Invalid or empty domain",

                "cache_hit":
                    False,
            }


        # =================================================
        # CACHE LOOKUP
        # =================================================

        cached = self._get_cached(
            cache_key
        )


        if cached is not None:

            # IMPORTANT:
            #
            # The decision belongs to the normalized
            # domain, but "input" should represent the
            # CURRENT request, not the first cached one.

            cached[
                "input"
            ] = value


            cached[
                "cache_hit"
            ] = True


            return cached


        with self.lock:

            self.cache_misses += 1


        # =================================================
        # RUN DECISION ENGINE
        # =================================================

        result = decide_domain(

            value,

            self.model,

            self.model_config,

            self.gambling_lookup,

            self.allowlist,

            self.user_blocklist,
        )


        result[
            "cache_hit"
        ] = False


        # =================================================
        # CACHE SUCCESSFUL RESULT
        # =================================================

        if (
            "error"
            not in result
        ):

            self._cache_result(
                cache_key,
                result
            )


        return result


    # =====================================================
    # EVALUATE MANY
    # =====================================================

    def evaluate_many(
        self,
        domains
    ):

        results = []


        for domain in domains:

            results.append(
                self.evaluate(
                    domain
                )
            )


        return results


    # =====================================================
    # RELOAD USER LISTS
    # =====================================================

    def reload_user_lists(
        self
    ):

        new_allowlist = (
            load_text_list(
                USER_ALLOWLIST_FILE
            ) if self.use_user_lists else set()
        )


        new_blocklist = (
            load_text_list(
                USER_BLOCKLIST_FILE
            ) if self.use_user_lists else set()
        )


        with self.lock:

            self.allowlist = (
                new_allowlist
            )


            self.user_blocklist = (
                new_blocklist
            )


            previous_cache_size = len(
                self.cache
            )


            self.cache.clear()


        return {
            "allowlist_count":
                len(
                    self.allowlist
                ),

            "blocklist_count":
                len(
                    self.user_blocklist
                ),

            "cache_entries_cleared":
                previous_cache_size,
        }


    # =====================================================
    # RELOAD GAMBLING BLOCKLIST
    # =====================================================

    def reload_gambling_blocklist(
        self
    ):

        new_lookup = (
            load_gambling_blocklist()
        )


        with self.lock:

            self.gambling_lookup = (
                new_lookup
            )


            previous_cache_size = len(
                self.cache
            )


            self.cache.clear()


        return {
            "gambling_domains":
                len(
                    self.gambling_lookup
                ),

            "cache_entries_cleared":
                previous_cache_size,
        }


    # =====================================================
    # CLEAR CACHE
    # =====================================================

    def clear_cache(
        self
    ):

        with self.lock:

            previous_size = len(
                self.cache
            )


            self.cache.clear()


        return {
            "cleared_entries":
                previous_size
        }


    # =====================================================
    # STATUS
    # =====================================================

    def get_status(
        self
    ):

        with self.lock:

            total_cache_requests = (
                self.cache_hits
                +
                self.cache_misses
            )


            if total_cache_requests > 0:

                cache_hit_rate = (
                    self.cache_hits
                    /
                    total_cache_requests
                )

            else:

                cache_hit_rate = 0.0


            return {

                "ready":
                    True,

                "model_name":
                    self.model_config.get(
                        "model_name"
                    ),

                "model_display_name":
                    self.model_config.get(
                        "display_name"
                    ),

                "operating_policy":
                    self.model_config.get(
                        "operating_policy"
                    ),

                "gambling_blocklist_domains":
                    len(
                        self.gambling_lookup
                    ),

                "user_allowlist_domains":
                    len(
                        self.allowlist
                    ),

                "user_blocklist_domains":
                    len(
                        self.user_blocklist
                    ),

                "cache_entries":
                    len(
                        self.cache
                    ),

                "cache_capacity":
                    self.cache_size,

                "requests":
                    self.request_count,

                "cache_hits":
                    self.cache_hits,

                "cache_misses":
                    self.cache_misses,

                "cache_hit_rate":
                    round(
                        cache_hit_rate,
                        4
                    ),
            }
