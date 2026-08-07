import streamlit as st
import pandas as pd
from dotenv import load_dotenv

from engine.application_engine import ApplicationEngine
from models.opportunity import (
    APP_STATE_DRAFT, APP_STATE_APPROVED, APP_STATE_SUBMITTED,
    PAYMENT_CONFIRMED
)
from notifications import STATUS_PENDING, STATUS_APPROVED, STATUS_REJECTED
from dashboard import DashboardTrackingLayer

load_dotenv()

st.set_page_config(
    page_title="MEGA Freelancer MVP Engine Dashboard",
    page_icon="🤖",
    layout="wide",
)

st.title("🤖 MEGA Freelancer — MVP Engine Dashboard")
st.markdown("---")

engine = ApplicationEngine()
tracker = DashboardTrackingLayer()

# Refresh button
col_t1, col_t2 = st.columns([8, 2])
with col_t2:
    if st.button("🔄 Refresh Dashboard Data", use_container_width=True):
        st.rerun()

# Sidebar
st.sidebar.header("🛡️ MEGA Safety & Integrity")
st.sidebar.success("Fake earnings: BLOCKED")
st.sidebar.success("Fake transactions: BLOCKED")
st.sidebar.success("Earnings: PAYMENT_CONFIRMED only")
st.sidebar.info("Manual approval strictly required")

# Load & track dashboard sections
sections = tracker.get_dashboard_sections()
metrics = tracker.get_financial_metrics(sections)
pending_approvals = sections.get("Pending Approval", [])

if pending_approvals:
    st.warning(f"🔔 **Notification:** You have **{len(pending_approvals)}** opportunity(s) in **PENDING_APPROVAL** status! Please review proposal previews in the '🔔 Pending Approval' tab.")

# Financial Metrics Banner (Kept strictly separated!)
m1, m2, m3, m4 = st.columns(4)
m1.metric("🔮 Potential Rewards", f"${metrics['Potential Rewards']:,.2f}", help="Total reward of newly discovered and unapproved opportunities.")
m2.metric("📝 Applied Value", f"${metrics['Applied Value']:,.2f}", help="Total reward of submitted and ready applications.")
m3.metric("🤝 Accepted Value", f"${metrics['Accepted Value']:,.2f}", help="Total reward of accepted work and work in progress.")
m4.metric("💵 Confirmed Earnings", f"${metrics['Confirmed Earnings']:,.2f}", help="Strictly counted ONLY from PAYMENT_CONFIRMED receipts with verified transaction evidence.")
if "Owner Confirmed Earnings" in metrics and "Agent Confirmed Earnings" in metrics:
    m4.caption(f"**Owner (70%):** ${metrics['Owner Confirmed Earnings']:,.2f} | **Agent (30%):** ${metrics['Agent Confirmed Earnings']:,.2f}")

st.markdown("---")
st.subheader("📡 Latest Scan Cycle Status")
latest_scan = engine.get_latest_scan()
if latest_scan:
    scan_time = latest_scan.get("scan_time", latest_scan.get("timestamp", "Unknown"))
    sources = latest_scan.get("sources_scanned", list(latest_scan.get("scanner_health", {}).keys()))
    opps_found = latest_scan.get("opportunities_found", latest_scan.get("counts", {}).get("unique", 0))
    verified_opps = latest_scan.get("verified_paid_opportunities", latest_scan.get("counts", {}).get("verified", 0))
    errors = latest_scan.get("errors", [])
    duration = latest_scan.get("duration", latest_scan.get("duration_seconds", "N/A"))

    time_str = str(scan_time)
    if "T" in time_str:
        try:
            parts = time_str.split("T")
            time_str = f"{parts[0]} {parts[1][:8]} UTC"
        except Exception:
            pass

    sources_str = ", ".join(sources) if isinstance(sources, list) else str(sources)
    duration_str = f"{duration}s" if isinstance(duration, (int, float)) else str(duration)

    st.write(f"**🕒 Scan Time:** `{time_str}` &nbsp;|&nbsp; **🌐 Sources Scanned:** `{sources_str}` &nbsp;|&nbsp; **⏱️ Duration:** `{duration_str}`")

    sc1, sc2, sc3, sc4 = st.columns(4)
    sc1.metric("🎯 Opportunities Found", opps_found)
    sc2.metric("💰 Verified Paid Opportunities", verified_opps)
    sc3.metric("⌛ Duration", duration_str)
    sc4.metric("⚠️ Scan Errors", len(errors))

    if errors:
        with st.expander(f"⚠️ View Scan Errors ({len(errors)})", expanded=True):
            for err in errors:
                st.error(err)
    else:
        st.caption("✅ Latest scan completed cleanly with no errors.")
else:
    st.info("No scan records yet. Run `python scan_only.py` or `python main.py` to record a scan cycle.")

st.markdown("---")

# Global Filtering Controls
st.write("### 🎛️ Global Dashboard Filters")
f_col1, f_col2, _ = st.columns([3, 3, 4])
with f_col1:
    plat_opts = tracker.get_available_platforms(sections)
    selected_plat = st.selectbox("Filter by Platform:", plat_opts, index=0)
with f_col2:
    selected_stat = st.selectbox("Filter by Status:", ["All", "NEW", "PENDING_APPROVAL", "READY", "MANUAL_ACTION_REQUIRED", "SUBMITTED", "ACCEPTED", "COMPLETED", "PAYMENT_PENDING", "PAYMENT_CONFIRMED"], index=0)

# Render 7 Separate Standalone Sections
tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs([
    f"1. 🆕 New Opportunities ({len(sections['New Opportunities'])})",
    f"2. 🔔 Pending Approval ({len(sections['Pending Approval'])})",
    f"3. 📝 Applications ({len(sections['Applications'])})",
    f"4. 🤝 Accepted Work ({len(sections['Accepted Work'])})",
    f"5. 🏁 Work Completed ({len(sections['Work Completed'])})",
    f"6. ⏳ Pending Payments ({len(sections['Pending Payments'])})",
    f"7. 💵 Confirmed Earnings ({len(sections['Confirmed Earnings'])})"
])

def render_items(item_list, section_name, show_actions=False, is_approval_tab=False):
    filtered_list = tracker.filter_items(item_list, platform_filter=selected_plat, status_filter=selected_stat)
    if not filtered_list:
        st.info(f"No items available in **{section_name}** matching filters (Platform: {selected_plat}, Status: {selected_stat}).")
        return

    for idx, item in enumerate(reversed(filtered_list)):
        status = item.get("status", "Unknown")
        payment_status = item.get("payment_status", "PAYMENT_UNKNOWN")
        color = "blue"
        if status in ["PENDING_APPROVAL", "DRAFT", "NEW"]: color = "orange"
        elif status == "MANUAL_ACTION_REQUIRED": color = "red"
        elif status in ["SUBMITTED", "APPROVED", "READY"]: color = "green"
        elif status in ["ACCEPTED", "COMPLETED", "PAYMENT_CONFIRMED"]: color = "violet"

        with st.expander(f"[{item.get('platform')}] {item.get('title')} — Job Status: :{color}[{status}] | Payment: `{payment_status}`", expanded=is_approval_tab):
            col_a, col_b = st.columns(2)
            with col_a:
                st.write(f"**Platform:** `{item.get('platform')}` &nbsp;|&nbsp; **Profit Score:** `{item.get('profit_score')}`")
                st.write(f"**URL:** [Open Opportunity Link]({item.get('url')})")
                st.write(f"**Job Status:** :{color}[**{status}**] &nbsp;|&nbsp; **Payment Status:** `{payment_status}`")
            with col_b:
                st.write(f"**Reward:** `{item.get('reward', 'Unknown')} {item.get('currency', '')}` (Verified: `{'YES ✅' if item.get('reward_verified') else 'NO ⚠️'}`)")
                st.write(f"**Deadline:** `{item.get('deadline', 'Not specified')}`")
                st.write(f"**Timestamps:** Created: `{item.get('created_at')}` | Submitted: `{item.get('submitted_at')}`")
                if item.get("transaction_hash"):
                    st.success(f"**Verified Evidence:** `{item.get('transaction_hash')}` (Received: ${item.get('actual_amount_received')})")

            if item.get("proposal"):
                st.write("**AI Proposal / Execution Plan:**")
                st.code(item.get("proposal"), language="markdown")

            # Interactive UI controls for workflow transitions
            app_id = item.get("id")
            opp_id = item.get("opportunity_id", app_id)
            if is_approval_tab and status == STATUS_PENDING:
                b1, b2, _ = st.columns([2, 2, 6])
                with b1:
                    if st.button("✅ Approve Application", key=f"appr_{app_id}_{idx}", use_container_width=True):
                        engine.approval_manager.approve(app_id, engine)
                        st.success("Promoted to Application Engine!")
                        st.rerun()
                with b2:
                    if st.button("🚫 Reject Application", key=f"rej_{app_id}_{idx}", use_container_width=True):
                        engine.approval_manager.reject(app_id)
                        st.error("Rejected! Blocked from engine.")
                        st.rerun()
            elif section_name == "Applications":
                b1, b2, b3 = st.columns([2, 2, 2])
                with b1:
                    if status == "READY":
                        if st.button("🚀 Simulate DRY_RUN", key=f"dry_{app_id}_{idx}"):
                            res = engine.submit_application(app_id, dry_run=True)
                            st.success(f"[DRY_RUN]: {res.get('label', 'Simulated submission step only.')}")
                    if st.button("Mark Submitted (Manual)", key=f"sub_{app_id}_{idx}"):
                        engine.update_application_status(app_id, APP_STATE_SUBMITTED)
                        st.rerun()
                with b2:
                    if status == APP_STATE_SUBMITTED:
                        if st.button("Mark Work Accepted", key=f"acc_{app_id}_{idx}"):
                            engine.update_application_status(app_id, "ACCEPTED")
                            st.rerun()
            elif section_name == "Accepted Work":
                if st.button("🏁 Mark Work Completed", key=f"comp_{app_id}_{idx}"):
                    engine.update_application_status(app_id, "COMPLETED")
                    st.rerun()
            elif section_name in ["Work Completed", "Pending Payments"]:
                if item.get("payment_status") != PAYMENT_CONFIRMED:
                    amt = st.number_input("Actual Amount Received", value=float(item.get("reward") or 0.0), key=f"amt_{app_id}_{idx}")
                    tx_ev = st.text_input("Transaction Evidence / Hash:", value="0x_manual_verified_hash", key=f"tx_{app_id}_{idx}")
                    if st.button("Confirm Payment Received", key=f"pay_{app_id}_{idx}"):
                        engine.mark_payment_confirmed(app_id, amt, tx_ev)
                        st.success("Payment confirmed! Confirmed Earnings updated.")
                        st.rerun()

with tab1:
    st.subheader("1. 🆕 New & Discovered Opportunities")
    render_items(sections["New Opportunities"], "New Opportunities")

with tab2:
    st.subheader("2. 🔔 Opportunities Pending Approval")
    render_items(sections["Pending Approval"], "Pending Approval", is_approval_tab=True)

with tab3:
    st.subheader("3. 📝 Active & Ready Applications")
    render_items(sections["Applications"], "Applications")

with tab4:
    st.subheader("4. 🤝 Accepted Work in Progress")
    render_items(sections["Accepted Work"], "Accepted Work")

with tab5:
    st.subheader("5. 🏁 Work Completed (Awaiting Payment Verification)")
    render_items(sections["Work Completed"], "Work Completed")

with tab6:
    st.subheader("6. ⏳ Pending & Unconfirmed Payments")
    render_items(sections["Pending Payments"], "Pending Payments")

with tab7:
    st.subheader("7. 💵 Confirmed Verified Earnings")
    render_items(sections["Confirmed Earnings"], "Confirmed Earnings")
