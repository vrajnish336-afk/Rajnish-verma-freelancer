import json

def read_json(path):
    try:
        return json.load(open(path, 'r', encoding='utf-8'))
    except Exception as e:
        return []

opps = read_json('data/opportunities.json')
apps = read_json('data/approvals.json')
if isinstance(apps, dict) and 'pending_approvals' in apps:
    apps = apps['pending_approvals']
elif isinstance(apps, list):
    pass

applied = read_json('data/applications.json')
applied_urls = {a.get('url') for a in applied}

candidates = []
opps_dict = {o.get('url'): o for o in opps}

for o in opps:
    url = o.get('url')
    
    reward_verified = o.get('reward_verified')
    proposal = o.get('proposal')
    auto_allowed = o.get('automation_allowed', False)
    evidence = o.get('reward_evidence')
    score = o.get('profit_score') or 0
    status = "EVALUATED"
    
    if reward_verified and url and proposal and url not in applied_urls and auto_allowed:
        candidates.append({
            'platform': o.get('platform'),
            'title': o.get('title'),
            'reward': f"{o.get('reward')} {o.get('currency')}",
            'evidence': evidence,
            'score': score,
            'proposal': proposal[:200] + '...' if len(proposal) > 200 else proposal,
            'auto': auto_allowed,
            'status': status
        })

if not candidates:
    print('No opportunity satisfies ALL conditions.')
    print('Reasons:')
    for o in opps:
        if o.get('automation_allowed'):
            print(f"- {o.get('title')[:30]}: verified={o.get('reward_verified')}, has_prop={bool(o.get('proposal'))}")
        elif o.get('proposal'):
            print(f"- {o.get('title')[:30]}: verified={o.get('reward_verified')}, auto={o.get('automation_allowed')}")
else:
    candidates.sort(key=lambda x: x['score'], reverse=True)
    best = candidates[0]
    print(f"1. Platform: {best['platform']}")
    print(f"2. Opportunity title: {best['title']}")
    print(f"3. Verified reward: {best['reward']}")
    print(f"4. Reward evidence: {best['evidence']}")
    print(f"5. AI score: {best['score']}")
    print(f"6. Proposal: {best['proposal']}")
    print(f"7. automation_allowed: {best['auto']}")
    print(f"8. duplicate check result: NOT APPLIED")
    print(f"9. approval status: {best['status']}")
    print(f"10. exact action that would happen after approval: Automatic submission to the GitHub API via GitHubPlatform.post_comment(), followed by moving the status to SUBMITTED and recording the event in data/applications.json.")
