import json
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

class LLMEvaluator:
    def __init__(self, groq_client, model: str = "llama-3.3-70b-versatile"):
        self.client = groq_client
        self.model = model

    def evaluate_opportunity(self, opportunity: Dict[str, Any]) -> Dict[str, Any]:
        title = opportunity.get("title", "Untitled")
        description = opportunity.get("description", "")
        reward = opportunity.get("reward")
        currency = opportunity.get("currency", "USD")

        reward_display = "Unknown" if reward is None else f"{reward} {currency}"

        system_prompt = (
            "You are an expert software engineering opportunity evaluator. "
            "Analyze job/bounty postings with high precision. "
            "NEVER invent or assume a reward amount. "
            "If no reward is stated, treat payment as unknown. "
            "DO NOT invent previous clients or experience when generating a proposal."
        )

        user_prompt = f"""
ANALYZE THIS OPPORTUNITY:
Title: {title}
Description: {description}
Source Reward: {reward_display}

REQUIREMENTS:
1. Estimate realistic effort in hours (1-8 hrs for small bugs, 5-20 hrs for API/scripts, 15-40 hrs for modules, 40+ hrs for full systems).
2. Determine technical difficulty (1-10).
3. Estimate success probability (10%-95%).
4. Categorize task type: 'technical', 'human_only', 'design', or 'other'.
5. Decision must be 'SELECT', 'NEEDS_REVIEW', or 'SKIP'.
6. Generate an honest proposal ONLY if SELECT or NEEDS_REVIEW (100-180 words, NO fabricated work experience).
7. NEVER invent a reward. If source reward is unknown, do not assume payment.

Return ONLY JSON:
{{
  "estimated_hours": <float/int>,
  "difficulty": <int 1-10>,
  "success_probability_pct": <int 10-95>,
  "task_category": "<technical|human_only|design|other>",
  "decision": "<SELECT|NEEDS_REVIEW|SKIP>",
  "decision_reason": "<concise explanation>",
  "required_skills": ["<skill1>", "<skill2>"],
  "risks": ["<risk1>", "<risk2>"],
  "proposal": "<honest execution plan or empty string>"
}}
"""

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.2,
                response_format={"type": "json_object"}
            )
            ai_data = json.loads(response.choices[0].message.content)
        except Exception as e:
            logger.error(f"LLM parsing failed: {e}")
            ai_data = {
                "estimated_hours": 10, "difficulty": 5, "success_probability_pct": 50,
                "task_category": "technical", "decision": "NEEDS_REVIEW",
                "decision_reason": f"Parsing Failure: {str(e)}", "required_skills": [],
                "risks": ["Evaluation error"], "__error": str(e)
            }

        est_hours = max(float(ai_data.get("estimated_hours", 10.0)), 1.0)
        difficulty = int(ai_data.get("difficulty", 5))
        success_prob = int(ai_data.get("success_probability_pct", 50))

        decision = ai_data.get("decision", "NEEDS_REVIEW")
        if ai_data.get("task_category") in ["human_only", "design"]:
            decision = "SKIP"
            
        ai_suitable = decision != "SKIP"

        est_reward_per_hour = 0
        if reward is not None and reward > 0:
            est_reward_per_hour = round(reward / est_hours, 2)

        hourly_rate_factor = min(est_reward_per_hour / 100.0, 1.0) * 100.0
        ease_factor = (11 - difficulty) * 10.0
        profit_score = int(round((hourly_rate_factor * 0.35) + (success_prob * 0.35) + (ease_factor * 0.30)))

        # Update the original opportunity data
        opportunity["estimated_hours"] = est_hours
        opportunity["difficulty"] = difficulty
        opportunity["success_probability"] = success_prob
        opportunity["profit_score"] = profit_score
        opportunity["ai_suitable"] = ai_suitable
        opportunity["required_skills"] = ai_data.get("required_skills", [])
        opportunity["evaluation_decision"] = decision
        opportunity["evaluation_reason"] = ai_data.get("decision_reason", "")
        
        prop = ai_data.get("proposal", "")
        error = ai_data.get("__error")
        
        if error:
            opportunity["proposal_status"] = "FAILED"
            opportunity["failure_reason"] = f"LLM parsing failed: {error}"
            opportunity["proposal"] = ""
            opportunity["proposal_exists"] = False
        elif not prop:
            opportunity["proposal_status"] = "FAILED"
            opportunity["failure_reason"] = "LLM returned empty proposal"
            opportunity["proposal"] = ""
            opportunity["proposal_exists"] = False
        else:
            opportunity["proposal_status"] = "SUCCESS"
            opportunity["failure_reason"] = ""
            opportunity["proposal"] = prop
            opportunity["proposal_exists"] = True

        return opportunity
