
import os
import json
from dotenv import load_dotenv
from groq import Groq

from jobs.job_scanner import JobScanner


# ============================================================
# MEGA FREELANCER
# PHASE 3.1
# REWARD INTELLIGENCE + PROFIT OPPORTUNITY ENGINE
# ============================================================

load_dotenv()


# ============================================================
# CONFIG
# ============================================================

GROQ_API_KEY = os.getenv(
    "GROQ_API_KEY"
)

if not GROQ_API_KEY:

    raise RuntimeError(
        "\n❌ GROQ_API_KEY is missing.\n\n"
        "Your project needs a .env file containing:\n\n"
        "GROQ_API_KEY=YOUR_GROQ_API_KEY\n"
    )


client = Groq(
    api_key=GROQ_API_KEY
)

scanner = JobScanner()

MODEL_NAME = (
    "llama-3.3-70b-versatile"
)


# ============================================================
# AI OPPORTUNITY EVALUATOR
# ============================================================

def evaluate_opportunity(
    job: dict,
) -> dict:

    system_prompt = """
You are MEGA's strict freelance opportunity
intelligence engine.

Your job is to evaluate whether a public opportunity
is worth further investigation by a software freelancer.

IMPORTANT RULES:

1. NEVER invent a reward.

2. The scanner provides:
   - reward
   - currency
   - reward_confidence
   - reward_evidence

   Treat those as source evidence.

3. If reward is null:
   reward must remain null.

4. A GitHub issue with "help wanted" is NOT automatically
   a paid job.

5. Human-only tasks must be rejected.

Examples:
- human video evaluation
- surveys
- subjective preference testing
- physical tasks
- attending events
- identity verification
- interviews requiring the actual person
- tasks requiring personal accounts or personal presence

6. Software/technical work is preferred.

Examples:
- Python
- JavaScript
- C/C++
- APIs
- automation
- backend
- testing
- DevOps
- GitHub development
- bug fixes
- data processing
- dashboards
- integrations

7. Paid technical work should score higher than unpaid
   technical work.

8. Unknown reward does NOT mean the task is worthless.
   It means payment is uncertain.

9. Do not say payment is guaranteed.

10. SELECT means:
    "Good candidate for further research/proposal."

    It does NOT mean:
    "Guaranteed payment."

11. For security vulnerabilities:
    Do not provide exploit instructions.
    Only evaluate whether the opportunity is suitable
    and whether the program appears legitimate.

Return ONLY valid JSON:

{
    "job_type": "software|research|design|content|human_task|security|other",
    "reward": null,
    "currency": null,
    "reward_confidence": "structured|stated|unknown",
    "human_only": false,
    "ai_suitable": true,
    "difficulty": 1,
    "estimated_hours": 1.0,
    "success_probability": 0,
    "profit_score": 0,
    "decision": "SELECT|SKIP|NEEDS_REVIEW",
    "reason": "",
    "required_skills": [],
    "risks": []
}
"""

    user_prompt = f"""
Evaluate this opportunity.

PLATFORM:
{job.get("platform")}

TYPE:
{job.get("type")}

TITLE:
{job.get("title")}

DESCRIPTION:
{job.get("description", "")}

SOURCE REWARD:
{job.get("reward")}

SOURCE CURRENCY:
{job.get("currency")}

SOURCE REWARD CONFIDENCE:
{job.get("reward_confidence")}

SOURCE REWARD EVIDENCE:
{job.get("reward_evidence")}

SOURCE REWARD VERIFIED:
{job.get("reward_verified")}

URL:
{job.get("url")}

REPOSITORY:
{job.get("repository")}

LABELS:
{job.get("labels")}
"""

    try:

        response = client.chat.completions.create(

            messages=[
                {
                    "role": "system",
                    "content": system_prompt,
                },
                {
                    "role": "user",
                    "content": user_prompt,
                },
            ],

            model=MODEL_NAME,

            response_format={
                "type": "json_object"
            },
        )

        result = json.loads(
            response.choices[
                0
            ].message.content
        )

        # ----------------------------------------------------
        # NEVER TRUST AI TO INVENT PAYMENT
        # ----------------------------------------------------

        source_reward = job.get(
            "reward"
        )

        source_currency = job.get(
            "currency"
        )

        source_confidence = job.get(
            "reward_confidence",
            "unknown",
        )

        source_evidence = job.get(
            "reward_evidence"
        )

        if source_reward is None:

            result["reward"] = None

            result["currency"] = None

            result[
                "reward_confidence"
            ] = "unknown"

        else:

            result["reward"] = (
                source_reward
            )

            result["currency"] = (
                source_currency
            )

            result[
                "reward_confidence"
            ] = source_confidence

        # ----------------------------------------------------
        # Human-only hard block
        # ----------------------------------------------------

        if result.get(
            "human_only",
            False,
        ):

            result[
                "decision"
            ] = "SKIP"

            result[
                "profit_score"
            ] = 0

            result[
                "ai_suitable"
            ] = False

        # ----------------------------------------------------
        # AI unsuitable hard block
        # ----------------------------------------------------

        if not result.get(
            "ai_suitable",
            False,
        ):

            result[
                "decision"
            ] = "SKIP"

        # ----------------------------------------------------
        # Unknown payment cannot become a confirmed
        # paid opportunity.
        # ----------------------------------------------------

        if source_reward is None:

            if result.get(
                "decision"
            ) == "SELECT":

                result[
                    "decision"
                ] = "NEEDS_REVIEW"

        # ----------------------------------------------------
        # Security-sensitive work
        # ----------------------------------------------------

        if result.get(
            "job_type"
        ) == "security":

            # Keep evaluation conservative.
            if result.get(
                "decision"
            ) == "SELECT":

                result[
                    "decision"
                ] = "NEEDS_REVIEW"

        # ----------------------------------------------------
        # Numeric validation
        # ----------------------------------------------------

        try:

            difficulty = int(
                result.get(
                    "difficulty",
                    10,
                )
            )

        except (
            ValueError,
            TypeError,
        ):

            difficulty = 10

        result[
            "difficulty"
        ] = max(
            1,
            min(
                10,
                difficulty,
            ),
        )

        try:

            hours = float(
                result.get(
                    "estimated_hours",
                    10,
                )
            )

        except (
            ValueError,
            TypeError,
        ):

            hours = 10.0

        result[
            "estimated_hours"
        ] = max(
            0.1,
            min(
                1000.0,
                hours,
            ),
        )

        try:

            probability = int(
                result.get(
                    "success_probability",
                    0,
                )
            )

        except (
            ValueError,
            TypeError,
        ):

            probability = 0

        result[
            "success_probability"
        ] = max(
            0,
            min(
                100,
                probability,
            ),
        )

        try:

            profit_score = int(
                result.get(
                    "profit_score",
                    0,
                )
            )

        except (
            ValueError,
            TypeError,
        ):

            profit_score = 0

        result[
            "profit_score"
        ] = max(
            0,
            min(
                100,
                profit_score,
            ),
        )

        # ----------------------------------------------------
        # Extra evidence field
        # ----------------------------------------------------

        result[
            "source_reward_evidence"
        ] = source_evidence

        return result

    except Exception as exc:

        print(
            "   ⚠️ AI evaluation failed: "
            f"{exc}"
        )

        return {
            "job_type": "other",
            "reward": None,
            "currency": None,
            "reward_confidence": "unknown",
            "human_only": False,
            "ai_suitable": False,
            "difficulty": 10,
            "estimated_hours": 0,
            "success_probability": 0,
            "profit_score": 0,
            "decision": "NEEDS_REVIEW",
            "reason": (
                "AI evaluation failed."
            ),
            "required_skills": [],
            "risks": [
                "AI evaluation failure"
            ],
        }


# ============================================================
# EVALUATE ALL OPPORTUNITIES
# ============================================================

def evaluate_all_opportunities(
    jobs: list,
) -> list:

    results = []

    print("\n")
    print("=" * 60)
    print(
        "🧠 MEGA OPPORTUNITY INTELLIGENCE V4"
    )
    print("=" * 60)

    for index, job in enumerate(
        jobs,
        start=1,
    ):

        print(
            f"\n[{index}/{len(jobs)}] "
            "Analyzing:"
        )

        print(
            f"   {job.get('title')}"
        )

        evaluation = (
            evaluate_opportunity(
                job
            )
        )

        combined = {
            **job,
            "evaluation": evaluation,
            "decision": evaluation.get(
                "decision",
                "NEEDS_REVIEW",
            ),
            "profit_score": evaluation.get(
                "profit_score",
                0,
            ),
        }

        results.append(
            combined
        )

        reward = (
            evaluation.get(
                "reward"
            )
        )

        currency = (
            evaluation.get(
                "currency"
            )
        )

        print(
            f"   Decision: "
            f"{combined['decision']}"
        )

        print(
            f"   Reward: "
            f"{reward} "
            f"{currency or ''}".strip()
        )

        print(
            f"   Profit Score: "
            f"{combined['profit_score']}/100"
        )

    # --------------------------------------------------------
    # Ranking
    # --------------------------------------------------------

    results.sort(
        key=lambda job: (
            job.get(
                "profit_score",
                0,
            ),
            1
            if job.get(
                "reward"
            ) is not None
            else 0,
        ),
        reverse=True,
    )

    return results


# ============================================================
# PAID CANDIDATE FILTER
# ============================================================

def get_paid_candidates(
    jobs: list,
) -> list:

    candidates = []

    for job in jobs:

        evaluation = job.get(
            "evaluation",
            {},
        )

        reward = evaluation.get(
            "reward"
        )

        reward_confidence = (
            evaluation.get(
                "reward_confidence",
                "unknown",
            )
        )

        decision = job.get(
            "decision"
        )

        human_only = evaluation.get(
            "human_only",
            False,
        )

        ai_suitable = evaluation.get(
            "ai_suitable",
            False,
        )

        # ----------------------------------------------------
        # We accept explicitly stated/structured rewards.
        # We do NOT call them guaranteed.
        # ----------------------------------------------------

        if (
            reward is not None
            and reward_confidence
            in {
                "structured",
                "stated",
            }
            and decision == "SELECT"
            and not human_only
            and ai_suitable
        ):

            candidates.append(
                job
            )

    candidates.sort(
        key=lambda job: job.get(
            "profit_score",
            0,
        ),
        reverse=True,
    )

    return candidates


# ============================================================
# TOP OPPORTUNITIES
# ============================================================

def display_top_opportunities(
    jobs: list,
    limit: int = 10,
):

    print("\n")
    print("=" * 60)
    print(
        "📊 TOP OPPORTUNITIES"
    )
    print("=" * 60)

    for rank, job in enumerate(
        jobs[:limit],
        start=1,
    ):

        evaluation = job.get(
            "evaluation",
            {},
        )

        reward = (
            evaluation.get(
                "reward"
            )
        )

        currency = (
            evaluation.get(
                "currency"
            )
        )

        reward_text = (
            f"{reward} "
            f"{currency or ''}".strip()
            if reward is not None
            else "Unknown"
        )

        print(
            f"\n#{rank} "
            f"[{job.get('profit_score')}/100]"
        )

        print(
            f"Platform: "
            f"{job.get('platform')}"
        )

        print(
            f"Title: "
            f"{job.get('title')}"
        )

        print(
            f"Reward: "
            f"{reward_text}"
        )

        print(
            f"Reward Confidence: "
            f"{evaluation.get('reward_confidence')}"
        )

        print(
            f"Decision: "
            f"{job.get('decision')}"
        )

        print(
            f"Difficulty: "
            f"{evaluation.get('difficulty')}/10"
        )

        print(
            f"Estimated Hours: "
            f"{evaluation.get('estimated_hours')}"
        )

        print(
            f"Success Probability: "
            f"{evaluation.get('success_probability')}%"
        )

        if job.get(
            "reward_evidence"
        ):

            print(
                f"Evidence: "
                f"{job.get('reward_evidence')}"
            )

        print(
            f"URL: "
            f"{job.get('url')}"
        )


# ============================================================
# REWARD REPORT
# ============================================================

def display_reward_report(
    jobs: list,
):

    reward_jobs = [
        job
        for job in jobs
        if job.get(
            "reward"
        ) is not None
    ]

    print("\n")
    print("=" * 60)
    print(
        "💰 REWARD DETECTION REPORT"
    )
    print("=" * 60)

    print(
        f"Opportunities scanned: "
        f"{len(jobs)}"
    )

    print(
        f"Explicit rewards found: "
        f"{len(reward_jobs)}"
    )

    if not reward_jobs:

        print(
            "\nNo explicit rewards detected."
        )

        return

    for job in reward_jobs:

        print("\n")
        print(
            f"🎯 {job.get('title')}"
        )

        print(
            f"   Platform: "
            f"{job.get('platform')}"
        )

        print(
            f"   Reward: "
            f"{job.get('reward')} "
            f"{job.get('currency') or ''}"
        )

        print(
            f"   Confidence: "
            f"{job.get('reward_confidence')}"
        )

        print(
            f"   Evidence: "
            f"{job.get('reward_evidence')}"
        )


# ============================================================
# BEST PAID OPPORTUNITY
# ============================================================

def select_best_paid_opportunity(
    candidates: list,
):

    print("\n")
    print("=" * 60)
    print(
        "💰 PAID OPPORTUNITY FILTER"
    )
    print("=" * 60)

    print(
        f"Paid candidates: "
        f"{len(candidates)}"
    )

    if not candidates:

        print("\n")
        print("=" * 60)
        print(
            "⚠️ NO PAID OPPORTUNITY "
            "READY FOR PROPOSAL"
        )
        print("=" * 60)

        print(
            "\nMEGA will not pretend that "
            "an unknown or invented reward "
            "is real."
        )

        return None

    best = candidates[0]

    evaluation = best.get(
        "evaluation",
        {},
    )

    print("\n")
    print("=" * 60)
    print(
        "🏆 BEST PAID OPPORTUNITY"
    )
    print("=" * 60)

    print(
        f"Platform: "
        f"{best.get('platform')}"
    )

    print(
        f"Title: "
        f"{best.get('title')}"
    )

    print(
        f"Reward: "
        f"{evaluation.get('reward')} "
        f"{evaluation.get('currency') or ''}"
    )

    print(
        f"Reward Confidence: "
        f"{evaluation.get('reward_confidence')}"
    )

    print(
        f"Profit Score: "
        f"{evaluation.get('profit_score')}/100"
    )

    print(
        f"Difficulty: "
        f"{evaluation.get('difficulty')}/10"
    )

    print(
        f"Estimated Hours: "
        f"{evaluation.get('estimated_hours')}"
    )

    print(
        f"Success Probability: "
        f"{evaluation.get('success_probability')}%"
    )

    print(
        f"Reason: "
        f"{evaluation.get('reason')}"
    )

    print(
        f"URL: "
        f"{best.get('url')}"
    )

    return best


# ============================================================
# PROPOSAL GENERATOR
# ============================================================

def generate_proposal(
    job: dict,
) -> str:

    evaluation = job.get(
        "evaluation",
        {},
    )

    proposal_prompt = """
You are MEGA's professional freelance proposal writer.

Create a concise and honest proposal for the opportunity.

RULES:

1. Never invent previous clients.
2. Never invent experience.
3. Never invent certifications.
4. Never claim the task is already completed.
5. Never guarantee success.
6. Never claim payment is guaranteed.
7. Do not mention being an AI.
8. Show understanding of the client's actual problem.
9. Explain a realistic technical approach.
10. Keep the proposal natural and professional.
11. Do not spam keywords.
12. Do not include fake portfolio links.

Structure:

- Opening
- Understanding of task
- Technical approach
- Testing/quality approach
- Closing

Maximum approximately 250 words.
"""

    user_prompt = f"""
PLATFORM:
{job.get('platform')}

TITLE:
{job.get('title')}

DESCRIPTION:
{job.get('description', '')}

REWARD:
{evaluation.get('reward')}

CURRENCY:
{evaluation.get('currency')}

REQUIRED SKILLS:
{evaluation.get('required_skills', [])}

RISKS:
{evaluation.get('risks', [])}
"""

    try:

        response = client.chat.completions.create(

            messages=[
                {
                    "role": "system",
                    "content": proposal_prompt,
                },
                {
                    "role": "user",
                    "content": user_prompt,
                },
            ],

            model=MODEL_NAME,
        )

        return (
            response.choices[
                0
            ].message.content.strip()
        )

    except Exception as exc:

        return (
            "❌ Proposal generation failed:\n"
            f"{exc}"
        )


# ============================================================
# MAIN
# ============================================================

def main():

    print("\n")
    print("=" * 60)
    print(
        "🤖 MEGA FREELANCER"
    )
    print(
        "💰 PHASE 3.1 — REWARD INTELLIGENCE"
    )
    print("=" * 60)

    # --------------------------------------------------------
    # 1. Scan public opportunities
    # --------------------------------------------------------

    jobs = (
        scanner.scan_for_opportunities()
    )

    if not jobs:

        print(
            "\n❌ No opportunities found."
        )

        return

    print(
        f"\n📥 Total opportunities: "
        f"{len(jobs)}"
    )

    # --------------------------------------------------------
    # 2. Show reward detection BEFORE AI
    # --------------------------------------------------------

    display_reward_report(
        jobs
    )

    # --------------------------------------------------------
    # 3. AI evaluation
    # --------------------------------------------------------

    evaluated_jobs = (
        evaluate_all_opportunities(
            jobs
        )
    )

    # --------------------------------------------------------
    # 4. Display rankings
    # --------------------------------------------------------

    display_top_opportunities(
        evaluated_jobs,
        limit=10,
    )

    # --------------------------------------------------------
    # 5. Paid candidate filter
    # --------------------------------------------------------

    paid_candidates = (
        get_paid_candidates(
            evaluated_jobs
        )
    )

    # --------------------------------------------------------
    # 6. Select best
    # --------------------------------------------------------

    best = (
        select_best_paid_opportunity(
            paid_candidates
        )
    )

    # --------------------------------------------------------
    # 7. Proposal generation
    # --------------------------------------------------------

    if best is None:

        print("\n")
        print("=" * 60)
        print(
            "⚠️ PHASE 3.1 COMPLETE"
        )
        print("=" * 60)

        print(
            "\nNo paid opportunity passed "
            "all safety and evidence checks."
        )

        return

    print("\n")
    print("=" * 60)
    print(
        "✍️ GENERATING PERSONALIZED PROPOSAL"
    )
    print("=" * 60)

    proposal = generate_proposal(
        best
    )

    print("\n")
    print(proposal)

    # --------------------------------------------------------
    # Submission deliberately disabled
    # --------------------------------------------------------

    print("\n")
    print("=" * 60)
    print(
        "⏸️ SUBMISSION STATUS"
    )
    print("=" * 60)

    print(
        "\nProposal generated successfully."
    )

    print(
        "🚫 Automatic submission is currently OFF."
    )

    print(
        "No application has been submitted."
    )

    print(
        "\nNext phase can add controlled "
        "submission for platforms/methods "
        "where automation is permitted."
    )


# ============================================================
# START
# ============================================================

if __name__ == "__main__":
    main()