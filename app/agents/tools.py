"""Tool definitions for the MCP agent."""

from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from sqlalchemy.orm import Session

from app.db.models import User, Goal, Transaction, GoalStatus, TransactionCategory
from app.config import settings


class AgentTools:
    """Tools that the MCP agent can use to interact with the system."""
    
    def __init__(self, db: Session, user_id: str):
        """
        Initialize agent tools.
        
        Args:
            db: Database session
            user_id: Telegram user ID
        """
        self.db = db
        self.user_id = user_id
        self.user = self._get_or_create_user()
    
    def _get_or_create_user(self) -> User:
        """Get or create user in database."""
        user = self.db.query(User).filter(User.telegram_id == self.user_id).first()
        if not user:
            user = User(telegram_id=self.user_id)
            self.db.add(user)
            self.db.commit()
            self.db.refresh(user)
        return user
    
    def set_saving_goal(
        self,
        title: str,
        target_amount: float,
        deadline_days: Optional[int] = None,
        month_nonessential_budget: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Create a new saving goal for the user.
        
        Args:
            title: Goal title (e.g., "Buy a laptop")
            target_amount: Target amount in ₹
            deadline_days: Days until deadline (optional)
            month_nonessential_budget: Monthly budget for non-essentials
            
        Returns:
            Goal information dictionary
        """
        deadline = None
        if deadline_days:
            deadline = datetime.utcnow() + timedelta(days=deadline_days)
        
        goal = Goal(
            user_id=self.user.id,
            title=title,
            target_amount=target_amount,
            deadline=deadline,
            month_nonessential_budget=month_nonessential_budget,
            status=GoalStatus.ACTIVE
        )
        
        self.db.add(goal)
        self.db.commit()
        self.db.refresh(goal)
        
        return {
            "goal_id": goal.id,
            "title": goal.title,
            "target_amount": goal.target_amount,
            "deadline": goal.deadline.isoformat() if goal.deadline else None,
            "status": goal.status.value
        }
    
    def get_active_goals(self) -> List[Dict[str, Any]]:
        """
        Get all active goals for the user.
        
        Returns:
            List of goal dictionaries
        """
        goals = self.db.query(Goal).filter(
            Goal.user_id == self.user.id,
            Goal.status == GoalStatus.ACTIVE
        ).all()
        
        return [
            {
                "goal_id": g.id,
                "title": g.title,
                "target_amount": g.target_amount,
                "current_amount": g.current_amount,
                "progress_percentage": g.progress_percentage,
                "deadline": g.deadline.isoformat() if g.deadline else None,
                "month_nonessential_budget": g.month_nonessential_budget
            }
            for g in goals
        ]
    
    def fetch_recent_transactions(self, days: int = 30) -> List[Dict[str, Any]]:
        """
        Fetch recent transactions for the user.
        
        Args:
            days: Number of days to look back
            
        Returns:
            List of transaction dictionaries
        """
        cutoff = datetime.utcnow() - timedelta(days=days)
        
        transactions = self.db.query(Transaction).filter(
            Transaction.user_id == self.user.id,
            Transaction.timestamp >= cutoff
        ).order_by(Transaction.timestamp.desc()).all()
        
        return [
            {
                "transaction_id": t.id,
                "amount": t.amount,
                "merchant": t.merchant,
                "category": t.category.value,
                "timestamp": t.timestamp.isoformat()
            }
            for t in transactions
        ]
    
    def analyze_spending_pattern(self) -> Dict[str, Any]:
        """
        Analyze the user's spending patterns this month.
        
        Returns:
            Spending analysis dictionary
        """
        # Get current month transactions
        now = datetime.utcnow()
        month_start = datetime(year=now.year, month=now.month, day=1)
        
        transactions = self.db.query(Transaction).filter(
            Transaction.user_id == self.user.id,
            Transaction.timestamp >= month_start
        ).all()
        
        # Calculate totals by category
        category_totals = {}
        total_nonessential = 0.0
        
        for tx in transactions:
            category = tx.category.value
            amount = tx.amount
            
            if category not in category_totals:
                category_totals[category] = 0.0
            category_totals[category] += amount
            
            # Non-essential categories
            if category in ["shopping", "food", "entertainment"]:
                total_nonessential += amount
        
        # Get active goal for budget comparison
        active_goal = self.db.query(Goal).filter(
            Goal.user_id == self.user.id,
            Goal.status == GoalStatus.ACTIVE
        ).first()
        
        budget = active_goal.month_nonessential_budget if active_goal else None
        remaining_budget = (budget - total_nonessential) if budget else None
        
        return {
            "total_nonessential": total_nonessential,
            "category_breakdown": category_totals,
            "month_nonessential_budget": budget,
            "remaining_budget": remaining_budget,
            "transaction_count": len(transactions)
        }
    
    def check_budget_status(self) -> Dict[str, Any]:
        """
        Check current budget status against goals.
        
        Returns:
            Budget status dictionary with verdict
        """
        spending = self.analyze_spending_pattern()
        active_goal = self.db.query(Goal).filter(
            Goal.user_id == self.user.id,
            Goal.status == GoalStatus.ACTIVE
        ).first()
        
        if not active_goal:
            return {
                "verdict": "NO_GOAL",
                "message": "No active goal set"
            }
        
        total_spent = spending["total_nonessential"]
        budget = active_goal.month_nonessential_budget or 0
        remaining = budget - total_spent
        saving_goal = active_goal.target_amount
        
        # Determine verdict
        if remaining >= saving_goal * settings.comfort_zone_threshold:
            verdict = "GREEN"
            label = "on track"
        elif remaining >= 0:
            verdict = "ORANGE"
            label = "borderline"
        else:
            verdict = "RED"
            label = "over budget"
        
        return {
            "verdict": verdict,
            "label": label,
            "total_spent": total_spent,
            "budget": budget,
            "remaining": remaining,
            "saving_goal": saving_goal,
            "goal_title": active_goal.title
        }
    
    def add_transaction(
        self,
        amount: float,
        merchant: str,
        category: str = "other"
    ) -> Dict[str, Any]:
        """
        Add a new transaction (for testing/manual entry).
        
        Args:
            amount: Transaction amount
            merchant: Merchant name
            category: Transaction category
            
        Returns:
            Transaction information
        """
        try:
            cat_enum = TransactionCategory[category.upper()]
        except KeyError:
            cat_enum = TransactionCategory.OTHER
        
        transaction = Transaction(
            user_id=self.user.id,
            amount=amount,
            merchant=merchant,
            category=cat_enum
        )
        
        self.db.add(transaction)
        self.db.commit()
        self.db.refresh(transaction)
        
        return {
            "transaction_id": transaction.id,
            "amount": transaction.amount,
            "merchant": transaction.merchant,
            "category": transaction.category.value,
            "timestamp": transaction.timestamp.isoformat()
        }
