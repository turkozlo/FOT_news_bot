
import os
import shutil
from newsendingbot.deduplicator import Deduplicator

TEST_FILE = "newsendingbot/test_dedup_storage.json"

if os.path.exists(TEST_FILE):
    os.remove(TEST_FILE)

print("Starting Deduplication Logic Verification...")

# Initialize deduplicator with a separate test file
dedup = Deduplicator(threshold=0.85, news_file=TEST_FILE)

news_text = "Apple выпустила новый iPhone 16 с искусственным интеллектом."

# 1. User A receives news
print("\n--- Step 1: User A processing ---")
is_dup_a = dedup.is_duplicate(news_text, user_id=101)
print(f"User A (101) first see: {is_dup_a} (Expected: False)")
assert not is_dup_a, "News should be new for User A"
dedup.add(news_text, user_id=101)

# 2. User A receives SAME news again
print("\n--- Step 2: User A duplicate check ---")
is_dup_a_2 = dedup.is_duplicate(news_text, user_id=101)
print(f"User A (101) second see: {is_dup_a_2} (Expected: True)")
assert is_dup_a_2, "News should be duplicate for User A"

# 3. User B receives SAME news (should NOT be duplicate)
print("\n--- Step 3: User B processing (Cross-user check) ---")
is_dup_b = dedup.is_duplicate(news_text, user_id=202)
print(f"User B (202) first see: {is_dup_b} (Expected: False)")
if is_dup_b:
    print("FAILURE: User B was blocked by User A's history!")
else:
    print("SUCCESS: User B is not blocked by User A.")
assert not is_dup_b, "News should be new for User B even if User A saw it"
dedup.add(news_text, user_id=202)

# 4. User B receives SAME news again
print("\n--- Step 4: User B duplicate check ---")
is_dup_b_2 = dedup.is_duplicate(news_text, user_id=202)
print(f"User B (202) second see: {is_dup_b_2} (Expected: True)")
assert is_dup_b_2

print("\nALL TESTS PASSED! Deduplication is now user-specific.")

# Cleanup
if os.path.exists(TEST_FILE):
    os.remove(TEST_FILE)
