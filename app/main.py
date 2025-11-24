from fastapi import FastAPI, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime

from .models import SetGoalRequest, AddTransactionRequest
from .storage import (
    USERS,
    add_transaction,
    update_goal,
    get_user,
    get_user_transactions,
)
from .telegram import send_telegram_text

app = FastAPI(title="Anya – Shopping Guardian (MVP)")

# Allow all origins for now (for testing from browser / tools)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------- Helper functions for evaluation ----------

def calc_month_nonessential_spend(user_id: str) -> float:
    """
    Calculate this month's total non-essential spend (shopping, food, entertainment)
    for the given user.
    """
    txs = get_user_transactions(user_id)
    now = datetime.utcnow()
    month_start = datetime(year=now.year, month=now.month, day=1)

    total = 0.0
    for tx in txs:
        if tx["timestamp"] >= month_start and tx["category"] in ("shopping", "food", "entertainment"):
            total += float(tx["amount"])
    return total


def evaluate_purchase(user: dict, tx: dict, month_spend_nonessential_before: float):
    """
    Decide if the purchase is OK / borderline / hurting the goal.

    Returns:
      verdict: "GREEN" | "ORANGE" | "RED"
      label: short text
      remaining_after: remaining non-essential budget after this purchase
    """
    nonessential_budget = user["month_nonessential_budget"]
    remaining_before = nonessential_budget - month_spend_nonessential_before
    remaining_after = remaining_before - tx["amount"]

    # Simple rules for demo:
    # - GREEN: comfortably above 50% of saving goal left in budget after this purchase
    # - ORANGE: still positive budget, but below that comfort zone
    # - RED: negative budget -> this is hurting the saving goal
    if remaining_after >= user["month_saving_goal"] * 0.5:
        verdict = "GREEN"
        label = "probably okay for your saving goal"
    elif remaining_after >= 0:
        verdict = "ORANGE"
        label = "borderline for your saving goal"
    else:
        verdict = "RED"
        label = "hurting your saving goal this month"

    return verdict, label, remaining_after


def build_verdict_message(user: dict, tx: dict, verdict: str, label: str, remaining_after: float) -> str:
    """
    Create the text you will send on Telegram.
    """
    emoji_map = {"GREEN": "🟢", "ORANGE": "🟠", "RED": "🔴"}
    emoji = emoji_map.get(verdict, "⚪")

    month_goal = user["month_saving_goal"]
    text = (
        f"{emoji} You just spent ₹{tx['amount']} on {tx['merchant']}.\n"
        f"This month you want to save ₹{month_goal}.\n"
        f"Based on your current spending, this purchase is {label}.\n\n"
        f"Approx. non-essential budget left this month after this: ₹{max(remaining_after, 0):.0f}.\n"
        "If you want, we can adjust something else to keep you on track. 💸"
    )
    return text


# -------------------- Routes --------------------

@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/set-goal")
def set_goal(body: SetGoalRequest):
    """
    Set the user's monthly saving goal and non-essential budget.
    This is the 'initially feed some goals' step.
    """
    user = update_goal(
        user_id=body.user_id,
        saving_goal=body.month_saving_goal,
        nonessential_budget=body.month_nonessential_budget,
    )
    return {
        "message": "Goals updated",
        "user": user,
    }


@app.post("/add-transaction")
def add_tx(body: AddTransactionRequest, background_tasks: BackgroundTasks):
    """
    Simulate spending on a shopping app.
    This will:
      1) Record the transaction
      2) Calculate current month non-essential spend
      3) Evaluate if this purchase aligns with the saving goal
      4) Return a verdict + send a Telegram message
    """
    user = get_user(body.user_id)
    if not user:
        return {"ok": False, "error": "User not found"}

    # 1) Save the transaction
    tx = add_transaction(
        user_id=body.user_id,
        amount=body.amount,
        merchant=body.merchant,
        category=body.category,
    )

    # 2) Calculate month non-essential spend *before* this new tx
    month_spend_total = calc_month_nonessential_spend(body.user_id)
    month_spend_before = month_spend_total - body.amount

    # 3) Evaluate this purchase
    verdict, label, remaining_after = evaluate_purchase(user, tx, month_spend_before)

    # 4) Build message text
    verdict_message = build_verdict_message(user, tx, verdict, label, remaining_after)

    # 5) Send Telegram message in the background
    background_tasks.add_task(send_telegram_text, verdict_message)

    return {
        "ok": True,
        "transaction": tx,
        "verdict": verdict,                      # "GREEN" / "ORANGE" / "RED"
        "verdict_label": label,                  # human-readable label
        "month_spend_nonessential_before": month_spend_before,
        "remaining_nonessential_budget_after": remaining_after,
        "notification_message": verdict_message,
        "notify_status": "telegram_send_triggered",
    }
