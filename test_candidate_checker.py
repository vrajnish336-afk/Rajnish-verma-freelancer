import os
import json
from check_opp_latest import get_candidates

def test_github_bounty_candidate():
    print("Running test_github_bounty_candidate...")
    
    DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')
    OPPS_FILE = os.path.join(DATA_DIR, 'opportunities.json')
    APPS_FILE = os.path.join(DATA_DIR, 'approvals.json')
    APPLIED_FILE = os.path.join(DATA_DIR, 'applications.json')

    with open(OPPS_FILE, 'r', encoding='utf-8') as f:
        opps = json.load(f)
    try:
        with open(APPS_FILE, 'r', encoding='utf-8') as f:
            apps = json.load(f)
    except:
        apps = []
    try:
        with open(APPLIED_FILE, 'r', encoding='utf-8') as f:
            applied = json.load(f)
    except:
        applied = []

    candidates = get_candidates(opps, apps, applied)

    found = False
    for c in candidates:
        if "1,500" in c.get('title', '') and c.get('platform') == 'GitHub':
            found = True
            break
            
    if found:
        print("[PASSED]: $1,500 GitHub case is a valid candidate!")
        print(f"Total candidates found: {len(candidates)}")
        return True
    else:
        print("[FAILED]: $1,500 GitHub case was NOT found in candidates.")
        print(f"Total candidates found: {len(candidates)}")
        return False

if __name__ == '__main__':
    passed = 0
    failed = 0
    
    if test_github_bounty_candidate():
        passed += 1
    else:
        failed += 1
        
    print(f"\nTest Results: {passed} passed, {failed} failed.")
    if failed > 0:
        exit(1)
