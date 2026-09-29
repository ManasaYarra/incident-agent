"""15 realistic backend incident records.

Each record has: log, root_cause, fix, outcome ("worked" / "failed").
"""

fake_incidents = [
    # ---------- Database issues ----------
    {
        "log": (
            "2026-03-04 02:14:07,331 ERROR [order-service] HikariPool-1 - Connection is not available, "
            "request timed out after 30000ms.\n"
            "org.postgresql.util.PSQLException: FATAL: remaining connection slots are reserved for "
            "non-replication superuser connections\n"
            "  at com.zaxxer.hikari.pool.HikariPool.createTimeoutException(HikariPool.java:696)"
        ),
        "root_cause": (
            "A nightly batch job opened connections without releasing them (missing try-with-resources), "
            "exhausting Postgres max_connections (100) shared by all services."
        ),
        "fix": (
            "Killed idle-in-transaction sessions, patched the batch job to close connections, and "
            "introduced PgBouncer in transaction-pooling mode in front of the primary."
        ),
        "outcome": "worked",
    },
    {
        "log": (
            "2026-04-11 14:52:39,012 ERROR [billing-worker] ERROR: deadlock detected\n"
            "DETAIL: Process 18342 waits for ShareLock on transaction 9928113; blocked by process 18377.\n"
            "Process 18377 waits for ShareLock on transaction 9928107; blocked by process 18342.\n"
            "HINT: See server log for query details.\n"
            "CONTEXT: while updating tuple (4021,17) in relation \"invoices\""
        ),
        "root_cause": (
            "Two workers updated the same invoice and ledger rows in opposite order, creating a "
            "lock-ordering deadlock under concurrent month-end billing."
        ),
        "fix": (
            "Added a retry-with-backoff wrapper around the transaction and reduced concurrency from 16 "
            "to 8 workers as a stopgap."
        ),
        "outcome": "failed",  # deadlocks dropped but still recurred; lock ordering wasn't fixed
    },
    {
        "log": (
            "2026-05-19 09:03:22 WARN  [analytics-api] Slow query (48213 ms): SELECT * FROM events "
            "WHERE user_id = $1 AND created_at > $2 ORDER BY created_at DESC\n"
            "2026-05-19 09:03:25 ERROR [analytics-api] Query cancelled: statement timeout\n"
            "2026-05-19 09:03:25 ERROR [gateway] 504 Gateway Timeout on GET /v2/users/8841/activity"
        ),
        "root_cause": (
            "The events table grew to 900M rows after a data backfill, and the composite index on "
            "(user_id, created_at) had been dropped during a previous migration, forcing sequential scans."
        ),
        "fix": (
            "Recreated the index using CREATE INDEX CONCURRENTLY, then ran ANALYZE on the table."
        ),
        "outcome": "worked",
    },
    {
        "log": (
            "2026-06-02 23:41:10 ERROR [replica-monitor] Replication lag on db-replica-02: 1847s "
            "(threshold 60s)\n"
            "2026-06-02 23:41:12 ERROR [search-service] Stale read detected: product 55120 price mismatch "
            "between primary and replica"
        ),
        "root_cause": (
            "A long-running ALTER TABLE on the primary generated a large WAL burst; the replica's "
            "undersized disk IOPS could not replay it fast enough."
        ),
        "fix": (
            "Temporarily routed all reads to the primary, upgraded the replica's storage tier, and "
            "waited for lag to drain."
        ),
        "outcome": "worked",
    },

    # ---------- Memory leaks ----------
    {
        "log": (
            "2026-02-17 18:27:55 FATAL [notification-service] java.lang.OutOfMemoryError: Java heap space\n"
            "  at java.base/java.util.HashMap.resize(HashMap.java:700)\n"
            "  at com.acme.notify.SessionCache.put(SessionCache.java:58)\n"
            "kubelet: Container notification-service OOMKilled (exit code 137), restarts: 14 in last 6h"
        ),
        "root_cause": (
            "SessionCache was an unbounded HashMap with no eviction; entries for disconnected websocket "
            "clients were never removed."
        ),
        "fix": (
            "Replaced the HashMap with a Caffeine cache (max 50k entries, 30-minute expireAfterAccess) "
            "and added a removal hook on websocket disconnect."
        ),
        "outcome": "worked",
    },
    {
        "log": (
            "2026-03-29 11:08:44 WARN  [image-processor] RSS memory 3.7GiB / limit 4GiB (92%)\n"
            "2026-03-29 11:19:03 ERROR [image-processor] MemoryError: Unable to allocate 128 MiB for an "
            "array with shape (4096, 4096, 2)\n"
            "Worker pid 2211 killed by OOM killer"
        ),
        "root_cause": (
            "A Pillow/NumPy image pipeline kept references to full-resolution intermediate arrays in a "
            "module-level list used for debug logging that was accidentally left enabled in production."
        ),
        "fix": (
            "Disabled the debug collector via config flag and increased the pod memory limit from 4GiB "
            "to 6GiB."
        ),
        "outcome": "failed",  # limit raise masked it; the flag wasn't deployed to all pods, leak persisted
    },
    {
        "log": (
            "2026-07-08 04:12:19 ERROR [ws-gateway] EMFILE: too many open files, accept\n"
            "2026-07-08 04:12:19 ERROR [ws-gateway] Active connections: 65211, file descriptors in use: "
            "65530/65536\n"
            "2026-07-08 04:12:21 ERROR [lb] Health check failed for ws-gateway-3, removing from pool"
        ),
        "root_cause": (
            "Websocket handler failed to close sockets when clients dropped without a FIN (mobile "
            "network switches), leaking file descriptors until the process hit the ulimit."
        ),
        "fix": (
            "Added server-side ping/pong heartbeats with a 45s idle timeout to reap dead connections "
            "and raised nofile ulimit to 262144."
        ),
        "outcome": "worked",
    },

    # ---------- API timeouts ----------
    {
        "log": (
            "2026-01-22 16:33:08 ERROR [checkout-service] java.net.SocketTimeoutException: Read timed out "
            "calling http://inventory-service/api/v1/reserve (timeout=5000ms)\n"
            "2026-01-22 16:33:08 WARN  [checkout-service] Retry 3/3 failed, giving up\n"
            "2026-01-22 16:33:09 ERROR [gateway] 502 Bad Gateway POST /checkout - upstream_response_time=15.2"
        ),
        "root_cause": (
            "inventory-service was blocked on a synchronous call to a legacy warehouse system that had "
            "slowed down; checkout's aggressive retries tripled the load and caused a retry storm."
        ),
        "fix": (
            "Added a circuit breaker (Resilience4j) with exponential backoff and jitter on the checkout "
            "client, and cached inventory availability for 10 seconds."
        ),
        "outcome": "worked",
    },
    {
        "log": (
            "2026-04-03 13:15:47 ERROR [user-profile-api] context deadline exceeded "
            "(Client.Timeout exceeded while awaiting headers)\n"
            "2026-04-03 13:15:47 ERROR [user-profile-api] GET https://auth.internal/v1/token/introspect "
            "latency=10.001s\n"
            "2026-04-03 13:15:50 WARN  [gateway] p99 latency 11.4s on /profile (SLO: 800ms)"
        ),
        "root_cause": (
            "The auth service's DNS entry pointed to a decommissioned node after a cluster migration, "
            "so ~25% of requests hit a dead IP and waited for the full timeout."
        ),
        "fix": (
            "Lowered the client timeout from 10s to 2s and restarted pods to flush the DNS cache."
        ),
        "outcome": "failed",  # stale DNS record remained at the resolver; timeouts returned within an hour
    },
    {
        "log": (
            "2026-08-14 20:05:31 ERROR [report-generator] Request timeout: POST /api/reports/export "
            "exceeded 60s (nginx upstream timed out, 504)\n"
            "2026-08-14 20:05:31 WARN  [report-generator] Export of 2.4M rows still running, "
            "worker 3 heap at 91%"
        ),
        "root_cause": (
            "Large customer exports were processed synchronously inside the HTTP request, exceeding "
            "the load balancer's 60s timeout."
        ),
        "fix": (
            "Converted exports to an async job: the endpoint returns 202 with a job ID, a background "
            "worker streams results to S3, and the client polls for a signed download URL."
        ),
        "outcome": "worked",
    },

    # ---------- Deployment failures ----------
    {
        "log": (
            "2026-02-05 10:44:02 ERROR [deploy-pipeline] Rolling update of payments-api stalled: "
            "0/6 new pods ready after 600s\n"
            "kubectl describe pod payments-api-7d9f8b-xk2lp:\n"
            "  Warning  Failed  ImagePullBackOff: Back-off pulling image "
            "\"registry.acme.io/payments-api:v3.18.0\": manifest unknown"
        ),
        "root_cause": (
            "The CI job tagged and pushed the image to the wrong registry repository because of a "
            "renamed environment variable in the pipeline config."
        ),
        "fix": (
            "Rolled back to v3.17.4 via kubectl rollout undo, fixed the pipeline variable, and "
            "re-ran the build and deploy."
        ),
        "outcome": "worked",
    },
    {
        "log": (
            "2026-05-27 15:20:11 ERROR [orders-api] Liveness probe failed: HTTP probe failed with "
            "statuscode: 500\n"
            "2026-05-27 15:20:14 ERROR [orders-api] Traceback (most recent call last):\n"
            "  File \"/app/models/order.py\", line 88, in <module>\n"
            "sqlalchemy.exc.ProgrammingError: column orders.fulfillment_status does not exist\n"
            "Pod orders-api-5c6d7f: CrashLoopBackOff (restarts: 9)"
        ),
        "root_cause": (
            "The new application version was deployed before the database migration that adds "
            "fulfillment_status had run, because the migration job was configured as a post-deploy hook."
        ),
        "fix": (
            "Manually ran the migration, restarted the pods, and moved the migration to a pre-deploy "
            "init step in the pipeline."
        ),
        "outcome": "worked",
    },
    {
        "log": (
            "2026-09-09 07:58:36 ERROR [config-loader] Failed to start recommendation-service: "
            "Missing required environment variable REDIS_TLS_CERT_PATH\n"
            "2026-09-09 07:58:36 ERROR [recommendation-service] Startup aborted (exit code 78)\n"
            "2026-09-09 07:59:10 WARN  [argo-rollouts] Canary aborted at 10% traffic, error rate 100%"
        ),
        "root_cause": (
            "A new required config value was added to the Helm chart's production values file in a "
            "feature branch that hadn't been merged to the environment-config repo."
        ),
        "fix": (
            "Argo automatically aborted the canary; the team added the variable to the config repo "
            "and redeployed with a startup config validation check in CI."
        ),
        "outcome": "worked",
    },

    # ---------- Third-party service outages ----------
    {
        "log": (
            "2026-03-12 19:22:47 ERROR [payment-service] Stripe API error: 503 Service Unavailable "
            "(request_id=req_9fQx2LmTz)\n"
            "2026-03-12 19:22:47 ERROR [payment-service] Failed to create PaymentIntent for order 771902\n"
            "2026-03-12 19:23:30 ERROR [alerting] payment_success_rate=41% (threshold 95%)"
        ),
        "root_cause": (
            "A Stripe platform incident degraded their API for ~40 minutes; our service had no "
            "fallback and returned hard failures to customers."
        ),
        "fix": (
            "Enabled a queue-and-retry path that stored pending payment attempts and replayed them "
            "with idempotency keys once Stripe recovered; showed a 'payment processing' status page."
        ),
        "outcome": "worked",
    },
    {
        "log": (
            "2026-06-21 08:31:05 ERROR [email-worker] SendGrid API returned 429 Too Many Requests\n"
            "2026-06-21 08:31:05 ERROR [email-worker] Rate limit exceeded: X-RateLimit-Remaining: 0, "
            "reset in 3600s\n"
            "2026-06-21 08:31:09 WARN  [email-worker] Queue depth: 182,440 (password-reset emails delayed)"
        ),
        "root_cause": (
            "A marketing campaign was sent through the same API key as transactional email, consuming "
            "the hourly rate limit and starving password-reset and receipt emails."
        ),
        "fix": (
            "Paused the campaign job and requested a limit increase from SendGrid; kept using the "
            "shared API key."
        ),
        "outcome": "failed",  # limit not raised in time; transactional emails stayed delayed for ~2 hours
    },
    {
        "log": (
            "2026-08-30 03:17:52 ERROR [storage-service] botocore.exceptions.EndpointConnectionError: "
            "Could not connect to the endpoint URL: \"https://acme-uploads.s3.us-east-1.amazonaws.com/\"\n"
            "2026-08-30 03:17:52 ERROR [upload-api] 500 on POST /v1/files (attempt 4/4)\n"
            "2026-08-30 03:18:40 ERROR [alerting] s3_put_error_rate=100% in us-east-1"
        ),
        "root_cause": (
            "A regional AWS S3 outage in us-east-1 made the single-region uploads bucket unreachable."
        ),
        "fix": (
            "Failed over uploads to a cross-region replica bucket in us-west-2 via a feature flag, "
            "then reconciled objects back after AWS recovered."
        ),
        "outcome": "worked",
    },
]


if __name__ == "__main__":
    from collections import Counter

    print(f"Total incidents: {len(fake_incidents)}")
    print(Counter(i["outcome"] for i in fake_incidents))
