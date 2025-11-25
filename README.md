# Anya – Shopping Guardian (MVP)

A FastAPI backend that evaluates every shopping transaction and tells the user whether it aligns with their monthly saving goal.

## 🚀 Endpoints
| Method | Route | Description |
|--------|--------|-------------|
| POST | `/set-goal` | Set monthly saving goal and non-essential budget |
| POST | `/add-transaction` | Record a shopping transaction and return a GREEN / ORANGE / RED verdict |

## 🧠 What it does
- User enters a saving goal for the month (₹)
- Every time the user spends on a shopping app, the backend:
  - Records the transaction
  - Compares spending vs saving goal
  - Generates a goal-alignment verdict and message

## 🛠 Tech Stack
- Python
- FastAPI
- Uvicorn
- In-memory storage (for prototype)

## ➡️ Next steps (roadmap)
- Send verdict as automated message to WhatsApp / Telegram
- Add decisions: "Go ahead 👍" / "Pause & save 💰"
- Track money saved over time
