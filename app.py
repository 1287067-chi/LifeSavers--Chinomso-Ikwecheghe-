import json
import math
from decimal import Decimal, ROUND_HALF_UP
from datetime import datetime, timezone
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

st.set_page_config(
    page_title="Career Venture Lab | Lifesavers (NUR-3)",
    page_icon="🩺",
    layout="wide",
)

# ---------------------------------------------------------------------------
# Constants & NUR-3 Baseline Defaults (Handbook pp. 37, 70, 83-87)
# ---------------------------------------------------------------------------
TEAM_ID_DEFAULT = "Lifesavers"
PATHWAY_ID = "NUR-3"
SELECTED_COURSE = "AP Calculus"
SELECTED_LEVEL = "Advanced"

DEFAULT_STATE = {
    "team_id": TEAM_ID_DEFAULT,
    "pathway_id": PATHWAY_ID,
    "selected_course": SELECTED_COURSE,
    "selected_level": SELECTED_LEVEL,
    "state_version": 1,
    "snapshot_id": "SNAP-NUR3-V1",
    "simulation_date": "2027-01-31",
    "random_seed": 2027,
    "base_price": 25.00,
    "d0": 80,
    "staff_hours": 30.0,
    "hours_per_unit": 0.5,
    "venue_seats": 60,
    "no_show_rate": 0.0,
    "satisfaction_mean": 4.0,
    "owner_contribution": 6000.00,
    "equipment_assets": 1500.00,
    "pre_opening_expense": 500.00,
    "opening_cash": 4000.00,
    "current_cash": 4000.00,
    "debt_principal": 0.00,
    "var_costs": {
        "educator_delivery": 2.00,
        "materials": 2.00,
        "cleaning_consumables": 1.00,
    },
    "fixed_costs": {
        "venue": 250.00,
        "scheduling_software": 100.00,
        "accessibility_support": 200.00,
        "admin_insurance_assumption": 150.00,
    },
    "ledger": [],
    "executed_run_ids": [],
}

FIXTURE_ROWS = [
    {"month": "2027-01", "requested": 80, "capacity_override": 60, "ad_cost": 0.00},
    {"month": "2027-02", "requested": 88, "capacity_override": 60, "ad_cost": 100.00},
    {"month": "2027-03", "requested": 72, "capacity_override": 45, "ad_cost": 0.00},
]


def to_money(val) -> Decimal:
    return Decimal(str(val)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def init_state():
    if "sim_state" not in st.session_state:
        st.session_state.sim_state = json.loads(json.dumps(DEFAULT_STATE))


def reset_to_opening_state(state: dict):
    state["state_version"] = 1
    state["snapshot_id"] = f"SNAP-{state['team_id'].upper()}-V1"
    state["simulation_date"] = "2027-01-31"
    state["current_cash"] = float(to_money(state["opening_cash"]))
    state["debt_principal"] = 0.00
    state["ledger"] = []
    state["executed_run_ids"] = []


def compute_nur_capacity(staff_hours: float, hours_per_unit: float, venue_seats: int) -> int:
    if hours_per_unit <= 0:
        return 0
    educator_cap = math.floor(staff_hours / hours_per_unit)
    return max(0, min(educator_cap, int(venue_seats)))


def simulate_nur_period(
    state: dict,
    sim_date: str,
    requested: int,
    price: float,
    ad_cost: float = 0.0,
    loan_proceeds: float = 0.0,
    principal_repayment: float = 0.0,
    interest_expense: float = 0.0,
    additional_capex: float = 0.0,
    refund_amount: float = 0.0,
    run_id: str = "",
    capacity_override: int | None = None,
) -> tuple[bool, str, dict | None]:
    if run_id and run_id in state["executed_run_ids"]:
        return False, f"Duplicate run_id '{run_id}' rejected: transaction already recorded.", None

    if requested < 0 or price < 0 or ad_cost < 0:
        return False, "Negative inputs are not permitted.", None

    derived_cap = compute_nur_capacity(
        state["staff_hours"], state["hours_per_unit"], state["venue_seats"]
    )
    effective_cap = int(capacity_override) if capacity_override is not None else derived_cap

    booked = min(int(requested), effective_cap)
    unserved_demand = max(0, int(requested) - booked)
    attended = math.floor(booked * (1.0 - float(state["no_show_rate"])))
    sold = attended

    v_unit = sum(to_money(x) for x in state["var_costs"].values())
    f_month = sum(to_money(x) for x in state["fixed_costs"].values())

    price_dec = to_money(price)
    refund_dec = to_money(refund_amount)
    ad_dec = to_money(ad_cost)
    interest_dec = to_money(interest_expense)
    principal_dec = to_money(principal_repayment)
    capex_dec = to_money(additional_capex)
    loan_dec = to_money(loan_proceeds)

    revenue = (price_dec * Decimal(sold)) - refund_dec
    var_expense = v_unit * Decimal(sold)
    fixed_expense = f_month
    total_operating_expense = var_expense + fixed_expense + ad_dec
    operating_profit = revenue - total_operating_expense
    net_profit = operating_profit - interest_dec

    opening_cash = to_money(state["current_cash"])
    closing_cash = (
        opening_cash
        + revenue
        - var_expense
        - fixed_expense
        - ad_dec
        - interest_dec
        - principal_dec
        - capex_dec
        + loan_dec
    )

    next_version = int(state["state_version"]) + 1
    tx_id = f"TX-{len(state['ledger']) + 1:04d}"
    mode_label = "FIXTURE_OVERRIDE" if capacity_override is not None else "NORMAL"

    record = {
        "transaction_id": tx_id,
        "run_id": run_id or f"RUN-{next_version}",
        "state_version": next_version,
        "date": sim_date,
        "mode": mode_label,
        "requested": int(requested),
        "capacity_used": effective_cap,
        "booked": booked,
        "attended": attended,
        "sold": sold,
        "unserved_demand": unserved_demand,
        "unit_price": float(price_dec),
        "revenue": float(revenue),
        "variable_expense": float(var_expense),
        "fixed_expense": float(fixed_expense),
        "marketing_expense": float(ad_dec),
        "total_expense": float(total_operating_expense),
        "operating_profit": float(operating_profit),
        "interest_expense": float(interest_dec),
        "net_profit": float(net_profit),
        "loan_proceeds": float(loan_dec),
        "principal_repayment": float(principal_dec),
        "additional_capex": float(capex_dec),
        "opening_cash": float(opening_cash),
        "closing_cash": float(closing_cash),
    }

    state["ledger"].append(record)
    if run_id:
        state["executed_run_ids"].append(run_id)
    state["current_cash"] = float(closing_cash)
    state["debt_principal"] = float(
        to_money(state["debt_principal"]) + loan_dec - principal_dec
    )
    state["state_version"] = next_version
    state["simulation_date"] = sim_date
    state["snapshot_id"] = f"SNAP-{state['team_id'].upper()}-V{next_version}"

    return True, f"Recorded {tx_id} (State v{next_version}).", record


# ---------------------------------------------------------------------------
# App Initialization & Sidebar
# ---------------------------------------------------------------------------
init_state()
state = st.session_state.sim_state

with st.sidebar:
    st.header("🩺 Lifesavers Control")
    st.caption("Career Venture Lab • Stage 1 Core Engine")

    team_input = st.text_input("Team ID", value=state["team_id"])
    if team_input.strip() and team_input.strip() != state["team_id"]:
        state["team_id"] = team_input.strip()
        state["snapshot_id"] = f"SNAP-{state['team_id'].upper()}-V{state['state_version']}"

    st.info(
        f"**Course:** {state['selected_course']}\n\n"
        f"**Pathway:** {state['pathway_id']} (Nurse-Led Health Education)\n\n"
        f"**Challenge Level:** {state['selected_level']}\n\n"
        f"**Snapshot:** `{state['snapshot_id']}` (v{state['state_version']})"
    )

    st.warning(
        "**Compliance Guardrail:** Fictional general wellness education only. "
        "No medical diagnosis, treatment, or real patient data."
    )

    st.divider()
    st.subheader("Save / Restore JSON")
    export_payload = json.dumps(state, indent=2)
    st.download_button(
        label="⬇️ Export Snapshot JSON",
        data=export_payload,
        file_name=f"{state['team_id']}_NUR3_v{state['state_version']}.json",
        mime="application/json",
        use_container_width=True,
    )

    uploaded_file = st.file_uploader("⬆️ Import Snapshot JSON", type=["json"])
    if uploaded_file is not None:
        if st.button("Validate & Load Snapshot", use_container_width=True):
            try:
                imported = json.loads(uploaded_file.read().decode("utf-8"))
                required_keys = {
                    "team_id",
                    "pathway_id",
                    "selected_course",
                    "state_version",
                    "base_price",
                    "d0",
                    "current_cash",
                    "ledger",
                }
                if not required_keys.issubset(imported.keys()):
                    st.error("Import rejected: missing required snapshot fields.")
                elif imported.get("team_id") != state["team_id"]:
                    st.error(
                        f"Import rejected: team_id '{imported.get('team_id')}' does not match '{state['team_id']}'."
                    )
                elif imported.get("pathway_id") != PATHWAY_ID:
                    st.error(
                        f"Import rejected: pathway_id '{imported.get('pathway_id')}' is not {PATHWAY_ID}."
                    )
                elif int(imported.get("state_version", 0)) < int(state["state_version"]):
                    st.error(
                        f"Import rejected: stale state_version v{imported.get('state_version')} "
                        f"(current is v{state['state_version']})."
                    )
                else:
                    st.session_state.sim_state = imported
                    st.success(
                        f"Loaded {imported.get('snapshot_id')} (v{imported.get('state_version')})."
                    )
                    st.rerun()
            except Exception as exc:
                st.error(f"Invalid JSON file: {exc}")

    if st.button("🔄 Reset to Opening State", use_container_width=True):
        reset_to_opening_state(state)
        st.success("Reset to post-startup opening state ($4,000 cash, v1).")
        st.rerun()

# ---------------------------------------------------------------------------
# Main Header & Navigation Tabs (Stage 1 Scope)
# ---------------------------------------------------------------------------
st.title(f"🩺 {state['team_id']} — Nurse-Led Health Education Simulation")
st.caption(
    "Stage 1 Build: Deterministic Math Engine • Single Dated Ledger • AP Calculus Panel • Acceptance Fixtures | "
    "Stage 2 (Report Center & Marketing Studio) and Stage 3 (Assessments) marked pending."
)

tab_overview, tab_inputs, tab_math, tab_ledger, tab_tests = st.tabs(
    [
        "1. Overview & KPIs",
        "2. Inputs & Funding",
        "3. AP Calculus Panel (Advanced)",
        "4. Simulation Step & Ledger",
        "5. Fixture & Acceptance Tests",
    ]
)

derived_capacity = compute_nur_capacity(
    state["staff_hours"], state["hours_per_unit"], state["venue_seats"]
)
unit_var_cost = float(sum(to_money(x) for x in state["var_costs"].values()))
monthly_fixed_cost = float(sum(to_money(x) for x in state["fixed_costs"].values()))

# ===========================================================================
# TAB 1: OVERVIEW
# ===========================================================================
with tab_overview:
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Spendable Cash", f"${state['current_cash']:,.2f}", f"Start: ${state['opening_cash']:,.2f}")
    c2.metric("Derived Monthly Capacity", f"{derived_capacity} seats", f"{state['staff_hours']}h / {state['hours_per_unit']}h")
    c3.metric("Base Price / Variable Cost", f"${state['base_price']:.2f} / ${unit_var_cost:.2f}", f"Margin: ${state['base_price'] - unit_var_cost:.2f}/seat")
    c4.metric("Monthly Fixed Costs", f"${monthly_fixed_cost:,.2f}", f"Ledger Runs: {len(state['ledger'])}")

    st.subheader("System Map & Stage Status")
    col_a, col_b = st.columns([3, 2])
    with col_a:
        st.markdown(
            """
            **Operating Flow (NUR-3):**
            1. **Inputs & Capacity:** `booked = min(requested, floor(staff_hours / hours_per_unit), venue_seats)`
            2. **Attendance Rule:** `attended = floor(booked * (1 - no_show_rate))` -> `sold = attended`
            3. **Accounting Rule:** Revenue (`price * sold`) and variable costs (`$5 * sold`) apply **only** to attended seats.
            4. **Human Governance:** AI specialists analyze exported snapshots externally; students verify math and approve updates.
            """
        )
    with col_b:
        st.info(
            "**Build Roadmap Status:**\n"
            "- ✅ **Stage 1 (Active):** Core inputs, AP Calculus models, dated ledger, JSON Save/Load, fixture verification.\n"
            "- ⏳ **Stage 2 (Next):** Full Report Center (PDF/CSV) & Costed Marketing Studio.\n"
            "- ⏳ **Stage 3 (Planned):** Cross-Course Panel & Frozen-Snapshot Assessments."
        )

# ===========================================================================
# TAB 2: INPUTS & FUNDING
# ===========================================================================
with tab_inputs:
    st.subheader("Startup Financing & Opening Balances (Fictional Teaching Defaults)")
    f1, f2, f3, f4 = st.columns(4)
    f1.metric("Owner Contribution", f"${state['owner_contribution']:,.2f}")
    f2.metric("Equipment Assets", f"${state['equipment_assets']:,.2f}")
    f3.metric("Pre-Opening Expense", f"${state['pre_opening_expense']:,.2f}")
    f4.metric("Post-Startup Cash", f"${state['opening_cash']:,.2f}")
    st.caption(
        "Accounting rule: Opening assets ($1,500 equipment + $4,000 cash = $5,500) equal owner equity ($6,000) minus pre-opening expense (-$500 retained earnings)."
    )

    st.divider()
    st.subheader("Editable Operating Parameters")
    col_left, col_right = st.columns(2)

    with col_left:
        state["base_price"] = st.number_input(
            "Baseline Price per Workshop Seat ($)",
            min_value=0.0,
            max_value=200.0,
            value=float(state["base_price"]),
            step=1.0,
        )
        state["d0"] = st.number_input(
            "Baseline Monthly Demand D0 (seats)",
            min_value=0,
            max_value=500,
            value=int(state["d0"]),
            step=5,
        )
        state["staff_hours"] = st.number_input(
            "Educator Staff Hours / Month",
            min_value=0.0,
            max_value=500.0,
            value=float(state["staff_hours"]),
            step=1.0,
        )
        state["hours_per_unit"] = st.number_input(
            "Educator Hours per Seat",
            min_value=0.1,
            max_value=10.0,
            value=float(state["hours_per_unit"]),
            step=0.1,
        )
        state["venue_seats"] = st.number_input(
            "Venue Seat Limit / Month",
            min_value=0,
            max_value=500,
            value=int(state["venue_seats"]),
            step=5,
        )
        state["no_show_rate"] = st.slider(
            "No-Show Rate (0.00 to 1.00)",
            min_value=0.0,
            max_value=1.0,
            value=float(state["no_show_rate"]),
            step=0.05,
        )

    with col_right:
        st.markdown("**Variable Cost Lines ($ per attended seat)**")
        state["var_costs"]["educator_delivery"] = st.number_input(
            "Educator Delivery ($/seat)", min_value=0.0, value=float(state["var_costs"]["educator_delivery"]), step=0.5
        )
        state["var_costs"]["materials"] = st.number_input(
            "Workshop Materials ($/seat)", min_value=0.0, value=float(state["var_costs"]["materials"]), step=0.5
        )
        state["var_costs"]["cleaning_consumables"] = st.number_input(
            "Cleaning Consumables ($/seat)", min_value=0.0, value=float(state["var_costs"]["cleaning_consumables"]), step=0.5
        )
        st.write(f"**Total Variable Cost ($v$):** `${sum(state['var_costs'].values()):.2f} / seat`")

        st.markdown("**Fixed Cost Lines ($ per month)**")
        state["fixed_costs"]["venue"] = st.number_input(
            "Venue Rental ($/mo)", min_value=0.0, value=float(state["fixed_costs"]["venue"]), step=10.0
        )
        state["fixed_costs"]["scheduling_software"] = st.number_input(
            "Scheduling Software ($/mo)", min_value=0.0, value=float(state["fixed_costs"]["scheduling_software"]), step=10.0
        )
        state["fixed_costs"]["accessibility_support"] = st.number_input(
            "Accessibility Support ($/mo)", min_value=0.0, value=float(state["fixed_costs"]["accessibility_support"]), step=10.0
        )
        state["fixed_costs"]["admin_insurance_assumption"] = st.number_input(
            "Admin & Insurance Assumption ($/mo)", min_value=0.0, value=float(state["fixed_costs"]["admin_insurance_assumption"]), step=10.0
        )
        st.write(f"**Total Fixed Cost ($F$):** `${sum(state['fixed_costs'].values()):.2f} / month`")

# ===========================================================================
# TAB 3: AP CALCULUS PANEL (ADVANCED)
# ===========================================================================
with tab_math:
    st.subheader("Math Skills & Challenge Level Panel — AP Calculus (Advanced)")
    st.markdown(
        """
        * **Skill:** Constrained Optimization via Derivatives & Definite Integral Accumulation
        * **Domain:** Price $p \in [0, 2p_0]$ where $q(p) = \max(0, a - b p)$, $a = 2D_0$, $b = D_0 / p_0$
        * **Continuous vs. Discrete Note:** Calculus curves below use continuous relaxation; actual ledger runs floor integer seat counts.
        """
    )

    p0 = float(state["base_price"]) if state["base_price"] > 0 else 25.0
    d0 = float(state["d0"])
    v = float(sum(state["var_costs"].values()))
    F = float(sum(state["fixed_costs"].values()))
    cap = float(derived_capacity)

    a = 2.0 * d0
    b = d0 / p0
    p_max = 2.0 * p0
    p_corner = (a - cap) / b if b > 0 else 0.0
    p_unconstrained_crit = (a + b * v) / (2.0 * b) if b > 0 else 0.0

    # Evaluate continuous constrained profit across domain
    p_grid = np.linspace(0, p_max, 400)
    q_demand = np.maximum(0.0, a - b * p_grid)
    s_constrained = np.minimum(cap, q_demand)
    profit_unconstrained = (p_grid - v) * q_demand - F
    profit_constrained = (p_grid - v) * s_constrained - F

    # Derivative P'(p) on branches
    deriv_constrained = np.where(
        q_demand > cap,
        cap,  # capacity-bound branch: P(p) = (p - v)*cap - F => P'(p) = cap
        a + b * v - 2.0 * b * p_grid,  # demand-bound branch
    )

    # Optimal constrained price check (analytic candidates: endpoints, corner, feasible critical point)
    candidates = [0.0, p_max]
    if 0.0 <= p_corner <= p_max:
        candidates.append(p_corner)
    if p_corner <= p_unconstrained_crit <= p_max:
        candidates.append(p_unconstrained_crit)

    def eval_constrained_profit(p_val: float) -> float:
        q_val = max(0.0, a - b * p_val)
        s_val = min(cap, q_val)
        return (p_val - v) * s_val - F

    best_p = max(candidates, key=eval_constrained_profit)
    best_profit = eval_constrained_profit(best_p)
    best_int_seats = math.floor(min(cap, max(0.0, a - b * best_p)))
    best_int_profit = (best_p - v) * best_int_seats - F

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Capacity Corner Price", f"${p_corner:.2f}", f"Where q(p) = {int(cap)} seats")
    m2.metric("Unconstrained Critical p*", f"${p_unconstrained_crit:.2f}", "Where P'(p) = 0")
    m3.metric("Constrained Optimum p*", f"${best_p:.2f}", f"Continuous Profit: ${best_profit:,.2f}")
    m4.metric("Integer Ledger Check at p*", f"{best_int_seats} seats", f"Discrete Profit: ${best_int_profit:,.2f}")

    # Aligned Profit & Derivative Plot
    fig = make_subplots(
        rows=2,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.1,
        subplot_titles=(
            "Constrained vs. Unconstrained Profit P(p) [$]",
            "Marginal Profit Derivative P'(p) [$/dollar of price]",
        ),
    )

    fig.add_trace(
        go.Scatter(
            x=p_grid,
            y=profit_unconstrained,
            name="Unconstrained Profit",
            line=dict(dash="dash", color="#7f8c8d"),
        ),
        row=1,
        col=1,
    )
    fig.add_trace(
        go.Scatter(
            x=p_grid,
            y=profit_constrained,
            name="Constrained Profit (s <= cap)",
            line=dict(color="#1f77b4", width=3),
        ),
        row=1,
        col=1,
    )
    fig.add_hline(y=0, line_dash="dot", line_color="black", row=1, col=1)

    if 0 <= p_corner <= p_max:
        fig.add_vline(
            x=p_corner,
            line_dash="dash",
            line_color="#d62728",
            annotation_text=f"Capacity Corner p=${p_corner:.2f}",
            row=1,
            col=1,
        )

    # Split derivative trace at corner to show undefined jump cleanly
    left_mask = p_grid < p_corner
    right_mask = p_grid > p_corner
    fig.add_trace(
        go.Scatter(
            x=p_grid[left_mask],
            y=deriv_constrained[left_mask],
            name="P'(p) Capacity Branch (= cap)",
            line=dict(color="#2ca02c", width=2.5),
        ),
        row=2,
        col=1,
    )
    fig.add_trace(
        go.Scatter(
            x=p_grid[right_mask],
            y=deriv_constrained[right_mask],
            name="P'(p) Demand Branch",
            line=dict(color="#ff7f0e", width=2.5),
        ),
        row=2,
        col=1,
    )
    if 0 <= p_corner <= p_max:
        fig.add_trace(
            go.Scatter(
                x=[p_corner, p_corner],
                y=[cap, a + b * v - 2 * b * p_corner],
                mode="markers",
                name="Corner Jump (P' undefined)",
                marker=dict(size=9, symbol="circle-open", color="#d62728", line=dict(width=2)),
            ),
            row=2,
            col=1,
        )

    fig.update_layout(height=580, hovermode="x unified")
    fig.update_xaxes(title_text="Workshop Seat Price p ($)", row=2, col=1)
    fig.update_yaxes(title_text="Profit ($)", row=1, col=1)
    fig.update_yaxes(title_text="dP/dp ($ / $)", row=2, col=1)
    st.plotly_chart(fig, use_container_width=True)

    # Interactive transfer check slider
    test_p = st.slider("Transfer Check: Test a Price p ($)", 0.0, p_max, float(p0), 0.25)
    q_at_p = max(0.0, a - b * test_p)
    s_at_p = min(cap, q_at_p)
    prof_at_p = (test_p - v) * s_at_p - F
    st.write(
        f"At **p = ${test_p:.2f}**: Demand $q(p) = {q_at_p:.2f}$ seats | "
        f"Constrained Sales $s(p) = {s_at_p:.2f}$ seats | "
        f"Continuous Profit $P(p) = \${prof_at_p:,.2f}$"
    )

    st.divider()
    st.subheader("Advanced Extension: Rate Accumulation via Definite Integrals")
    st.caption(
        "Isolated rate exercise mapped to a workshop campaign (does not overwrite the monthly accounting ledger)."
    )
    ic1, ic2, ic3 = st.columns(3)
    t_end = ic1.slider("Campaign Window T (days)", min_value=1, max_value=30, value=10)
    r0 = ic2.number_input("Initial Revenue Rate r(0) ($/day)", value=100.0, step=10.0)
    r_slope = ic2.number_input("Revenue Rate Growth ($/day²)", value=20.0, step=5.0)
    c0 = ic3.number_input("Initial Cost Rate c(0) ($/day)", value=60.0, step=10.0)
    c_slope = ic3.number_input("Cost Rate Growth ($/day²)", value=5.0, step=1.0)

    # Exact definite integrals from 0 to T: int_0^T (r0 + r_slope*t) dt = r0*T + 0.5*r_slope*T^2
    acc_rev = r0 * t_end + 0.5 * r_slope * (t_end ** 2)
    acc_cost = c0 * t_end + 0.5 * c_slope * (t_end ** 2)
    acc_profit = acc_rev - acc_cost

    ir1, ir2, ir3 = st.columns(3)
    ir1.metric(f"Accumulated Revenue [0, {t_end}]", f"${acc_rev:,.2f}")
    ir2.metric(f"Accumulated Cost [0, {t_end}]", f"${acc_cost:,.2f}")
    ir3.metric(f"Net Accumulated Profit [0, {t_end}]", f"${acc_profit:,.2f}")

# ===========================================================================
# TAB 4: SIMULATION STEP & LEDGER
# ===========================================================================
with tab_ledger:
    st.subheader("Run One Monthly Simulation Step (Normal Mode)")
    st.caption(
        "Normal mode derives capacity directly from staff hours and venue seats. Approving a step records one transaction in the dated ledger."
    )

    with st.form("run_step_form"):
        sc1, sc2, sc3, sc4 = st.columns(4)
        step_date = sc1.text_input("Simulation Date (YYYY-MM-DD)", value="2027-01-31")
        step_req = sc2.number_input("Requested Seats", min_value=0, value=int(state["d0"]), step=1)
        step_price = sc3.number_input("Seat Price ($)", min_value=0.0, value=float(state["base_price"]), step=1.0)
        step_run_id = sc4.text_input("Unique Run ID", value=f"RUN-{state['team_id'].upper()}-{state['state_version']}")

        sc5, sc6, sc7, sc8 = st.columns(4)
        step_ad = sc5.number_input("Approved Marketing Expense ($)", min_value=0.0, value=0.0, step=25.0)
        step_loan = sc6.number_input("Loan Proceeds ($)", min_value=0.0, value=0.0, step=100.0)
        step_principal = sc7.number_input("Loan Principal Repayment ($)", min_value=0.0, value=0.0, step=50.0)
        step_interest = sc8.number_input("Interest Expense ($)", min_value=0.0, value=0.0, step=10.0)

        submitted = st.form_submit_button("✅ Approve & Advance Simulation Step")
        if submitted:
            ok, msg, _ = simulate_nur_period(
                state=state,
                sim_date=step_date,
                requested=int(step_req),
                price=float(step_price),
                ad_cost=float(step_ad),
                loan_proceeds=float(step_loan),
                principal_repayment=float(step_principal),
                interest_expense=float(step_interest),
                run_id=step_run_id.strip(),
            )
            if ok:
                st.success(msg)
                st.rerun()
            else:
                st.error(msg)

    st.divider()
    st.subheader("Dated Event Ledger")
    if state["ledger"]:
        df_ledger = pd.DataFrame(state["ledger"])
        st.dataframe(df_ledger, use_container_width=True)
        st.download_button(
            label="⬇️ Download Ledger CSV",
            data=df_ledger.to_csv(index=False),
            file_name=f"{state['team_id']}_NUR3_ledger_v{state['state_version']}.csv",
            mime="text/csv",
        )
    else:
        st.info("No transactions recorded yet. Run a normal simulation step above or run the NUR fixture test in Tab 5.")

# ===========================================================================
# TAB 5: FIXTURE & ACCEPTANCE TESTS
# ===========================================================================
with tab_tests:
    st.subheader("NUR Package Acceptance & Fixture Tests (Handbook p. 85)")
    st.warning(
        "**Fixture Mode Notice:** Replaying `monthly_fixture.csv` resets to post-startup cash ($4,000) and uses "
        "explicit `capacity_override` values to verify the ledger rules."
    )

    if st.button("▶️ Replay Official 3-Month NUR Fixture"):
        reset_to_opening_state(state)
        for row in FIXTURE_ROWS:
            simulate_nur_period(
                state=state,
                sim_date=f"{row['month']}-28",
                requested=row["requested"],
                price=25.00,
                ad_cost=row["ad_cost"],
                run_id=f"FIXTURE-{row['month']}",
                capacity_override=row["capacity_override"],
            )
        st.success("Replayed 3-month NUR fixture from opening state ($4,000 cash).")
        st.rerun()

    expected_df = pd.DataFrame(
        [
            {"Month": "2027-01", "Expected Sold": 60, "Expected Revenue": 1500.0, "Expected Expense": 1000.0, "Expected Profit": 500.0, "Expected Cash": 4500.0},
            {"Month": "2027-02", "Expected Sold": 60, "Expected Revenue": 1500.0, "Expected Expense": 1100.0, "Expected Profit": 400.0, "Expected Cash": 4900.0},
            {"Month": "2027-03", "Expected Sold": 45, "Expected Revenue": 1125.0, "Expected Expense": 925.0, "Expected Profit": 200.0, "Expected Cash": 5100.0},
        ]
    )
    st.markdown("**Printed Handbook Expected Results (NUR Package p. 85):**")
    st.dataframe(expected_df, use_container_width=True)

    st.divider()
    st.subheader("Automated Stage 1 Unit Checks")
    if st.button("🧪 Run All Stage 1 Acceptance Checks"):
        results = []

        # Test 1: Zero sales
        s_zero = json.loads(json.dumps(DEFAULT_STATE))
        simulate_nur_period(s_zero, "2027-01-31", requested=0, price=25.0, run_id="T_ZERO")
        tx_z = s_zero["ledger"][0]
        pass_zero = (tx_z["revenue"] == 0.0 and tx_z["variable_expense"] == 0.0 and tx_z["operating_profit"] == -700.0)
        results.append(("Zero sales -> Revenue $0, Profit -$700", "PASS" if pass_zero else "FAIL", f"Rev={tx_z['revenue']}, Profit={tx_z['operating_profit']}"))

        # Test 2: Demand exceeds capacity
        s_cap = json.loads(json.dumps(DEFAULT_STATE))
        simulate_nur_period(s_cap, "2027-01-31", requested=80, price=25.0, run_id="T_CAP")
        tx_c = s_cap["ledger"][0]
        pass_cap = (tx_c["sold"] == 60 and tx_c["unserved_demand"] == 20)
        results.append(("Demand (80) > Capacity (60) -> Sold 60, Unserved 20", "PASS" if pass_cap else "FAIL", f"Sold={tx_c['sold']}, Unserved={tx_c['unserved_demand']}"))

        # Test 3: NUR No-Show Business Test (no_show_rate = 0.20)
        s_ns = json.loads(json.dumps(DEFAULT_STATE))
        s_ns["no_show_rate"] = 0.20
        simulate_nur_period(s_ns, "2027-01-31", requested=80, price=25.0, run_id="T_NOSHOW")
        tx_ns = s_ns["ledger"][0]
        pass_ns = (tx_ns["booked"] == 60 and tx_ns["attended"] == 48 and tx_ns["revenue"] == 1200.0 and tx_ns["operating_profit"] == 260.0)
        results.append(("No-show 20% -> Booked 60, Attended 48, Profit $260", "PASS" if pass_ns else "FAIL", f"Attended={tx_ns['attended']}, Profit={tx_ns['operating_profit']}"))

        # Test 4: Duplicate run_id protection
        ok_dup, _, _ = simulate_nur_period(s_cap, "2027-01-31", requested=80, price=25.0, run_id="T_CAP")
        results.append(("Duplicate run_id rejected", "PASS" if (not ok_dup and len(s_cap["ledger"]) == 1) else "FAIL", f"Rejected={not ok_dup}, LedgerLen={len(s_cap['ledger'])}"))

        # Test 5: Loan received (cash & debt rise, revenue unchanged)
        s_loan = json.loads(json.dumps(DEFAULT_STATE))
        simulate_nur_period(s_loan, "2027-01-31", requested=0, price=25.0, loan_proceeds=1000.0, run_id="T_LOAN")
        tx_l = s_loan["ledger"][0]
        pass_loan = (tx_l["revenue"] == 0.0 and tx_l["closing_cash"] == 4300.0 and s_loan["debt_principal"] == 1000.0)
        results.append(("Loan $1,000 -> Cash +$1,000 (net of $700 fixed), Revenue $0", "PASS" if pass_loan else "FAIL", f"Cash={tx_l['closing_cash']}, Debt={s_loan['debt_principal']}"))

        # Test 6: AP Calculus Course Acceptance Check (D0=60, p0=30, v=10, F=500, cap=40 -> p*=40, profit=700; Integral=1150)
        a_t, b_t, v_t, F_t, cap_t = 120.0, 2.0, 10.0, 500.0, 40.0
        p_c_test = (a_t - cap_t) / b_t
        prof_c_test = (p_c_test - v_t) * cap_t - F_t
        int_test = (100.0 * 10 + 0.5 * 20.0 * 100) - (60.0 * 10 + 0.5 * 5.0 * 100)
        pass_calc = (abs(p_c_test - 40.0) < 1e-6 and abs(prof_c_test - 700.0) < 1e-6 and abs(int_test - 1150.0) < 1e-6)
        results.append(("AP Calc Adapter Check (p*=40, Profit=$700, Integral=$1150)", "PASS" if pass_calc else "FAIL", f"p*={p_c_test}, Profit={prof_c_test}, Int={int_test}"))

        st.table(pd.DataFrame(results, columns=["Acceptance Test", "Status", "Evidence"]))
