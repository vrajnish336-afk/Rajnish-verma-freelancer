import json
import os

def get_candidates(opps, apps, applied):
    applied_urls = {a.get('url') for a in applied if a.get('url')}
    candidates = []

    for o in opps:
        url = o.get('url')
        opp_id = str(o.get('id', ''))
        
        # Match by opportunity_id first
        app_record = None
        if opp_id:
            app_record = next((a for a in apps if str(a.get('opportunity_id', '')) == opp_id), None)
            
        # URL as safe fallback
        if not app_record and url:
            app_record = next((a for a in apps if a.get('url') == url), None)

        status = app_record.get('approval_status') if app_record else "NOT_IN_APPROVALS"
        
        reward_verified = o.get('reward_verified')
        proposal_status = o.get('proposal_status', 'UNKNOWN')
        proposal_exists = o.get('proposal_exists', False)
        proposal = o.get('proposal', '')
        auto_allowed = o.get('automation_allowed', False)
        
        if reward_verified and url and proposal_status == 'SUCCESS' and proposal_exists and proposal and url not in applied_urls and auto_allowed and status == 'PENDING_APPROVAL':
            candidates.append(o)
        else:
            if o.get('profit_score', 0) > 0:
                print(f"Skipped {o.get('title')[:40]}...")
                if not reward_verified: print("  - reward_verified is false")
                if not url: print("  - missing url")
                if proposal_status != 'SUCCESS': print(f"  - proposal_status is {proposal_status} (expected SUCCESS)")
                if not proposal_exists: print("  - proposal_exists is false")
                if not proposal: print("  - proposal is empty")
                if not auto_allowed: print("  - automation_allowed is false")
                if url in applied_urls: print("  - already applied")
                if status != 'PENDING_APPROVAL': print(f"  - approval status is {status} (expected PENDING_APPROVAL)")

    return candidates

def main():
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

    if candidates:
        print(f"Found {len(candidates)} candidates.")
    else:
        print("Zero candidates exist.")

if __name__ == '__main__':
    main()
