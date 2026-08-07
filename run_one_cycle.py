import os
import json
from pipeline.worker import LocalWorker

def run():
    worker = LocalWorker(interval_seconds=60, max_cycles=1)
    print("Starting ONE controlled Local Worker cycle...")
    
    # Pre-cycle metrics
    opps_file = worker.engine.opps_file
    apps_file = worker.engine.approval_manager.approvals_file
    
    pre_opps = json.load(open(opps_file, encoding='utf-8')) if os.path.exists(opps_file) else []
    pre_apps = json.load(open(apps_file, encoding='utf-8')) if os.path.exists(apps_file) else []
    
    stats = worker.run_cycle(1)
    
    # Post-cycle metrics
    post_opps = json.load(open(opps_file, encoding='utf-8')) if os.path.exists(opps_file) else []
    post_apps = json.load(open(apps_file, encoding='utf-8')) if os.path.exists(apps_file) else []
    
    print("\n--- RESULTS ---")
    print(f"Opportunities Scanned/Processed: {stats.get('scanned', 0)}")
    print(f"Opportunities Evaluated: {stats.get('evaluated', 0)}")
    
    # Check proposal generation status on evaluated opportunities
    success_props = [o for o in post_opps if o.get('proposal_status') == 'SUCCESS']
    failed_props = [o for o in post_opps if o.get('proposal_status') == 'FAILED']
    
    print(f"Proposals Generated (SUCCESS): {len(success_props)}")
    print(f"Proposal Failures (FAILED): {len(failed_props)}")
    
    new_apps = len(post_apps) - len(pre_apps)
    print(f"Approval Records Created/Updated: {new_apps} (Total: {len(post_apps)})")
    
    # Duplicates skipped
    duplicates = stats.get('scanned', 0) - stats.get('evaluated', 0)
    print(f"Duplicates/Previously Evaluated Skipped: {duplicates}")
    
    print("Applications Submitted: 0 (No automated submission enabled in worker run)")
    print("Earnings Changed: 0 (No payout verification enabled in worker run)")

if __name__ == '__main__':
    run()
