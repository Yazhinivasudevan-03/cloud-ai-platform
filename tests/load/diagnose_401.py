"""Diagnostic script: reproduce the ~50% 401 rate seen under sustained
Locust load, with more visibility than Locust's own summary gives."""
import asyncio
import httpx

BASE_URL = "http://backend:8000"
NUM_USERS = 10
DURATION_SECONDS = 60


async def simulate_user(user_id: int, results: list, headers_store: dict) -> None:
    username = f"loadtest_viewer_{user_id % 20}"
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=10.0) as client:
        headers = headers_store[user_id]
        end_time = asyncio.get_event_loop().time() + DURATION_SECONDS
        while asyncio.get_event_loop().time() < end_time:
            resp = await client.get("/api/v1/auth/me", headers=headers)
            results.append((user_id, "me", resp.status_code, resp.text[:200] if resp.status_code != 200 else ""))
            await asyncio.sleep(1)


async def main() -> None:
    results: list = []
    headers_store: dict = {}

    # Stagger logins first (respecting RATE_LIMIT_LOGIN), exactly like the
    # real Locust run's slow ramp-up did - so every user starts the
    # sustained polling phase with a token already confirmed valid.
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=10.0) as login_client:
        for user_id in range(NUM_USERS):
            username = f"loadtest_viewer_{user_id % 20}"
            resp = await login_client.post(
                "/api/v1/auth/login",
                data={"username": username, "password": "Sup3rSecret1"},
            )
            if resp.status_code != 200:
                print(f"user {user_id}: LOGIN FAILED {resp.status_code} {resp.text}")
                headers_store[user_id] = {}
                continue
            token = resp.json()["access_token"]
            headers_store[user_id] = {"Authorization": f"Bearer {token}"}
            await asyncio.sleep(12)  # ~5/minute

    print("All logins done, starting sustained concurrent polling...")
    await asyncio.gather(*(simulate_user(i, results, headers_store) for i in range(NUM_USERS)))

    by_user: dict[int, list] = {}
    for user_id, kind, status, body in results:
        by_user.setdefault(user_id, []).append((kind, status, body))

    for user_id, entries in sorted(by_user.items()):
        statuses = [e[1] for e in entries]
        fail_count = sum(1 for s in statuses if s != 200)
        print(f"user {user_id}: {len(entries)} requests, {fail_count} non-200")
        if fail_count:
            for kind, status, body in entries:
                if status != 200:
                    print(f"    {kind} -> {status}: {body}")
                    break


if __name__ == "__main__":
    asyncio.run(main())
