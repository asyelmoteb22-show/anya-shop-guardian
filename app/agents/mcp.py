"""MCP (Model-Context-Protocol) Agent - Observe → Reason → Act."""

from typing import Dict, Any, Optional, List
from groq import Groq
from sqlalchemy.orm import Session

from app.config import settings
from app.agents.prompts import (
    FINANCIAL_ADVISOR_SYSTEM_PROMPT,
    GOAL_SETTING_PROMPT,
    SPENDING_ANALYSIS_PROMPT,
    BEHAVIORAL_NUDGE_PROMPT
)
from app.agents.tools import AgentTools
from app.messaging.session_manager import session_manager


class MCPAgent:
    """
    MCP Agent orchestrates the Observe → Reason → Act cycle.
    
    - Observe: Gather context (user message, goals, spending, history)
    - Reason: Use LLM to understand intent and plan response
    - Act: Execute tools and generate response
    """
    
    def __init__(self, db: Session, user_id: str):
        """
        Initialize MCP agent.
        
        Args:
            db: Database session
            user_id: Telegram user ID
        """
        self.db = db
        self.user_id = user_id
        self.tools = AgentTools(db, user_id)
        
        # Initialize Groq client
        if settings.groq_api_key:
            self.client = Groq(api_key=settings.groq_api_key)
        else:
            self.client = None
            print("⚠️  GROQ_API_KEY not configured - agent will use fallback responses")
    
    def observe(self, user_message: str) -> Dict[str, Any]:
        """
        Observe: Gather all relevant context.
        
        Args:
            user_message: User's message
            
        Returns:
            Context dictionary
        """
        # Get conversation history
        history = session_manager.get_history(self.user_id, limit=5)
        
        # Get active goals
        goals = self.tools.get_active_goals()
        
        # Get spending status
        budget_status = self.tools.check_budget_status()
        
        # Get conversation state
        state = session_manager.get_conversation_state(self.user_id)
        
        return {
            "user_message": user_message,
            "history": history,
            "goals": goals,
            "budget_status": budget_status,
            "conversation_state": state
        }
    
    def reason(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Reason: Use LLM to understand intent and plan response.
        
        Args:
            context: Observed context
            
        Returns:
            Reasoning result with intent and planned actions
        """
        if not self.client:
            return self._fallback_reasoning(context)
        
        # Build messages for LLM
        messages = [
            {"role": "system", "content": FINANCIAL_ADVISOR_SYSTEM_PROMPT}
        ]
        
        # Add conversation history
        for msg in context["history"]:
            messages.append({
                "role": msg["role"],
                "content": msg["content"]
            })
        
        # Add current context as system message
        context_str = self._format_context(context)
        messages.append({
            "role": "system",
            "content": f"Current context:\n{context_str}"
        })
        
        # Add user message
        messages.append({
            "role": "user",
            "content": context["user_message"]
        })
        
        try:
            # Call Groq LLM
            response = self.client.chat.completions.create(
                model=settings.groq_model,
                messages=messages,
                temperature=0.7,
                max_tokens=500
            )
            
            assistant_message = response.choices[0].message.content
            
            # Detect intent from response
            intent = self._detect_intent(context["user_message"], assistant_message)
            
            return {
                "intent": intent,
                "response": assistant_message,
                "actions": []  # Actions will be determined based on intent
            }
        
        except Exception as e:
            print(f"❌ Groq API error: {e}")
            return self._fallback_reasoning(context)
    
    def act(self, reasoning: Dict[str, Any], context: Dict[str, Any]) -> str:
        """
        Act: Execute actions and return final response.
        
        Args:
            reasoning: Reasoning result
            context: Observed context
            
        Returns:
            Final response message
        """
        intent = reasoning["intent"]
        response = reasoning["response"]
        
        # Execute intent-specific actions
        if intent == "set_goal":
            pass
        
        elif intent == "check_status":
            pass
        
        elif intent == "analyze_spending":
            pass
        
        # Store conversation in history
        session_manager.add_to_history(self.user_id, "user", context["user_message"])
        session_manager.add_to_history(self.user_id, "assistant", response)
        
        return response
    
    def process_message(self, user_message: str) -> str:
        """
        Main entry point: Process a user message through the MCP cycle.
        
        Args:
            user_message: User's message
            
        Returns:
            Agent's response
        """
        # Observe
        context = self.observe(user_message)
        
        # Reason
        reasoning = self.reason(context)
        
        # Act
        response = self.act(reasoning, context)
        
        return response
    
    def _format_context(self, context: Dict[str, Any]) -> str:
        """Format context for LLM."""
        parts = []
        
        # Goals
        if context["goals"]:
            goals_str = "\n".join([
                f"- {g['title']}: ₹{g['current_amount']:.0f} / ₹{g['target_amount']:.0f} ({g['progress_percentage']:.0f}%)"
                for g in context["goals"]
            ])
            parts.append(f"Active Goals:\n{goals_str}")
        else:
            parts.append("No active goals set.")
        
        # Budget status
        budget = context["budget_status"]
        if budget["verdict"] != "NO_GOAL":
            parts.append(
                f"\nBudget Status: {budget['verdict']} ({budget['label']})\n"
                f"Spent: ₹{budget['total_spent']:.0f} / ₹{budget['budget']:.0f}\n"
                f"Remaining: ₹{budget['remaining']:.0f}"
            )
        
        return "\n\n".join(parts)
    
    def _detect_intent(self, user_message: str, assistant_response: str) -> str:
        """Detect user intent from message and response."""
        user_lower = user_message.lower()
        
        # Simple keyword-based intent detection
        if any(word in user_lower for word in ["goal", "save", "want to buy", "planning"]):
            return "set_goal"
        elif any(word in user_lower for word in ["status", "how am i", "progress", "doing"]):
            return "check_status"
        elif any(word in user_lower for word in ["spent", "spending", "budget", "transactions"]):
            return "analyze_spending"
        else:
            return "general_chat"
    
    def _fallback_reasoning(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Fallback reasoning when Groq is not available."""
        user_message = context["user_message"].lower()
        
        # Simple rule-based responses
        if "goal" in user_message or "save" in user_message:
            response = "I'd love to help you set a goal! What are you saving for? 🎯"
            intent = "set_goal"
        
        elif "status" in user_message or "progress" in user_message:
            budget = context["budget_status"]
            if budget["verdict"] != "NO_GOAL":
                response = (
                    f"You've spent ₹{budget['total_spent']:.0f} out of ₹{budget['budget']:.0f} "
                    f"this month. You have ₹{budget['remaining']:.0f} left! 💰"
                )
            else:
                response = "You haven't set a goal yet. Want to create one? 🎯"
            intent = "check_status"
        
        else:
            response = "I'm here to help you with your financial goals! You can ask me about your spending, set goals, or check your progress. 😊"
            intent = "general_chat"
        
        return {
            "intent": intent,
            "response": response,
            "actions": []
        }
